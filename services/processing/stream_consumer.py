import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
import pandas as pd
from deltalake import write_deltalake
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from kafka import KafkaConsumer

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = "sensors-raw"

INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "admin123admin123admin123admin123ad==")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "orhan")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "sensors")

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DELTA_SENSORS_PATH = os.path.join(DATA_DIR, "delta_lake", "sensors")
os.makedirs(DELTA_SENSORS_PATH, exist_ok=True)

SENSORS = [
    "temperature_bearing", "temperature_motor", "temperature_hydraulic",
    "temperature_ambient", "vibration_axial", "vibration_radial",
    "vibration_vertical", "pressure_hydraulic", "pressure_pneumatic",
    "pressure_lubrication", "current_motor", "current_servo",
    "rpm_spindle", "rpm_fan", "torque_output", "power_consumption",
    "acoustic_emission", "oil_particle_count", "coolant_flow",
    "electrical_resistance", "displacement_linear",
]
SENSOR_BOUNDS = {
    "temperature_bearing": (0.0, 200.0), "temperature_motor": (0.0, 200.0),
    "temperature_hydraulic": (0.0, 200.0), "temperature_ambient": (0.0, 60.0),
    "vibration_axial": (0.0, 0.5), "vibration_radial": (0.0, 0.5),
    "vibration_vertical": (0.0, 0.5), "pressure_hydraulic": (0.0, 20.0),
    "pressure_pneumatic": (0.0, 20.0), "pressure_lubrication": (0.0, 20.0),
    "current_motor": (0.0, 50.0), "current_servo": (0.0, 50.0),
    "rpm_spindle": (0.0, 5000.0), "rpm_fan": (0.0, 5000.0),
    "torque_output": (0.0, 200.0), "power_consumption": (0.0, 50.0),
    "acoustic_emission": (0.0, 120.0), "oil_particle_count": (0.0, 100.0),
    "coolant_flow": (0.0, 20.0), "electrical_resistance": (0.0, 100.0),
    "displacement_linear": (0.0, 50.0),
}
WINDOW_SIZE = 15
GRU_SEQ_LENGTH = 50

FEATURE_COLS = (
    [f"{s}_mean" for s in SENSORS]
    + [f"{s}_std" for s in SENSORS]
    + [f"{s}_min" for s in SENSORS]
    + [f"{s}_max" for s in SENSORS]
    + ["vibration_rms"]
)

window_buffer = defaultdict(list)

anomaly_model = None
rul_model = None
health_calc = None
mlflow_tracking_uri = os.path.join(os.path.dirname(__file__), "..", "mlflow.db")


def load_ml_models():
    global anomaly_model, rul_model, health_calc
    os.environ["MLFLOW_TRACKING_URI"] = f"sqlite:///{mlflow_tracking_uri}"
    print(f"[ML] MLflow URI: {mlflow_tracking_uri}")
    try:
        from ml_models.anomaly_detection.predict import AnomalyPredictor
        anomaly_model = AnomalyPredictor()
        print("[ML] IsolationForest charge OK")
    except Exception as e:
        print(f"[ML] IsolationForest ERREUR: {e}")
    try:
        from ml_models.predictive_maintenance.predict import RULPredictor
        rul_model = RULPredictor()
        print(f"[ML] GRU RUL charge OK, type: {type(rul_model.model)}")
    except Exception as e:
        print(f"[ML] GRU RUL ERREUR: {e}")
    from ml_models.health_score import HealthScoreCalculator
    health_calc = HealthScoreCalculator()
    print("[ML] HealthScoreCalculator pret")


def clean_reading(reading):
    for sensor, (lo, hi) in SENSOR_BOUNDS.items():
        val = reading.get(sensor)
        if val is not None and not (lo <= val <= hi):
            return None
    return reading


def compute_features(machine_id):
    buf = window_buffer.get(machine_id, [])
    if len(buf) < WINDOW_SIZE:
        return None
    recent = buf[-WINDOW_SIZE:]
    df = pd.DataFrame(recent)
    features = {"machine_id": machine_id, "timestamp": datetime.now(timezone.utc).isoformat()}
    for s in SENSORS:
        vals = df[s].values
        features[f"{s}_mean"] = float(np.mean(vals))
        features[f"{s}_std"] = float(np.std(vals))
        features[f"{s}_min"] = float(np.min(vals))
        features[f"{s}_max"] = float(np.max(vals))
    features["vibration_rms"] = float(np.sqrt(np.mean(df[["vibration_axial", "vibration_radial", "vibration_vertical"]].values ** 2)))
    return features


