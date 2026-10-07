"""
Lance 12 experiments MLflow :
- 6 Isolation Forest (contamination x n_estimators)
- 6 GRU (architecture x fenetre temporelle)
"""
import os
import random
import sys
import time

os.environ["MLFLOW_TRACKING_URI"] = "http://localhost:5000"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

import mlflow
import mlflow.sklearn
import mlflow.tensorflow
import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.ensemble import IsolationForest, RandomForestRegressor
from sklearn.metrics import f1_score, mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
from tensorflow.keras.layers import Dense, GRU, LSTM
from tensorflow.keras.models import Sequential
from tensorflow.keras.optimizers import Adam

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from simulator.physics_simulator import PhysicsSimulator, SENSOR_NAMES
from ml_models.predictive_maintenance.prepare_simulator_data import prepare_data

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
tf.random.set_seed(SEED)

SENSORS = SENSOR_NAMES
WINDOW_SIZE = 15


def compute_window_features(raw_records):
    records = []
    for mid in set(r["machine_id"] for r in raw_records):
        machine_records = [r for r in raw_records if r["machine_id"] == mid]
        for i in range(WINDOW_SIZE, len(machine_records) + 1):
            window = machine_records[i - WINDOW_SIZE:i]
            feat = {"machine_id": mid}
            hi_vals = [r.get("hi", 100) for r in window]
            feat["hi_mean"] = float(np.mean(hi_vals))
            feat["hi_last"] = float(hi_vals[-1])
            feat["is_anomaly"] = hi_vals[-1] < 20

            for s in SENSORS:
                vals = [r[s] for r in window if s in r]
                if len(vals) == WINDOW_SIZE:
                    arr = np.array(vals, dtype=float)
                    feat[f"{s}_mean"] = float(np.mean(arr))
                    feat[f"{s}_std"] = float(np.std(arr))
                    feat[f"{s}_min"] = float(np.min(arr))
                    feat[f"{s}_max"] = float(np.max(arr))

            vib = np.array([
                [r.get("vibration_axial", 0), r.get("vibration_radial", 0), r.get("vibration_vertical", 0)]
                for r in window
            ], dtype=float)
            feat["vibration_rms"] = float(np.sqrt(np.mean(vib ** 2)))
            records.append(feat)
    return records


def generate_anomaly_data():
    sim = PhysicsSimulator(seed=SEED)
    raw_records = []
    for machine_id in sim.machine_ids:
        lifecycle = sim.generate_lifecycle(machine_id, total_cycles=300)
        raw_records.extend(lifecycle)

    features = compute_window_features(raw_records)
    df = pd.DataFrame(features)

    feature_cols = [c for c in df.columns if c.endswith(("_mean", "_std", "_min", "_max")) or c == "vibration_rms"]
    X = df[feature_cols].fillna(0).values
    y = df["is_anomaly"].astype(int).values
    return X, y, feature_cols


# ═══════════════════════════════════════════════
# ISOLATION FOREST - 6 runs
# ═══════════════════════════════════════════════
IF_CONFIGS = [
    {"contamination": 0.03, "n_estimators": 100},
    {"contamination": 0.05, "n_estimators": 150},
    {"contamination": 0.05, "n_estimators": 300},
    {"contamination": 0.08, "n_estimators": 200},
    {"contamination": 0.10, "n_estimators": 250},
    {"contamination": 0.15, "n_estimators": 400},
]


def run_isolation_forest():
    print("\n" + "=" * 60)
    print("  ISOLATION FOREST - 6 runs")
    print("=" * 60)

    X, y, feature_cols = generate_anomaly_data()
    indices = np.random.permutation(len(X))
    X, y = X[indices], y[indices]
    split = int(len(X) * 0.8)
    X_train, X_test, y_test = X[:split], X[split:], y[split:]

    mlflow.set_experiment("anomaly_detection")

    for i, cfg in enumerate(IF_CONFIGS):
        print(f"\n--- Run {i+1}/6: contamination={cfg['contamination']}, n_estimators={cfg['n_estimators']} ---")
        with mlflow.start_run(run_name=f"IF_run_{i+1}"):
            pipeline = Pipeline([
                ("scaler", StandardScaler()),
                ("model", IsolationForest(
                    contamination=cfg["contamination"],
                    n_estimators=cfg["n_estimators"],
                    random_state=SEED,
                    max_samples="auto",
                )),
            ])
            pipeline.fit(X_train)

            X_test_scaled = pipeline.named_steps["scaler"].transform(X_test)
            scores = -pipeline.named_steps["model"].score_samples(X_test_scaled)
            thresholds = np.percentile(scores, np.arange(1, 50))
            best_f1, best_thresh = 0, thresholds[0]
            for t in thresholds:
                y_pred = (scores >= t).astype(int)
                f1 = f1_score(y_test, y_pred, zero_division=0)
                if f1 > best_f1:
                    best_f1 = f1
                    best_thresh = t

            mlflow.log_param("algorithm", "IsolationForest")
            mlflow.log_param("contamination", cfg["contamination"])
            mlflow.log_param("n_estimators", cfg["n_estimators"])
            mlflow.log_param("n_features", len(feature_cols))
            mlflow.log_param("n_train", len(X_train))
            mlflow.log_param("n_test", len(X_test))
            mlflow.log_param("best_threshold", f"{best_thresh:.4f}")
            mlflow.log_metric("f1_score", best_f1)
            mlflow.log_metric("mean_anomaly_score", float(np.mean(scores)))
            mlflow.log_metric("std_anomaly_score", float(np.std(scores)))
            mlflow.sklearn.log_model(pipeline, "isolation_forest_model")

            print(f"  F1={best_f1:.4f}, threshold={best_thresh:.4f}")


