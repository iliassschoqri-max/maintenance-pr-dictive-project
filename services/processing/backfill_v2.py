"""
Add anomalies for ASSY-01 and fix health_score data.
Overwrite with clean backfill data for 10:00-11:00.
"""
import math
import random
from datetime import datetime, timezone, timedelta

import numpy as np
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

INFLUXDB_URL = "http://localhost:8086"
INFLUXDB_TOKEN = "admin123admin123admin123admin123ad=="
INFLUXDB_ORG = "orhan"
INFLUXDB_BUCKET = "sensors"

client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
write_api = client.write_api(write_options=SYNCHRONOUS)

MACHINES = {
    "INJ-01": {
        "baselines": {
            "temperature_bearing": 65.0, "temperature_motor": 72.0,
            "temperature_hydraulic": 55.0, "temperature_ambient": 25.0,
            "vibration_axial": 0.032, "vibration_radial": 0.028,
            "vibration_vertical": 0.025, "pressure_hydraulic": 5.0,
            "pressure_pneumatic": 3.2, "pressure_lubrication": 2.1,
            "current_motor": 12.5, "current_servo": 3.8,
            "rpm_spindle": 1450.0, "rpm_fan": 880.0,
            "torque_output": 45.0, "power_consumption": 3.2,
            "acoustic_emission": 42.0, "oil_particle_count": 15.0,
            "coolant_flow": 8.5, "electrical_resistance": 0.12,
            "displacement_linear": 0.05,
        },
        "health_start": 95.0, "health_end": 88.0,
        "anomaly_times": ["10:22:00", "10:45:00"],
        "anomaly_sensors": ["temperature_bearing", "vibration_axial"],
    },
    "INJ-02": {
        "baselines": {
            "temperature_bearing": 68.0, "temperature_motor": 75.0,
            "temperature_hydraulic": 58.0, "temperature_ambient": 25.0,
            "vibration_axial": 0.035, "vibration_radial": 0.030,
            "vibration_vertical": 0.027, "pressure_hydraulic": 5.2,
            "pressure_pneumatic": 3.4, "pressure_lubrication": 2.2,
            "current_motor": 13.0, "current_servo": 4.0,
            "rpm_spindle": 1480.0, "rpm_fan": 900.0,
            "torque_output": 47.0, "power_consumption": 3.4,
            "acoustic_emission": 44.0, "oil_particle_count": 18.0,
            "coolant_flow": 8.2, "electrical_resistance": 0.13,
            "displacement_linear": 0.055,
        },
        "health_start": 92.0, "health_end": 82.0,
        "anomaly_times": ["10:15:00", "10:35:00", "10:52:00"],
        "anomaly_sensors": ["vibration_radial", "pressure_hydraulic"],
    },
    "SOUD-01": {
        "baselines": {
            "temperature_bearing": 58.0, "temperature_motor": 68.0,
            "temperature_hydraulic": 50.0, "temperature_ambient": 25.0,
            "vibration_axial": 0.020, "vibration_radial": 0.018,
            "vibration_vertical": 0.015, "pressure_hydraulic": 4.5,
            "pressure_pneumatic": 3.0, "pressure_lubrication": 1.8,
            "current_motor": 18.0, "current_servo": 5.5,
            "rpm_spindle": 1200.0, "rpm_fan": 750.0,
            "torque_output": 60.0, "power_consumption": 4.0,
            "acoustic_emission": 55.0, "oil_particle_count": 10.0,
            "coolant_flow": 10.0, "electrical_resistance": 0.10,
            "displacement_linear": 0.04,
        },
        "health_start": 98.0, "health_end": 93.0,
        "anomaly_times": ["10:30:00"],
        "anomaly_sensors": ["acoustic_emission"],
    },
    "ASSY-01": {
        "baselines": {
            "temperature_bearing": 55.0, "temperature_motor": 65.0,
            "temperature_hydraulic": 48.0, "temperature_ambient": 25.0,
            "vibration_axial": 0.015, "vibration_radial": 0.012,
            "vibration_vertical": 0.010, "pressure_hydraulic": 4.0,
            "pressure_pneumatic": 2.8, "pressure_lubrication": 1.5,
            "current_motor": 10.0, "current_servo": 3.0,
            "rpm_spindle": 1100.0, "rpm_fan": 650.0,
            "torque_output": 35.0, "power_consumption": 2.5,
            "acoustic_emission": 38.0, "oil_particle_count": 8.0,
            "coolant_flow": 7.0, "electrical_resistance": 0.08,
            "displacement_linear": 0.03,
        },
        "health_start": 97.0, "health_end": 85.0,
        "anomaly_times": ["10:18:00", "10:42:00"],
        "anomaly_sensors": ["current_motor", "acoustic_emission"],
    },
    "PEINT-01": {
        "baselines": {
            "temperature_bearing": 50.0, "temperature_motor": 60.0,
            "temperature_hydraulic": 45.0, "temperature_ambient": 25.0,
            "vibration_axial": 0.018, "vibration_radial": 0.016,
            "vibration_vertical": 0.013, "pressure_hydraulic": 3.8,
            "pressure_pneumatic": 2.5, "pressure_lubrication": 1.3,
            "current_motor": 8.5, "current_servo": 2.8,
            "rpm_spindle": 900.0, "rpm_fan": 550.0,
            "torque_output": 30.0, "power_consumption": 2.0,
            "acoustic_emission": 35.0, "oil_particle_count": 6.0,
            "coolant_flow": 6.0, "electrical_resistance": 0.07,
            "displacement_linear": 0.025,
        },
        "health_start": 85.0, "health_end": 65.0,
        "anomaly_times": ["10:10:00", "10:25:00", "10:40:00", "10:55:00"],
        "anomaly_sensors": ["temperature_bearing", "vibration_axial", "oil_particle_count"],
    },
}

