"""Lance le PhysicsSimulator en mode real-time → Kafka."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from kafka import KafkaProducer
from simulator.physics_simulator import PhysicsSimulator

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "sensors-raw")

print(f"Connexion a Kafka: {KAFKA_BOOTSTRAP}")
producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP,
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
)

print(f"Topic: {KAFKA_TOPIC}")
sim = PhysicsSimulator(seed=42)
sim.stream(interval_seconds=2, kafka_producer=producer, topic=KAFKA_TOPIC)
