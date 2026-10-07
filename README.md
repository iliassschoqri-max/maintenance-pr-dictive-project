# Détection d'Anomalies & Maintenance Prédictive — PFA Orhan Automotive

Pipeline Big Data + Machine Learning pour la maintenance prédictive des équipements de production industrielle.

## Architecture

```
Simulateur Python 
    → Apache Kafka (streaming)
    → Python (kafka-python + pandas, fenêtrage glissant)
    → Delta Lake (historique) + InfluxDB (temps réel)
    → Isolation Forest (anomalies) + LSTM (RUL)
    → Health Score
    → API FastAPI
    → Dashboard Web + Grafana
    → Feedback Loop → ré-entraînement
    → Orchestration Airflow
```

## Structure du projet

```
pfa-orhan-project/
├── simulator/          # Simulateur de données capteurs
├── kafka_scripts_backup/# Configuration et scripts Kafka (backup)
├── processing/         # Nettoyage et feature engineering
├── storage/            # Configuration stockage (Delta Lake, InfluxDB)
├── ml_models/          # Modèles ML (Isolation Forest, LSTM)
│   ├── anomaly_detection/
│   └── predictive_maintenance/
├── api/                # API FastAPI
├── dashboard/          # Configuration Grafana
├── airflow/            # DAGs Airflow
├── data/               # Datasets (NASA Turbofan)
├── docs/               # Documentation
├── tests/              # Tests d'intégration
├── docker-compose.yml  # Orchestration des services
└── requirements.txt    # Dépendances Python
```

## Lancement rapide

```bash
# 1. Créer l'environnement virtuel
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Lancer les services Docker
docker-compose up -d

# 4. Lancer le simulateur (mode test)
python simulator/sensor_simulator.py

# 5. Lancer l'API
uvicorn api.main:app --reload
```

## Perspectives d'industrialisation

| Composant | Actuel (stage) | Cible production |
|-----------|----------------|------------------|
| **Traitement streaming** | Python (kafka-python + pandas) | PySpark Structured Streaming |
| **Stockage Delta Lake** | delta-rs (local) | MinIO / S3 avec delta-rs |
| **MLflow** | Tracking local | MLflow server centralisé |
| **Orchestration** | Airflow LocalExecutor | Airflow CeleryExecutor + workers |

## Documentation

- [Architecture détaillée](docs/architecture.md)
- [Guide d'installation](docs/setup.md)

## Étapes du projet

| Étape | Description |
|-------|-------------|
| 0 | Setup du projet |
| 1 | Simulateur de données capteurs |
| 2 | Ingestion Kafka |
| 3 | Traitement des données |
| 4 | Détection d'anomalies (Isolation Forest) |
| 5 | Maintenance prédictive (LSTM) |
| 6 | Health Score |
| 7 | API FastAPI |
| 8 | Dashboard Grafana |
| 9 | Orchestration Airflow |
| 10 | Tests d'intégration |
| 11 | Documentation finale |
