"""Training RUL prediction - version autonome pour Airflow Docker"""
import os
import random

os.environ["MLFLOW_TRACKING_URI"] = os.getenv("MLFLOW_TRACKING_URI", "sqlite:///mlflow.db")

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
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

SEQ_LENGTH = 50
MACHINE_IDS = ["INJ-01", "INJ-02", "SOUD-01", "ASSY-01", "PEINT-01", "FRAIS-01", "TOUR-01"]


def generate_data(n_machines=7, cycles=250):
    records = []
    for i in range(n_machines):
        mid = MACHINE_IDS[i % len(MACHINE_IDS)]
        hi = 100.0
        for c in range(cycles):
            hi -= random.uniform(0.1, 0.5)
            hi = max(0, hi)
            rul = hi * cycles / 100.0
            rec = {"machine_id": mid, "cycle": c + 1, "hi": hi, "rul": rul}
            for s in SENSOR_NAMES:
                base = random.uniform(20, 80)
                degradation = (100 - hi) / 100.0
                rec[s] = base * (1 + degradation * random.uniform(0.1, 0.5)) + random.gauss(0, base * 0.02)
                rec[s] = max(0, rec[s])
            records.append(rec)
    return pd.DataFrame(records)


def prepare_data():
    df = generate_data()
    Xs, ys = [], []
    for mid in df["machine_id"].unique():
        mdf = df[df["machine_id"] == mid].reset_index(drop=True)
        vals = mdf[SENSOR_NAMES].fillna(0).values
        ruls = mdf["rul"].values
        for i in range(SEQ_LENGTH, len(vals)):
            Xs.append(vals[i - SEQ_LENGTH:i].flatten())
            ys.append(ruls[i])

    X = np.array(Xs)
    y = np.array(ys)
    scaler = StandardScaler()
    X = scaler.fit_transform(X)

    split1 = int(len(X) * 0.7)
    split2 = int(len(X) * 0.85)
    return (X[:split1], y[:split1]), (X[split1:split2], y[split1:split2]), (X[split2:], y[split2:])


def train():
    print("Preparation des donnees...")
    (X_train, y_train), (X_val, y_val), (X_test, y_test) = prepare_data()
    print(f"Train: {len(X_train)}, Val: {len(X_val)}, Test: {len(X_test)}")

    mlflow.set_experiment("predictive_maintenance")

    configs = [
        {"n_estimators": 200, "max_depth": 15, "name": "RF_depth15"},
        {"n_estimators": 300, "max_depth": 20, "name": "RF_depth20"},
    ]

    for i, cfg in enumerate(configs):
        print(f"\n--- Run {i+1}/2: {cfg['name']} ---")
        with mlflow.start_run(run_name=f"{cfg['name']}_dag_run_{i+1}"):
            rf = RandomForestRegressor(
                n_estimators=cfg["n_estimators"],
                max_depth=cfg["max_depth"],
                random_state=SEED,
                n_jobs=-1,
            )
            rf.fit(X_train, y_train)
            y_pred = rf.predict(X_test)

            rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
            mae = float(mean_absolute_error(y_test, y_pred))

            mlflow.log_param("algorithm", "RandomForest")
            mlflow.log_param("n_estimators", cfg["n_estimators"])
            mlflow.log_param("max_depth", cfg["max_depth"])
            mlflow.log_param("n_features", X_train.shape[1])
            mlflow.log_param("seq_length", SEQ_LENGTH)
            mlflow.log_param("n_train", len(X_train))
            mlflow.log_param("n_test", len(X_test))
            mlflow.log_metric("rmse", rmse)
            mlflow.log_metric("mae", mae)

            print(f"  RMSE={rmse:.2f}, MAE={mae:.2f}")

    print("\nTraining RUL termine avec succes")


if __name__ == "__main__":
    train()
