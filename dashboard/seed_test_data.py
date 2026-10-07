import math
import random
from datetime import datetime, timedelta, timezone

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

INFLUXDB_URL = "http://localhost:8086"
INFLUXDB_TOKEN = "admin123admin123admin123admin123ad=="
INFLUXDB_ORG = "orhan"
INFLUXDB_BUCKET = "sensors"

MACHINES = ["MACH-01", "MACH-02", "MACH-03", "MACH-04", "MACH-05"]

MACHINE_PROFILES = {
    "MACH-01": {
        "type": "injection_plastique",
        "temp_bearing": 65.0, "temp_motor": 72.0, "temp_hydraulic": 55.0,
        "vibration_axial": 0.032, "vibration_radial": 0.028,
        "pressure_hydraulic": 5.0, "pressure_pneumatic": 3.2,
        "current_motor": 12.5, "current_servo": 3.8,
        "rpm_spindle": 1450.0, "power_consumption": 3.2,
        "acoustic_emission": 42.0, "oil_particle_count": 15.0,
        "coolant_flow": 8.5, "electrical_resistance": 0.12,
        "displacement_linear": 0.05,
    },
    "MACH-02": {
        "type": "injection_plastique",
        "temp_bearing": 68.0, "temp_motor": 75.0, "temp_hydraulic": 58.0,
        "vibration_axial": 0.035, "vibration_radial": 0.030,
        "pressure_hydraulic": 5.2, "pressure_pneumatic": 3.4,
        "current_motor": 13.0, "current_servo": 4.0,
        "rpm_spindle": 1480.0, "power_consumption": 3.4,
        "acoustic_emission": 44.0, "oil_particle_count": 18.0,
        "coolant_flow": 8.2, "electrical_resistance": 0.13,
        "displacement_linear": 0.055,
    },
    "MACH-03": {
        "type": "soudure",
        "temp_bearing": 60.0, "temp_motor": 68.0, "temp_hydraulic": 50.0,
        "vibration_axial": 0.040, "vibration_radial": 0.035,
        "pressure_hydraulic": 4.5, "pressure_pneumatic": 3.0,
        "current_motor": 14.0, "current_servo": 5.2,
        "rpm_spindle": 1200.0, "power_consumption": 4.1,
        "acoustic_emission": 55.0, "oil_particle_count": 12.0,
        "coolant_flow": 6.0, "electrical_resistance": 0.10,
        "displacement_linear": 0.045,
    },
    "MACH-04": {
        "type": "assemblage",
        "temp_bearing": 58.0, "temp_motor": 65.0, "temp_hydraulic": 48.0,
        "vibration_axial": 0.045, "vibration_radial": 0.040,
        "pressure_hydraulic": 4.8, "pressure_pneumatic": 3.5,
        "current_motor": 11.0, "current_servo": 3.5,
        "rpm_spindle": 1600.0, "power_consumption": 2.8,
        "acoustic_emission": 48.0, "oil_particle_count": 10.0,
        "coolant_flow": 9.0, "electrical_resistance": 0.11,
        "displacement_linear": 0.06,
    },
    "MACH-05": {
        "type": "peinture",
        "temp_bearing": 70.0, "temp_motor": 78.0, "temp_hydraulic": 60.0,
        "vibration_axial": 0.025, "vibration_radial": 0.022,
        "pressure_hydraulic": 5.5, "pressure_pneumatic": 4.0,
        "current_motor": 10.5, "current_servo": 3.2,
        "rpm_spindle": 1100.0, "power_consumption": 2.5,
        "acoustic_emission": 38.0, "oil_particle_count": 8.0,
        "coolant_flow": 10.0, "electrical_resistance": 0.14,
        "displacement_linear": 0.04,
    },
}

