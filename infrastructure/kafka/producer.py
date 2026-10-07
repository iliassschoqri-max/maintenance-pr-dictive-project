import json
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from kafka import KafkaProducer
from simulator.sensor_simulator import SensorSimulator

BOOTSTRAP_SERVERS = "localhost:9092"
TOPIC = "sensors-raw"

producer = KafkaProducer(
    bootstrap_servers=BOOTSTRAP_SERVERS,
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
)

sim = SensorSimulator()
sim.stream(interval_seconds=2, kafka_producer=producer, topic=TOPIC)