def predict_anomaly(features):
    if anomaly_model is None:
        return -5.0, False
    try:
        result = anomaly_model.predict(features)
        return result["anomaly_score"], result["is_anomaly"]
    except Exception as e:
        print(f"[ML] Anomaly predict error: {e}")
        return -5.0, False


def predict_rul(machine_id):
    if rul_model is None:
        print(f"[RUL] {machine_id}: modele non charge, fallback 150j")
        return 150.0
    buf = window_buffer.get(machine_id, [])
    if len(buf) < GRU_SEQ_LENGTH:
        if len(buf) % 10 == 0:
            print(f"[RUL] {machine_id}: buffer={len(buf)}/{GRU_SEQ_LENGTH}, attente...")
        return 150.0
    try:
        seq = buf[-GRU_SEQ_LENGTH:]
        df = pd.DataFrame(seq)
        arr = df[SENSORS].values.astype(np.float32)
        print(f"[RUL] {machine_id}: prediction avec shape={arr.shape}")
        result = rul_model.predict(arr)
        rul_val = result["rul_prediction"]
        print(f"[RUL] {machine_id}: RUL predit = {rul_val}j")
        return rul_val
    except Exception as e:
        print(f"[RUL] {machine_id}: ERREUR prediction: {e}")
        return 150.0


def write_to_influxdb(features, anomaly_score, is_anomaly, rul_pred, health_score, status):
    try:
        client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
        write_api = client.write_api(write_options=SYNCHRONOUS)

        pt = Point("sensor_reading").tag("machine_id", features["machine_id"])
        for k, v in features.items():
            if k in ("machine_id", "timestamp"):
                continue
            pt = pt.field(k, float(v) if isinstance(v, (int, float, np.integer, np.floating)) else v)
        write_api.write(bucket=INFLUXDB_BUCKET, record=pt)

        hs_point = (
            Point("health_score")
            .tag("machine_id", features["machine_id"])
            .field("health_score", float(health_score))
            .field("anomaly_score", float(anomaly_score))
            .field("rul_days", float(rul_pred))
            .field("status", status)
        )
        write_api.write(bucket=INFLUXDB_BUCKET, record=hs_point)

        if is_anomaly:
            alert_id = f"{features['machine_id']}-{int(time.time())}"
            severity = "high" if anomaly_score > 1.0 else "medium"
            a_point = (
                Point("anomalies")
                .tag("machine_id", features["machine_id"])
                .tag("severity", severity)
                .tag("status", "active")
                .field("alert_id", alert_id)
                .field("anomaly_score", float(anomaly_score))
                .field("capteur", "multi-sensor")
                .field("comment", f"Anomaly detected (score={anomaly_score:.3f})")
            )
            write_api.write(bucket=INFLUXDB_BUCKET, record=a_point)

        write_api.close()
        client.close()
    except Exception as e:
        print(f"[InfluxDB] Write failed: {e}")


def write_to_delta(features):
    try:
        df = pd.DataFrame([features])
        write_deltalake(DELTA_SENSORS_PATH, df, mode="append")
    except Exception as e:
        print(f"[Delta] Write failed: {e}")


def main_loop():
    print("[Consumer] Chargement des modeles ML...")
    load_ml_models()
    print(f"[Consumer] Connexion a Kafka: {KAFKA_BOOTSTRAP}, topic: {KAFKA_TOPIC}")
    consumer = KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="latest",
        max_poll_records=100,
    )
    print("[Consumer] En attente des messages...")
    count = 0
    for msg in consumer:
        reading = msg.value
        reading = clean_reading(reading)
        if reading is None:
            continue
        mid = reading["machine_id"]
        window_buffer.setdefault(mid, []).append(reading)
        if len(window_buffer[mid]) > GRU_SEQ_LENGTH + 50:
            window_buffer[mid] = window_buffer[mid][-(GRU_SEQ_LENGTH + 50):]
        features = compute_features(mid)
        if features:
            anomaly_score, is_anomaly = predict_anomaly(features)
            rul_pred = predict_rul(mid)
            health = health_calc.compute(anomaly_score, rul_pred)
            health_score = health["health_score"]
            status = health["status"]
            write_to_influxdb(features, anomaly_score, is_anomaly, rul_pred, health_score, status)
            write_to_delta(features)
            count += 1
            if count % 10 == 0:
                print(f"[OK] {mid} #{count} | health={health_score} status={status} anomaly={anomaly_score:.3f} rul={rul_pred:.0f}j")
            else:
                print(f"[OK] {mid} #{count} health={health_score}")


if __name__ == "__main__":
    main_loop()
