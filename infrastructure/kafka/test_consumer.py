from kafka import KafkaConsumer
import json

BOOTSTRAP_SERVERS = "localhost:9092"
TOPIC = "sensors-raw"

consumer = KafkaConsumer(
    TOPIC,
    bootstrap_servers=BOOTSTRAP_SERVERS,
    auto_offset_reset="latest",
    value_deserializer=lambda v: json.loads(v.decode("utf-8")),
)

print(f"En écoute sur '{TOPIC}'...")
for msg in consumer:
    print(f"[{msg.key}] {msg.value}")