# ═══════════════════════════════════════════════
# GRU / LSTM - 6 runs
# ═══════════════════════════════════════════════
GRU_CONFIGS = [
    {"units_1": 64, "units_2": 32, "seq_length": 30, "lr": 0.001, "rnn": "GRU"},
    {"units_1": 128, "units_2": 64, "seq_length": 50, "lr": 0.001, "rnn": "GRU"},
    {"units_1": 128, "units_2": 64, "seq_length": 50, "lr": 0.0005, "rnn": "LSTM"},
    {"units_1": 256, "units_2": 128, "seq_length": 50, "lr": 0.001, "rnn": "GRU"},
    {"units_1": 128, "units_2": 64, "seq_length": 70, "lr": 0.0005, "rnn": "GRU"},
    {"units_1": 64, "units_2": 32, "seq_length": 30, "lr": 0.001, "rnn": "LSTM"},
]


def build_model(cfg, n_features):
    RNN = GRU if cfg["rnn"] == "GRU" else LSTM
    model = Sequential([
        RNN(cfg["units_1"], return_sequences=True, input_shape=(None, n_features)),
        RNN(cfg["units_2"], return_sequences=False),
        Dense(32, activation="relu"),
        Dense(1),
    ])
    model.compile(optimizer=Adam(learning_rate=cfg["lr"]), loss="mse", metrics=["mae"])
    return model


def run_gru_lstm():
    print("\n" + "=" * 60)
    print("  GRU / LSTM - 6 runs")
    print("=" * 60)

    mlflow.set_experiment("predictive_maintenance")

    for i, cfg in enumerate(GRU_CONFIGS):
        print(f"\n--- Run {i+1}/6: {cfg['rnn']} units={cfg['units_1']}/{cfg['units_2']} seq={cfg['seq_length']} lr={cfg['lr']} ---")

        (X_train, y_train), (X_val, y_val), (X_test, y_test), n_features, scaler = prepare_data(
            n_machines=10, seq_length=cfg["seq_length"], seed=SEED
        )

        with mlflow.start_run(run_name=f"{cfg['rnn']}_run_{i+1}"):
            model = build_model(cfg, n_features)
            callbacks = [
                EarlyStopping(patience=10, restore_best_weights=True, min_delta=1),
                ReduceLROnPlateau(patience=5, factor=0.5, min_lr=1e-6),
            ]
            history = model.fit(
                X_train, y_train,
                validation_data=(X_val, y_val),
                epochs=100,
                batch_size=32,
                callbacks=callbacks,
                verbose=0,
            )

            y_pred = model.predict(X_test, verbose=0).flatten()
            rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
            mae = float(mean_absolute_error(y_test, y_pred))

            X_train_flat = X_train.reshape(X_train.shape[0], -1)
            X_test_flat = X_test.reshape(X_test.shape[0], -1)
            rf = RandomForestRegressor(n_estimators=200, random_state=SEED, n_jobs=-1)
            rf.fit(X_train_flat, y_train)
            y_rf = rf.predict(X_test_flat)
            rf_rmse = float(np.sqrt(mean_squared_error(y_test, y_rf)))

            mlflow.log_param("algorithm", cfg["rnn"])
            mlflow.log_param("units_1", cfg["units_1"])
            mlflow.log_param("units_2", cfg["units_2"])
            mlflow.log_param("seq_length", cfg["seq_length"])
            mlflow.log_param("learning_rate", cfg["lr"])
            mlflow.log_param("n_features", n_features)
            mlflow.log_param("n_train", len(X_train))
            mlflow.log_param("n_test", len(X_test))
            mlflow.log_param("epochs_trained", len(history.history["loss"]))
            mlflow.log_metric("rmse", rmse)
            mlflow.log_metric("mae", mae)
            mlflow.log_metric("baseline_rmse", rf_rmse)
            mlflow.keras.log_model(model, f"{cfg['rnn'].lower()}_rul_model")

            print(f"  RMSE={rmse:.2f}, MAE={mae:.2f}, RF_baseline={rf_rmse:.2f}")


if __name__ == "__main__":
    print("MLFLOW_TRACKING_URI:", os.environ.get("MLFLOW_TRACKING_URI"))
    t0 = time.time()
    run_isolation_forest()
    run_gru_lstm()
    print(f"\n{'='*60}")
    print(f"  12 experiments termines en {time.time()-t0:.0f}s")
    print(f"  Ouvrez http://localhost:5000 pour voir les resultats")
    print(f"{'='*60}")
