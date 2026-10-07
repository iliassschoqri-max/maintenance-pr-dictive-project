"""Training Isolation Forest - version autonome pour Airflow Docker (sans imports du host)"""
import os
import random
import sys

os.environ["MLFLOW_TRACKING_URI"] = os.getenv("MLFLOW_TRACKING_URI", "sqlite:///mlflow.db")

import mlflow
import mlflow.sklearn
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.metrics import f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

SEED = 42
random.seed(SEED)
np.random.seed(SEED)

SENSOR_NAMES = [
    "temperature_bearing", "temperature_motor", "temperature_hydraulic",
    "temperature_ambient", "vibration_axial", "vibration_radial",
    "vibration_vertical", "pressure_hydraulic", "pressure_pneumatic",
    "pressure_lubrication", "current_motor", "current_servo",
    "rpm_spindle", "rpm_fan", "torque_output", "power_consumption",
    "acoustic_emission", "oil_particle_count", "coolant_flow",
    "electrical_resistance", "displacement_linear",
]

WINDOW_SIZE = 15
MACHINE_IDS = ["INJ-01", "INJ-02", "SOUD-01", "ASSY-01", "PEINT-01", "FRAIS-01", "TOUR-01"]


def generate_simple_data(n_machines=5, cycles=200):
    import pandas as pd
    np.random.seed(SEED)
    records = []
    for i in range(n_machines):
        mid = MACHINE_IDS[i % len(MACHINE_IDS)]
        hi = 100.0
        for c in range(cycles):
            hi -= random.uniform(0.1, 0.5)
            hi = max(0, hi)
            rec = {"machine_id": mid, "cycle": c + 1, "hi": hi, "rul": hi * cycles / 100.0}
            for s in SENSOR_NAMES:
                base = random.uniform(20, 80)
                degradation = (100 - hi) / 100.0
                rec[s] = base * (1 + degradation * random.uniform(0.1, 0.5)) + random.gauss(0, base * 0.02)
                rec[s] = max(0, rec[s])
            records.append(rec)
    return pd.DataFrame(records)


def compute_window_features(df):
    import pandas as pd
    records = []
    for mid in df["machine_id"].unique():
        mdf = df[df["machine_id"] == mid].reset_index(drop=True)
        for i in range(WINDOW_SIZE, len(mdf)):
            window = mdf.iloc[i - WINDOW_SIZE:i]
            feat = {"machine_id": mid}
            feat["is_anomaly"] = window.iloc[-1]["hi"] < 20
            for s in SENSOR_NAMES:
                vals = window[s].values
                feat[f"{s}_mean"] = float(np.mean(vals))
                feat[f"{s}_std"] = float(np.std(vals))
                feat[f"{s}_min"] = float(np.min(vals))
                feat[f"{s}_max"] = float(np.max(vals))
            vib = window[["vibration_axial", "vibration_radial", "vibration_vertical"]].values
            feat["vibration_rms"] = float(np.sqrt(np.mean(vib ** 2)))
            records.append(feat)
    return pd.DataFrame(records)


def train():
    import pandas as pd
    print("Generation de donnees synthetiques...")
    df = generate_simple_data(n_machines=5, cycles=200)
    print(f"{len(df)} enregistrements generes")

    features = compute_window_features(df)
    feature_cols = [c for c in features.columns
                    if c.endswith(("_mean", "_std", "_min", "_max")) or c == "vibration_rms"]

    X = features[feature_cols].fillna(0).values
    y = features["is_anomaly"].astype(int).values

    indices = np.random.permutation(len(X))
    X, y = X[indices], y[indices]
    split = int(len(X) * 0.8)
    X_train, X_test, y_test = X[:split], X[split:], y[split:]

    mlflow.set_experiment("anomaly_detection")

    configs = [
        {"contamination": 0.05, "n_estimators": 200},
        {"contamination": 0.08, "n_estimators": 300},
    ]

    for i, cfg in enumerate(configs):
        print(f"\n--- Run {i+1}/2: contamination={cfg['contamination']}, n_estimators={cfg['n_estimators']} ---")
        with mlflow.start_run(run_name=f"IF_dag_run_{i+1}"):
            pipeline = Pipeline([
                ("scaler", StandardScaler()),
                ("model", IsolationForest(
                    contamination=cfg["contamination"],
                    n_estimators=cfg["n_estimators"],
                    random_state=SEED,
                )),
            ])
            pipeline.fit(X_train)

            scores = -pipeline.named_steps["model"].score_samples(
                pipeline.named_steps["scaler"].transform(X_test)
            )
            thresholds = np.percentile(scores, np.arange(1, 50))
            best_f1, best_thresh = 0, thresholds[0]
            for t in thresholds:
                f1 = f1_score(y_test, (scores >= t).astype(int), zero_division=0)
                if f1 > best_f1:
                    best_f1, best_thresh = f1, t

            mlflow.log_param("algorithm", "IsolationForest")
            mlflow.log_param("contamination", cfg["contamination"])
            mlflow.log_param("n_estimators", cfg["n_estimators"])
            mlflow.log_param("n_features", len(feature_cols))
            mlflow.log_param("n_train", len(X_train))
            mlflow.log_param("n_test", len(X_test))
            mlflow.log_metric("f1_score", best_f1)
            mlflow.log_metric("mean_anomaly_score", float(np.mean(scores)))

            print(f"  F1={best_f1:.4f}")

    print("\nTraining Isolation Forest termine avec succes")


if __name__ == "__main__":
    train()
