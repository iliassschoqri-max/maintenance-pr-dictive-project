import json
import random
import time
from datetime import datetime, timezone


class SensorSimulator:
    MACHINE_PROFILES = {
        "INJ-01": {
            "type": "injection_plastique",
            "temperature": (70.0, 5.0, True),
            "vibration": (0.03, 0.01, False),
            "pressure": (5.0, 0.5, True),
            "courant_moteur": (12.5, 1.5, False),
        },
        "INJ-02": {
            "type": "injection_plastique",
            "temperature": (72.0, 5.0, True),
            "vibration": (0.035, 0.01, False),
            "pressure": (5.2, 0.5, True),
            "courant_moteur": (13.0, 1.5, False),
        },
        "SOUD-01": {
            "type": "soudure",
            "temperature": (65.0, 4.0, False),
            "vibration": (0.04, 0.015, False),
            "pressure": (4.5, 0.4, False),
            "courant_moteur": (14.0, 2.0, True),
        },
        "ASSY-01": {
            "type": "assemblage",
            "temperature": (60.0, 3.0, False),
            "vibration": (0.045, 0.018, True),
            "pressure": (4.8, 0.4, False),
            "courant_moteur": (11.0, 1.2, False),
        },
        "PEINT-01": {
            "type": "peinture",
            "temperature": (75.0, 6.0, True),
            "vibration": (0.025, 0.008, False),
            "pressure": (5.5, 0.6, False),
            "courant_moteur": (10.5, 1.0, False),
        },
        "FRAIS-01": {
            "type": "fraisage_cnc",
            "temperature": (68.0, 5.0, True),
            "vibration": (0.042, 0.012, True),
            "pressure": (6.0, 0.5, True),
            "courant_moteur": (15.0, 2.0, True),
        },
        "TOUR-01": {
            "type": "tour_cnc",
            "temperature": (63.0, 4.5, False),
            "vibration": (0.032, 0.010, False),
            "pressure": (5.0, 0.45, False),
            "courant_moteur": (13.5, 1.8, True),
        },
    }

    def __init__(self):
        self.machine_ids = list(self.MACHINE_PROFILES.keys())
        self.drift_state = {mid: 0.0 for mid in self.machine_ids}

    def _generate_normal_value(self, mean, std_dev):
        value = random.gauss(mean, std_dev)
        return round(float(max(value, 0)), 3)

    def _inject_anomaly(self, value, sensor_is_critical):
        if sensor_is_critical:
            anomaly_type = random.choices(["pic", "derive"], weights=[0.6, 0.4])[0]
        else:
            anomaly_type = "pic"
        if anomaly_type == "pic":
            return round(value * random.uniform(1.8, 2.8), 3)
        else:
            return round(value * random.uniform(1.15, 1.4), 3)

    def _update_drift(self, machine_id, is_anomaly):
        if is_anomaly:
            self.drift_state[machine_id] += random.uniform(0.001, 0.005)
        return self.drift_state[machine_id]

    def generate_reading(self, machine_id, anomaly_probability=0.05):
        profile = self.MACHINE_PROFILES[machine_id]
        is_anomaly = random.random() < anomaly_probability

        reading = {
            "machine_id": machine_id,
            "machine_type": profile["type"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        for sensor, sensor_value in profile.items():
            if sensor == "type":
                continue
            mean, std_dev, is_critical = sensor_value
            value = self._generate_normal_value(mean, std_dev)
            if is_anomaly:
                value = self._inject_anomaly(value, is_critical)
                if is_critical:
                    drift = self._update_drift(machine_id, is_anomaly)
                    value = round(value * (1 + drift), 3)
            reading[sensor] = value

        reading["_is_anomaly_ground_truth"] = is_anomaly
        return reading

    def stream(self, interval_seconds=2, kafka_producer=None, topic=None):
        print(f"Simulateur demarre - {len(self.machine_ids)} machines")
        try:
            while True:
                for machine_id in self.machine_ids:
                    reading = self.generate_reading(machine_id)
                    if kafka_producer:
                        kafka_producer.send(topic or "sensors-raw", value=reading)
                        kafka_producer.flush()
                    else:
                        print(json.dumps(reading, indent=2))
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            print("\nSimulateur arrêté.")


if __name__ == "__main__":
    sim = SensorSimulator()
    sim.stream(interval_seconds=2)
