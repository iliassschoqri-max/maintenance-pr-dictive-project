from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError

BOOTSTRAP_SERVERS = "localhost:9092"
TOPIC = "sensors-raw"
PARTITIONS = 3
REPLICATION = 1

admin = KafkaAdminClient(bootstrap_servers=BOOTSTRAP_SERVERS)

topic = NewTopic(
    name=TOPIC,
    num_partitions=PARTITIONS,
    replication_factor=REPLICATION,
)

try:
    admin.create_topics([topic])
    print(f"Topic '{TOPIC}' créé avec {PARTITIONS} partitions.")
except TopicAlreadyExistsError:
    print(f"Le topic '{TOPIC}' existe déjà.")
