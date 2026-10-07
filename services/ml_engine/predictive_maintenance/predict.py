import os

import joblib
import mlflow
import numpy as np


class RULPredictor:
    def __init__(self, run_id=None):
        self.scaler = None
        self.model = None

        client = mlflow.tracking.MlflowClient()
        if run_id:
            self.run_id = run_id
            self._load_from_run(client, run_id)
        else:
            self._find_best_run(client)

        if self.model is None:
            self._load_fallback()

    def _find_best_run(self, client):
        experiment = client.get_experiment_by_name("predictive_maintenance")
        if not experiment:
            raise ValueError("Experiment 'predictive_maintenance' non trouve")

        runs = client.search_runs(
            experiment.experiment_id,
            order_by=["start_time DESC"],
            max_results=20,
        )

        for run in runs:
            rid = run.info.run_id
            try:
                client.download_artifacts(rid, "lstm_rul_model", "/tmp/_mlflow_check")
                self.run_id = rid
                self._load_from_run(client, rid)
                if self.model is not None:
                    print(f"[ML] Run valide trouve: {rid}")
                    return
            except Exception:
                continue

        raise ValueError("Aucun run avec modele LSTM valide")

    def _load_from_run(self, client, run_id):
        self.run_id = run_id
        try:
            self.model = mlflow.keras.load_model(f"runs:/{run_id}/lstm_rul_model")
        except Exception:
            try:
                self.model = mlflow.tensorflow.load_model(f"runs:/{run_id}/lstm_rul_model")
            except Exception as e:
                print(f"[ML] Model non charge depuis run {run_id}: {e}")
                self.model = None

        try:
            local_path = client.download_artifacts(run_id, "scaler/scaler_gru.joblib")
            self.scaler = joblib.load(local_path)
        except Exception:
            self.scaler = None

    def _load_fallback(self):
        import glob as globmod
        import tensorflow as tf

        models_dir = os.path.join(os.path.dirname(__file__), "..", "..", "mlruns", "1")
        keras_files = globmod.glob(
            os.path.join(models_dir, "**", "lstm_rul_model", "data", "model", "saved_model.pb"),
            recursive=True,
        )
        if keras_files:
            model_dir = os.path.dirname(keras_files[-1])
            try:
                self.model = tf.keras.models.load_model(model_dir)
                print(f"[ML] Fallback: modele charge depuis {model_dir}")
            except Exception as e:
                print(f"[ML] Fallback echoue: {e}")

        scaler_files = globmod.glob(
            os.path.join(models_dir, "**", "scaler_gru.joblib"),
            recursive=True,
        )
        if scaler_files and self.scaler is None:
            self.scaler = joblib.load(scaler_files[-1])
            print(f"[ML] Fallback: scaler charge depuis {scaler_files[-1]}")

    def predict(self, sequence):
        seq = np.array(sequence)
        if self.scaler is not None:
            orig_shape = seq.shape
            seq = self.scaler.transform(seq.reshape(-1, orig_shape[-1])).reshape(orig_shape)
        seq = seq.reshape(1, *seq.shape)
        rul = float(self.model.predict(seq, verbose=0)[0, 0])
        return {"rul_prediction": round(max(rul, 0), 2)}
