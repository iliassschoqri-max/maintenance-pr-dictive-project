import os
import random

import joblib
import mlflow
import mlflow.tensorflow
import numpy as np
import tensorflow as tf
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
from tensorflow.keras.layers import Dense, GRU
from tensorflow.keras.models import Sequential
from tensorflow.keras.optimizers import Adam

from prepare_simulator_data import prepare_data

os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"
os.environ["MLFLOW_TRACKING_URI"] = os.getenv("MLFLOW_TRACKING_URI", "sqlite:///mlflow.db")

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
tf.random.set_seed(SEED)


def build_gru(n_features):
    model = Sequential([
        GRU(128, return_sequences=True, input_shape=(None, n_features)),
        GRU(64, return_sequences=False),
        Dense(32, activation="relu"),
        Dense(1),
    ])
    model.compile(optimizer=Adam(learning_rate=0.001), loss="mse", metrics=["mae"])
    return model


def train():
    (X_train, y_train), (X_val, y_val), (X_test, y_test), n_features, scaler = prepare_data()

    mlflow.set_experiment("predictive_maintenance")
    with mlflow.start_run():
        model = build_gru(n_features)
        model.summary()

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
            verbose=1,
        )

        y_pred = model.predict(X_test, verbose=0).flatten()
        rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
        mae = float(mean_absolute_error(y_test, y_pred))

        X_train_flat = X_train.reshape(X_train.shape[0], -1)
        X_test_flat = X_test.reshape(X_test.shape[0], -1)
        baseline = RandomForestRegressor(n_estimators=200, random_state=SEED, n_jobs=-1)
        baseline.fit(X_train_flat, y_train)
        y_base = baseline.predict(X_test_flat)
        base_rmse = float(np.sqrt(mean_squared_error(y_test, y_base)))
        base_mae = float(mean_absolute_error(y_test, y_base))

        mlflow.log_param("seed", SEED)
        mlflow.log_param("data_source", "physics_simulator")
        mlflow.log_param("n_features", n_features)
        mlflow.log_param("seq_length", X_train.shape[1])
        mlflow.log_param("n_train_samples", len(X_train))
        mlflow.log_param("n_val_samples", len(X_val))
        mlflow.log_param("n_test_samples", len(X_test))
        mlflow.log_param("gru_units_1", 128)
        mlflow.log_param("gru_units_2", 64)
        mlflow.log_param("epochs_trained", len(history.history["loss"]))
        mlflow.log_metric("rmse", rmse)
        mlflow.log_metric("mae", mae)
        mlflow.log_metric("baseline_rmse", base_rmse)
        mlflow.log_metric("baseline_mae", base_mae)
        mlflow.keras.log_model(model, "lstm_rul_model")
        mlflow.sklearn.log_model(baseline, "rf_rul_baseline")

        scaler_path = "scaler_gru.joblib"
        joblib.dump(scaler, scaler_path)
        mlflow.log_artifact(scaler_path, "scaler")
        os.remove(scaler_path)
        print(f"[ML] Scaler sauvegardé dans MLflow")

        print(f"\n{'='*40}")
        print(f"GRU      - RMSE: {rmse:.2f}, MAE: {mae:.2f}")
        print(f"RF (base)- RMSE: {base_rmse:.2f}, MAE: {base_mae:.2f}")
        print(f"{'='*40}")
        if rmse < base_rmse:
            print(f"GRU meilleur de {(1 - rmse / base_rmse) * 100:.1f}%")
        else:
            print(f"RF meilleur de {(1 - base_rmse / rmse) * 100:.1f}%")
        print(f"Run MLflow: {mlflow.active_run().info.run_id}")


if __name__ == "__main__":
    train()
