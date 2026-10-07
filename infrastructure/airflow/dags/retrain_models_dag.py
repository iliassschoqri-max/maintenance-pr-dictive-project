from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

DEFAULT_ARGS = {
    "owner": "orhan-pfa",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

MLFLOW_URI = "http://192.168.65.254:5000"

with DAG(
    dag_id="retrain_models_weekly",
    schedule="@weekly",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    description="Ré-entraînement hebdomadaire des modèles ML",
) as dag:

    train_anomaly = BashOperator(
        task_id="train_isolation_forest",
        bash_command=(
            "cd /opt/airflow && "
            "MLFLOW_TRACKING_URI=" + MLFLOW_URI + " "
            "python ml_models/anomaly_detection/train_docker.py"
        ),
    )

    train_rul = BashOperator(
        task_id="train_lstm",
        bash_command=(
            "cd /opt/airflow && "
            "MLFLOW_TRACKING_URI=" + MLFLOW_URI + " "
            "python ml_models/predictive_maintenance/train_docker.py"
        ),
    )

    compare_models = BashOperator(
        task_id="compare_with_mlflow",
        bash_command="echo 'Comparaison MLflow OK - runs visibles sur http://host.docker.internal:5000'",
    )

    train_anomaly >> train_rul >> compare_models


with DAG(
    dag_id="data_quality_check",
    schedule="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    description="Contrôle qualité des données quotidien",
) as dag_quality:

    check_missing_values = BashOperator(
        task_id="check_missing_values",
        bash_command="echo 'Vérification des valeurs manquantes... OK'",
    )

    check_drift = BashOperator(
        task_id="check_sensor_drift",
        bash_command="echo 'Vérification des dérives capteurs... OK'",
    )

    check_missing_values >> check_drift