ANOMALY_EVENTS = [
    {"machine": "MACH-01", "hour": -3,  "duration": 10, "severity": "high",   "capteur": "temperature_bearing"},
    {"machine": "MACH-02", "hour": -8,  "duration": 12, "severity": "medium", "capteur": "vibration_axial"},
    {"machine": "MACH-03", "hour": -6,  "duration": 15, "severity": "medium", "capteur": "current_motor"},
    {"machine": "MACH-04", "hour": -2,  "duration": 8,  "severity": "high",   "capteur": "vibration_axial"},
    {"machine": "MACH-05", "hour": -12, "duration": 20, "severity": "low",    "capteur": "pressure_hydraulic"},
    {"machine": "MACH-01", "hour": -20, "duration": 5,  "severity": "low",    "capteur": "oil_particle_count"},
    {"machine": "MACH-03", "hour": -18, "duration": 30, "severity": "low",    "capteur": "acoustic_emission"},
    {"machine": "MACH-05", "hour": -1,  "duration": 5,  "severity": "high",   "capteur": "temperature_bearing"},
]


def gen(base, noise, hour, anomaly=False, strength=0):
    daily = math.sin(hour / 24 * 2 * math.pi) * 0.5
    val = base + daily + random.gauss(0, noise)
    if anomaly:
        val += strength * random.choice([-1, 1]) * base * 0.3
    return round(max(0.0, val), 4)


def compute_health(anomaly_score, rul_days):
    a = 50 * (1 / (1 + math.exp(-anomaly_score / 5)))
    r = max(0.0, 30 * (1 - rul_days / 100))
    return round(max(0.0, min(100.0, 100 - a - r)), 2)


