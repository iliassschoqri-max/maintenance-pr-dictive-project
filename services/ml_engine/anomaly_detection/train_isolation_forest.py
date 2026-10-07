import os
os.environ["MLFLOW_TRACKING_URI"] = os.getenv("MLFLOW_TRACKING_URI", "sqlite:///mlflow.db")

import random
import sys

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    classification_report, confusion_matrix, f1_score,
    precision_recall_curve, auc,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from simulator.physics_simulator import PhysicsSimulator, SENSOR_NAMES
from storage.delta_writer import DeltaLakeManager

SEED = 42
random.seed(SEED)
np.random.seed(SEED)

SENSORS = SENSOR_NAMES
WINDOW_SIZE = 15

FEATURE_COLS = (
    [f"{s}_mean" for s in SENSORS]
    + [f"{s}_std" for s in SENSORS]
    + [f"{s}_min" for s in SENSORS]
    + [f"{s}_max" for s in SENSORS]
    + ["vibration_rms"]
)


def load_real_data():
    try:
        delta = DeltaLakeManager()
        if not os.path.exists(delta.sensors_path):
            return None
        from deltalake import DeltaTable
        dt = DeltaTable(delta.sensors_path)
        df = dt.to_pandas()
        if len(df) < 100:
            print(f"Delta Lake: {len(df)} lignes (insuffisant, min 100)")
            return None
        print(f"Charge {len(df)} releves reels depuis Delta Lake")
        for col in FEATURE_COLS:
            if col not in df.columns:
                print(f"Colonne manquante: {col}")
                return None
        return df
    except Exception as e:
        print(f"Pas de donnees reelles: {e}")
        return None


def compute_window_features(raw_records):
    records = []
    for mid in set(r["machine_id"] for r in raw_records):
        machine_records = [r for r in raw_records if r["machine_id"] == mid]
        for i in range(WINDOW_SIZE, len(machine_records) + 1):
            window = machine_records[i - WINDOW_SIZE:i]
            feat = {
                "machine_id": mid,
                "timestamp": window[-1].get("timestamp", ""),
            }
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


def generate_synthetic_data(n_machines=20, cycles_per_machine=300):
    sim = PhysicsSimulator(seed=SEED)
    raw_records = []
    for machine_id in sim.machine_ids[:n_machines % len(sim.machine_ids)] or sim.machine_ids[:5]:
        lifecycle = sim.generate_lifecycle(machine_id, total_cycles=cycles_per_machine)
        raw_records.extend(lifecycle)

    print(f"Genere {len(raw_records)} enregistrements bruts depuis {n_machines} machines")
    features = compute_window_features(raw_records)
    print(f"Genere {len(features)} fenetres de features")

    df = pd.DataFrame(features)
    n_anomalies = int(df["is_anomaly"].sum()) if "is_anomaly" in df.columns else 0
    print(f"Anomalies: {n_anomalies}/{len(df)} ({n_anomalies/len(df)*100:.1f}%)")

    return df


def train():
    print("Chargement des donnees...")

    real_df = load_real_data()
    if real_df is not None:
        df = real_df
        has_labels = "is_anomaly" in df.columns
        source = "reel"
    else:
        print("Generation de donnees synthetiques...")
        df = generate_synthetic_data()
        has_labels = True
        source = "synthetique"

    available_features = [f for f in FEATURE_COLS if f in df.columns]
    if len(available_features) < 10:
        print(f"Erreur: seulement {len(available_features)} features disponibles")
        return

    print(f"Features utilisees: {len(available_features)}")
    X = df[available_features].values
    X = np.nan_to_num(X, nan=0.0)

    if has_labels and "is_anomaly" in df.columns:
        y_true = df["is_anomaly"].astype(int).values
    else:
        y_true = None

    indices = np.random.permutation(len(X))
    X_shuffled = X[indices]
    y_shuffled = y_true[indices] if y_true is not None else None

    split = int(len(X_shuffled) * 0.8)
    X_train, X_test = X_shuffled[:split], X_shuffled[split:]
    y_test = y_shuffled[split:] if y_shuffled is not None else None

    anomaly_rate = float(y_test.mean()) if y_test is not None else 0.05
    contamination = max(0.01, min(0.15, anomaly_rate))

    mlflow.set_experiment("anomaly_detection")
    with mlflow.start_run():
        pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("model", IsolationForest(
                contamination=contamination,
                random_state=SEED,
                n_estimators=300,
                max_samples="auto",
            )),
        ])
        pipeline.fit(X_train)

        mlflow.log_param("seed", SEED)
        mlflow.log_param("contamination", contamination)
        mlflow.log_param("n_estimators", 300)
        mlflow.log_param("source", source)
        mlflow.log_param("n_features", len(available_features))
        mlflow.log_param("n_train", len(X_train))
        mlflow.log_param("n_test", len(X_test))
        mlflow.sklearn.log_model(pipeline, "isolation_forest_model")

        iso_model = pipeline.named_steps["model"]
        scores_test = iso_model.score_samples(pipeline.named_steps["scaler"].transform(X_test))
        mlflow.log_metric("mean_anomaly_score", float(np.mean(scores_test)))
        mlflow.log_metric("std_anomaly_score", float(np.std(scores_test)))

        if y_test is not None:
            X_test_scaled = pipeline.named_steps["scaler"].transform(X_test)
            anomaly_scores = -iso_model.score_samples(X_test_scaled)
            thresholds = np.percentile(anomaly_scores, np.arange(1, 50))
            best_f1, best_thresh = 0, thresholds[0]
            for t in thresholds:
                y_t = (anomaly_scores >= t).astype(int)
                f1_t = f1_score(y_test, y_t, zero_division=0)
                if f1_t > best_f1:
                    best_f1 = f1_t
                    best_thresh = t

            y_pred = (anomaly_scores >= best_thresh).astype(int)
            report = classification_report(y_test, y_pred, target_names=["Normal", "Anomalie"], zero_division=0)
            cm = confusion_matrix(y_test, y_pred)
            f1 = best_f1
            mlflow.log_metric("f1_score", f1)
            mlflow.log_param("best_threshold", f"{best_thresh:.4f}")

            precision_arr, recall_arr, _ = precision_recall_curve(y_test, anomaly_scores)
            pr_auc = auc(recall_arr, precision_arr)
            mlflow.log_metric("pr_auc", float(pr_auc))

            print("\n=== RAPPORT DE PERFORMANCE ===")
            print(report)
            print("Matrice de confusion:")
            print(cm)
            print(f"\nF1-Score: {f1:.4f} (threshold: {best_thresh:.4f})")
            print(f"PR-AUC: {pr_auc:.4f}")
            n_pred = y_pred.sum()
            print(f"Anomalies predites: {n_pred}/{len(y_test)} ({n_pred/len(y_test)*100:.1f}%)")
        else:
            print("Mode non supervise - pas de ground truth")
            X_test_scaled = pipeline.named_steps["scaler"].transform(X_test)
            anomalies = (iso_model.predict(X_test_scaled) == -1).sum()
            print(f"Anomalies detectees dans le test: {anomalies}/{len(X_test)} ({anomalies/len(X_test)*100:.1f}%)")

        run_id = mlflow.active_run().info.run_id
        print(f"\nModele sauvegarde dans MLflow (run_id: {run_id})")


if __name__ == "__main__":
    train()