SENSOR_NAMES = list(MACHINES["INJ-01"]["baselines"].keys())
today = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0)
START = today
END = today + timedelta(hours=1)
INTERVAL_SEC = 30
BATCH_SIZE = 200


def noise_pct(base, pct):
    return base * random.uniform(-pct, pct)


def is_anomaly_time(mconf, ts):
    for at in mconf["anomaly_times"]:
        h, m, s = map(int, at.split(":"))
        at_time = START.replace(hour=h, minute=m, second=s)
        if abs((ts - at_time).total_seconds()) < 45:
            return True
    return False


points = []
total = 0

print(f"Backfilling {START.isoformat()} to {END.isoformat()} (ASSY-01 anomalies added)")

ts = START
while ts < END:
    progress = (ts - START).total_seconds() / (END - START).total_seconds()

    for mid, mconf in MACHINES.items():
        is_anom = is_anomaly_time(mconf, ts)

        pt = Point("sensor_reading").tag("machine_id", mid).time(ts)
        for sname in SENSOR_NAMES:
            base = mconf["baselines"][sname]
            val = base + noise_pct(base, 0.03)
            if is_anom and sname in mconf["anomaly_sensors"]:
                val = base * random.uniform(1.5, 2.5)
            if sname.startswith("vibration"):
                val = max(0.001, val)
            pt = pt.field(sname, round(float(val), 4))
        points.append(pt)

        health_range = mconf["health_end"] - mconf["health_start"]
        health_val = mconf["health_start"] + health_range * progress
        if is_anom:
            health_val -= random.uniform(5, 15)
        health_val = max(10.0, min(100.0, health_val))

        anomaly_score = 0.0
        if is_anom:
            anomaly_score = round(random.uniform(0.5, 2.0), 4)

        rul = max(1.0, (100 - health_val) * 5 + random.uniform(-10, 10))

        if health_val < 30:
            status = "critical"
        elif health_val < 60:
            status = "warning"
        else:
            status = "normal"

        hs = (
            Point("health_score").tag("machine_id", mid).time(ts)
            .field("health_score", round(float(health_val), 2))
            .field("anomaly_score", round(float(anomaly_score), 4))
            .field("rul_days", round(float(rul), 1))
            .field("status", status)
        )
        points.append(hs)

        if is_anom and anomaly_score > 0.3:
            severity = "high" if anomaly_score > 1.2 else "medium"
            alert_id = f"{mid}-{int(ts.timestamp())}"
            for asens in mconf["anomaly_sensors"]:
                ap = (
                    Point("anomalies").tag("machine_id", mid)
                    .tag("severity", severity).tag("status", "active").time(ts)
                    .field("alert_id", alert_id)
                    .field("anomaly_score", round(float(anomaly_score), 4))
                    .field("capteur", asens)
                    .field("comment", f"Anomaly on {asens} (score={anomaly_score:.3f})")
                )
                points.append(ap)

        total += 1

    if len(points) >= BATCH_SIZE:
        write_api.write(bucket=INFLUXDB_BUCKET, record=points)
        points = []
        if total % 300 == 0:
            print(f"  Written batch, ts={ts.strftime('%H:%M:%S')}, total={total}")

    ts += timedelta(seconds=INTERVAL_SEC)

if points:
    write_api.write(bucket=INFLUXDB_BUCKET, record=points)

write_api.close()
client.close()
print(f"\nDONE: {total} readings x {len(MACHINES)} machines (including ASSY-01 anomalies)")
