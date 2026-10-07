import os
from dotenv import load_dotenv

load_dotenv()

# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC_SENSORS = "sensor_data"
KAFKA_TOPIC_ANOMALIES = "anomalies"

# InfluxDB Configuration
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "pfa_org")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "pfa_bucket")

# Storage Paths
DELTA_LAKE_PATH = os.path.join(os.getcwd(), "data", "delta_lake")
MODEL_REGISTRY_PATH = os.path.join(os.getcwd(), "services", "ml_engine", "saved_models")