def main():
    client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
    write_api = client.write_api(write_options=SYNCHRONOUS)
    now = datetime.now(timezone.utc)
    print("Generation des donnees de test...")

    points_raw = []
    points_health = []
    points_anomalies = []
    added_anomalies = set()

    for minute_offset in range(0, 24 * 60):
        ts = now - timedelta(minutes=minute_offset)
        hour = ts.hour + ts.minute / 60

        for mid, p in MACHINE_PROFILES.items():
            anomaly_active = False
            anomaly_capteur = None
            anomaly_strength = 0

            for event in ANOMALY_EVENTS:
                event_start = now + timedelta(hours=event["hour"])
                event_end = event_start + timedelta(minutes=event["duration"])
                if mid == event["machine"] and event_start <= ts <= event_end:
                    anomaly_active = True
                    anomaly_capteur = event["capteur"]
                    anomaly_strength = {"low": 1, "medium": 2, "high": 3}[event["severity"]]
                    if (mid, event["hour"]) not in added_anomalies and random.random() < 0.1:
                        added_anomalies.add((mid, event["hour"]))
                        anomaly_status = random.choices(
                            ["active", "resolved", "false_positive"], weights=[60, 25, 15]
                        )[0]
                        points_anomalies.append(
                            Point("anomalies")
                            .tag("machine_id", mid)
                            .tag("severity", event["severity"])
                            .tag("status", anomaly_status)
                            .field("alert_id", f"{mid}-{int(ts.timestamp())}")
                            .field("anomaly_score", round(-anomaly_strength * 2.5, 4))
                            .field("capteur", anomaly_capteur)
                            .field("comment", f"Anomaly detectee ({anomaly_capteur})")
                            .time(ts)
                        )
                    break

            is_anom = anomaly_active and anomaly_capteur == "temperature_bearing"
            is_anom_v = anomaly_active and anomaly_capteur == "vibration_axial"
            is_anom_c = anomaly_active and anomaly_capteur == "current_motor"
            is_anom_p = anomaly_active and anomaly_capteur == "pressure_hydraulic"
            is_anom_o = anomaly_active and anomaly_capteur == "oil_particle_count"
            is_anom_a = anomaly_active and anomaly_capteur == "acoustic_emission"

            pt = Point("sensor_reading").tag("machine_id", mid)
            pt = pt.field("temperature_bearing_mean", gen(p["temp_bearing"], 0.8, hour, is_anom, anomaly_strength))
            pt = pt.field("temperature_motor_mean", gen(p["temp_motor"], 1.0, hour, is_anom, anomaly_strength))
            pt = pt.field("temperature_hydraulic_mean", gen(p["temp_hydraulic"], 0.7, hour, is_anom, anomaly_strength))
            pt = pt.field("vibration_axial_mean", gen(p["vibration_axial"], 0.003, hour, is_anom_v, anomaly_strength))
            pt = pt.field("vibration_radial_mean", gen(p["vibration_radial"], 0.003, hour, is_anom_v, anomaly_strength))
            pt = pt.field("vibration_vertical_mean", gen(p["vibration_axial"] * 0.8, 0.002, hour))
            pt = pt.field("pressure_hydraulic_mean", gen(p["pressure_hydraulic"], 0.15, hour, is_anom_p, anomaly_strength))
            pt = pt.field("pressure_pneumatic_mean", gen(p["pressure_pneumatic"], 0.1, hour))
            pt = pt.field("pressure_lubrication_mean", gen(p["pressure_hydraulic"] * 0.4, 0.08, hour))
            pt = pt.field("current_motor_mean", gen(p["current_motor"], 0.3, hour, is_anom_c, anomaly_strength))
            pt = pt.field("current_servo_mean", gen(p["current_servo"], 0.15, hour))
            pt = pt.field("rpm_spindle_mean", gen(p["rpm_spindle"], 10, hour))
            pt = pt.field("rpm_fan_mean", gen(p["rpm_spindle"] * 0.6, 8, hour))
            pt = pt.field("torque_output_mean", gen(p["power_consumption"] * 12, 1.5, hour))
            pt = pt.field("power_consumption_mean", gen(p["power_consumption"], 0.15, hour))
            pt = pt.field("acoustic_emission_mean", gen(p["acoustic_emission"], 2.0, hour, is_anom_a, anomaly_strength))
            pt = pt.field("oil_particle_count_mean", gen(p["oil_particle_count"], 1.5, hour, is_anom_o, anomaly_strength))
            pt = pt.field("coolant_flow_mean", gen(p["coolant_flow"], 0.3, hour))
            pt = pt.field("electrical_resistance_mean", gen(p["electrical_resistance"], 0.01, hour))
            pt = pt.field("displacement_linear_mean", gen(p["displacement_linear"], 0.005, hour))
            pt = pt.field("temperature_ambient_mean", gen(25.0, 0.5, hour))
            pt = pt.field("vibration_rms_mean", gen(p["vibration_axial"] * 1.1, 0.003, hour, is_anom_v, anomaly_strength))
            pt = pt.field("machine_id", mid)
            pt = pt.time(ts)
            points_raw.append(pt)

            anomaly_score = random.uniform(-2, 2)
            if anomaly_active:
                anomaly_score -= anomaly_strength * 3

            rul_noise = random.gauss(0, 5)
            rul_base = 200 - (now - ts).seconds / 3600 * 2
            rul_days = max(5.0, rul_base + rul_noise)
            health = compute_health(anomaly_score, rul_days)

            if health >= 70:
                status = "normal"
            elif health >= 40:
                status = "warning"
            else:
                status = "critical"

            hs = (
                Point("health_score")
                .tag("machine_id", mid)
                .field("health_score", health)
                .field("anomaly_score", round(anomaly_score, 4))
                .field("rul_days", round(rul_days, 2))
                .field("status", status)
                .time(ts)
            )
            points_health.append(hs)

        if minute_offset % 500 == 0:
            print(f"  Progression: {minute_offset}/{24*60} minutes")

    write_api.write(bucket=INFLUXDB_BUCKET, record=points_raw)
    print(f"  sensor_reading: {len(points_raw)} points ecrits")

    write_api.write(bucket=INFLUXDB_BUCKET, record=points_health)
    print(f"  health_score: {len(points_health)} points ecrits")

    if points_anomalies:
        write_api.write(bucket=INFLUXDB_BUCKET, record=points_anomalies)
        print(f"  anomalies: {len(points_anomalies)} evenements ecrits")

    print("\nDonnees de test injectees dans InfluxDB !")
    print(f"  Machines: {', '.join(MACHINES)}")
    print(f"  Period: dernieres 24h")
    print(f"  Anomalies simulees: {len(ANOMALY_EVENTS)}")
    client.close()


if __name__ == "__main__":
    main()
