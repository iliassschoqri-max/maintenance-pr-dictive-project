from __future__ import annotations

import os
from datetime import datetime, timezone

import pandas as pd
from deltalake import DeltaTable, write_deltalake

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "delta_lake")

SENSORS = [
    "temperature_bearing", "temperature_motor", "temperature_hydraulic",
    "temperature_ambient", "vibration_axial", "vibration_radial",
    "vibration_vertical", "pressure_hydraulic", "pressure_pneumatic",
    "pressure_lubrication", "current_motor", "current_servo",
    "rpm_spindle", "rpm_fan", "torque_output", "power_consumption",
    "acoustic_emission", "oil_particle_count", "coolant_flow",
    "electrical_resistance", "displacement_linear",
]

SENSORS_SCHEMA = {
    "machine_id": "string",
    "machine_type": "string",
    "timestamp": "timestamp",
    **{s: "double" for s in SENSORS},
    **{f"{s}_mean": "double" for s in SENSORS},
    **{f"{s}_std": "double" for s in SENSORS},
    "vibration_rms": "double",
    "health_score": "double",
    "anomaly_score": "double",
    "is_anomaly": "boolean",
}

FEEDBACK_SCHEMA = {
    "alert_id": "string",
    "machine_id": "string",
    "decision": "string",
    "comment": "string",
    "timestamp": "timestamp",
    "original_severity": "string",
    "original_score": "double",
}


def _write_df(table_path: str, df: pd.DataFrame, mode: str = "append"):
    os.makedirs(os.path.dirname(table_path), exist_ok=True)
    write_deltalake(
        table_path,
        df,
        mode=mode,
        partition_by=["machine_id"] if "machine_id" in df.columns else None,
    )


class DeltaLakeManager:
    def __init__(self, base_path: str = DATA_DIR):
        self.base_path = base_path
        self.sensors_path = os.path.join(base_path, "sensors")
        self.feedback_path = os.path.join(base_path, "feedback")

    # ── Sensors ──────────────────────────────────────

    def write_sensors(self, records: list[dict]) -> int:
        if not records:
            return 0
        df = pd.DataFrame(records)
        for col in SENSORS_SCHEMA:
            if col not in df.columns:
                df[col] = None
        df = df[list(SENSORS_SCHEMA.keys())]
        _write_df(self.sensors_path, df, mode="append")
        return len(df)

    def read_sensors(
        self,
        machine_id: str | None = None,
        limit: int = 100,
        hours: int | None = None,
    ) -> pd.DataFrame:
        if not os.path.exists(self.sensors_path):
            return pd.DataFrame()
        dt = DeltaTable(self.sensors_path)
        df = dt.to_pandas()
        if machine_id:
            df = df[df["machine_id"] == machine_id]
        if hours:
            cutoff = datetime.now(timezone.utc).timestamp() * 1_000_000_000
            cutoff -= hours * 3600 * 1_000_000_000
            df = df[df["timestamp"] >= cutoff]
        return df.sort_values("timestamp", ascending=False).head(limit)

    def get_version(self) -> int:
        if not os.path.exists(self.sensors_path):
            return -1
        return DeltaTable(self.sensors_path).version()

    def time_travel(self, version: int) -> pd.DataFrame:
        dt = DeltaTable(self.sensors_path)
        return dt.to_pandas(version=version)

    # ── Feedback ─────────────────────────────────────

    def write_feedback(self, record: dict) -> int:
        df = pd.DataFrame([record])
        for col in FEEDBACK_SCHEMA:
            if col not in df.columns:
                df[col] = None
        df = df[list(FEEDBACK_SCHEMA.keys())]
        _write_df(self.feedback_path, df, mode="append")
        return 1

    def read_feedback(
        self,
        machine_id: str | None = None,
        limit: int = 100,
    ) -> pd.DataFrame:
        if not os.path.exists(self.feedback_path):
            return pd.DataFrame()
        dt = DeltaTable(self.feedback_path)
        df = dt.to_pandas()
        if machine_id:
            df = df[df["machine_id"] == machine_id]
        return df.sort_values("timestamp", ascending=False).head(limit)

    # ── Stats ────────────────────────────────────────

    def get_table_stats(self, table: str = "sensors") -> dict:
        path = getattr(self, f"{table}_path", None)
        if not path or not os.path.exists(path):
            return {"exists": False, "version": -1, "num_records": 0}
        dt = DeltaTable(path)
        return {
            "exists": True,
            "version": dt.version(),
            "num_records": len(dt.to_pandas()),
            "path": path,
        }
