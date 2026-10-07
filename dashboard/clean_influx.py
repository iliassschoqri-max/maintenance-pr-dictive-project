from influxdb_client import InfluxDBClient

client = InfluxDBClient(url="http://localhost:8086", token="admin123admin123admin123admin123ad==", org="orhan")
delete_api = client.delete_api()
bucket = "sensors"
org = "orhan"
start = "2020-01-01T00:00:00Z"
stop = "2030-01-01T00:00:00Z"

for measurement in ["sensors_raw", "sensor_reading", "health_score", "anomalies"]:
    try:
        delete_api.delete(start, stop, f'_measurement="{measurement}"', bucket=bucket, org=org)
        print(f"Deleted {measurement}")
    except Exception as e:
        print(f"Skip {measurement}: {e}")

client.close()
print("Cleanup done")
