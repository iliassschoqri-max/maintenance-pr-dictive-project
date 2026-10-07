import mlflow
import numpy as np

SENSORS = [
    "temperature_bearing", "temperature_motor", "temperature_hydraulic",
    "temperature_ambient", "vibration_axial", "vibration_radial",
    "vibration_vertical", "pressure_hydraulic", "pressure_pneumatic",
    "pressure_lubrication", "current_motor", "current_servo",
    "rpm_spindle", "rpm_fan", "torque_output", "power_consumption",
    "acoustic_emission", "oil_particle_count", "coolant_flow",
    "electrical_resistance", "displacement_linear",
]
FEATURES = (
    [f"{s}_mean" for s in SENSORS]
    + [f"{s}_std" for s in SENSORS]
    + [f"{s}_min" for s in SENSORS]
    + [f"{s}_max" for s in SENSORS]
    + ["vibration_rms"]
)


class AnomalyPredictor:
    def __init__(self, run_id=None):
        client = mlflow.tracking.MlflowClient()
        if run_id:
            self.run_id = run_id
        else:
            experiment = client.get_experiment_by_name("anomaly_detection")
            runs = client.search_runs(experiment.experiment_id, order_by=["start_time DESC"], max_results=1)
            if not runs:
                raise ValueError("Aucun modèle entraîné trouvé dans MLflow")
            self.run_id = runs[0].info.run_id

        self.pipeline = mlflow.sklearn.load_model(f"runs:/{self.run_id}/isolation_forest_model")

    def predict(self, features_dict):
        values = [features_dict.get(f, 0) for f in FEATURES]
        X = np.array(values).reshape(1, -1)
        pred = self.pipeline.predict(X)
        score = self.pipeline.decision_function(X)[0]
        is_anomaly = pred[0] == -1
        return {
            "is_anomaly": bool(is_anomaly),
            "anomaly_score": float(round(score, 4)),
        }
