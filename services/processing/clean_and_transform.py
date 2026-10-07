"""
Traitement des données en streaming avec PySpark Structured Streaming.

Architecture :
  Kafka (topic: sensors-raw, 21 capteurs)
    → PySpark readStream (kafka)
    → JSON parsing + nettoyage (bornes physiques)
    → Feature engineering (fenêtrage glissant 15 mesures)
    → WriteStream → Delta Lake (partitionné par machine_id)
    → foreachBatch → InfluxDB (temps réel)

Exécution :
  python processing/clean_and_transform.py
"""
import json
import os
from datetime import datetime, timezone

os.environ["SPARK_LOCAL_HOSTNAME"] = "127.0.0.1"
os.environ["SPARK_LOCAL_IP"] = "127.0.0.1"
os.environ["PYSPARK_PYTHON"] = "python"

from delta import configure_spark_with_delta_pip
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    avg, col, from_json, max as spark_max, min as spark_min,
    sqrt, stddev, window, expr,
)
from pyspark.sql.types import (
    DoubleType, StringType, StructField, StructType, TimestampType,
)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = "sensors-raw"
WINDOW_DURATION = "30 seconds"
SLIDE_DURATION = "10 seconds"

INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "admin123admin123admin123admin123ad==")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "orhan")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "sensors")

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DELTA_SENSORS_PATH = os.path.join(DATA_DIR, "delta_lake", "sensors")

SENSORS = [
    "temperature_bearing", "temperature_motor", "temperature_hydraulic",
    "temperature_ambient", "vibration_axial", "vibration_radial",
    "vibration_vertical", "pressure_hydraulic", "pressure_pneumatic",
    "pressure_lubrication", "current_motor", "current_servo",
    "rpm_spindle", "rpm_fan", "torque_output", "power_consumption",
    "acoustic_emission", "oil_particle_count", "coolant_flow",
    "electrical_resistance", "displacement_linear",
]

KEY_SENSORS = [
    "temperature_bearing", "temperature_motor",
    "vibration_axial", "vibration_radial",
    "pressure_hydraulic", "current_motor",
    "rpm_spindle", "torque_output", "power_consumption",
    "acoustic_emission",
]

SENSOR_BOUNDS = {
    "temperature_bearing": (0.0, 200.0), "temperature_motor": (0.0, 200.0),
    "vibration_axial": (0.0, 0.5), "vibration_radial": (0.0, 0.5),
    "pressure_hydraulic": (0.0, 20.0), "current_motor": (0.0, 50.0),
    "rpm_spindle": (0.0, 5000.0), "torque_output": (0.0, 200.0),
    "power_consumption": (0.0, 50.0), "acoustic_emission": (0.0, 120.0),
}

KAFKA_SCHEMA = StructType([
    StructField("machine_id", StringType()),
    StructField("machine_type", StringType()),
    StructField("timestamp", StringType()),
    StructField("cycle", DoubleType()),
    StructField("hi", DoubleType()),
    StructField("rul", DoubleType()),
    StructField("regime", StringType()),
] + [StructField(s, DoubleType()) for s in SENSORS])

FEATURE_COLS = (
    [f"{s}_mean" for s in KEY_SENSORS]
    + [f"{s}_std" for s in KEY_SENSORS]
    + [f"{s}_min" for s in KEY_SENSORS]
    + [f"{s}_max" for s in KEY_SENSORS]
    + ["vibration_rms"]
)


def create_spark():
    builder = (
        SparkSession.builder
        .master("local[1]")
        .appName("PFA-Orhan-Spark")
        .config("spark.driver.host", "127.0.0.1")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .config("spark.driver.memory", "4g")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        .config("spark.sql.streaming.schemaInference", "true")
        .config("spark.sql.streaming.metricsEnabled", "false")
        .config("spark.sql.adaptive.enabled", "false")
        .config("spark.sql.debug.maxToStringFields", "200")
        .config("spark.cleaner.periodicGC.interval", "30s")
    )
    spark = configure_spark_with_delta_pip(
        builder,
        extra_packages=["org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.3"],
    ).getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    return spark


def write_to_influxdb(df, epoch_id):
    """foreachBatch: écrit le micro-batch Spark dans InfluxDB."""
    if df.isEmpty():
        return
    try:
        client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
        write_api = client.write_api(write_options=SYNCHRONOUS)
        rows = df.collect()
        for row in rows:
            mid = row["machine_id"]
            pt = Point("sensor_features").tag("machine_id", mid)
            if row.get("window") is not None:
                w = row["window"]
                if hasattr(w, 'start'):
                    pt = pt.time(w.start)
            for feat in FEATURE_COLS:
                val = row.get(feat)
                if val is not None:
                    pt = pt.field(feat, float(val))
            write_api.write(bucket=INFLUXDB_BUCKET, record=pt)
        write_api.close()
        client.close()
    except Exception as e:
        print(f"[InfluxDB] Write failed for batch {epoch_id}: {e}")


def main_loop():
    while True:
        spark = None
        try:
            spark = create_spark()
            print(f"[Spark] Lecture du topic Kafka: {KAFKA_TOPIC}")

            df_raw = (
                spark.readStream
                .format("kafka")
                .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
                .option("subscribe", KAFKA_TOPIC)
                .option("startingOffsets", "latest")
                .option("maxOffsetsPerTrigger", "1000")
                .option("failOnDataLoss", "false")
                .load()
            )

            df_json = (
                df_raw
                .select(from_json(col("value").cast("string"), KAFKA_SCHEMA).alias("data"))
                .select("data.*")
                .dropna(subset=KEY_SENSORS)
            )

            for sensor, (lo, hi) in SENSOR_BOUNDS.items():
                df_json = df_json.filter(col(sensor).between(lo, hi))

            df_ts = df_json.withColumn("ts", col("timestamp").cast(TimestampType()))

            agg_exprs = []
            for s in KEY_SENSORS:
                agg_exprs.extend([
                    avg(s).alias(f"{s}_mean"),
                    stddev(s).alias(f"{s}_std"),
                    spark_min(s).alias(f"{s}_min"),
                    spark_max(s).alias(f"{s}_max"),
                ])
            agg_exprs.append(
                sqrt(
                    avg(col("vibration_axial") ** 2)
                    + avg(col("vibration_radial") ** 2)
                    + avg(col("vibration_vertical") ** 2)
                ).alias("vibration_rms")
            )

            df_features = (
                df_ts
                .withWatermark("ts", "1 minute")
                .groupBy(col("machine_id"), window(col("ts"), WINDOW_DURATION, SLIDE_DURATION))
                .agg(*agg_exprs)
            )

            query_delta = (
                df_features.writeStream
                .format("delta")
                .option("checkpointLocation", os.path.join(DELTA_SENSORS_PATH, "_checkpoints"))
                .option("mergeSchema", "true")
                .option("maxRecordsPerFile", "10000")
                .partitionBy("machine_id")
                .outputMode("append")
                .start(DELTA_SENSORS_PATH)
            )

            query_influx = (
                df_features.writeStream
                .outputMode("append")
                .foreachBatch(write_to_influxdb)
                .start()
            )

            print("[Spark] Streaming actif - Delta Lake + InfluxDB")
            spark.streams.awaitAnyTermination()

        except Exception as e:
            err = str(e)
            if "KafkaMicroBatchStream" in err or "NullPointerException" in err:
                print(f"[Spark] Crash Kafka connu, redémarrage dans 5s...")
                if spark is not None:
                    try:
                        spark.stop()
                    except Exception:
                        pass
                import time
                time.sleep(5)
            else:
                raise


if __name__ == "__main__":
    main_loop()
