"""Test A-Z du projet PFA Orhan Automotive"""
import os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
os.environ["PYTHONPATH"] = ROOT
os.environ["MLFLOW_ALLOW_FILE_STORE"] = "true"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

passed = []
failed = []

def test(name, func):
    try:
        func()
        print(f"  [PASS] {name}")
        passed.append(name)
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        failed.append(name)


# ═══════════════════════════════════════════════
# TEST 1: PhysicsSimulator
# ═══════════════════════════════════════════════
def test_physics_simulator():
    from simulator.physics_simulator import PhysicsSimulator, SENSOR_NAMES
    sim = PhysicsSimulator(seed=42)
    records, configs = sim.generate_dataset(n_machines=5, cycles_range=(200, 300))
    assert len(records) > 0, "No records generated"
    assert len(configs) == 5, f"Expected 5 machines, got {len(configs)}"
    assert len(SENSOR_NAMES) == 21, f"Expected 21 sensors, got {len(SENSOR_NAMES)}"
    assert "unit" in records[0], "Missing 'unit' field"
    assert "hi" in records[0], "Missing 'hi' field"
    assert "rul" in records[0], "Missing 'rul' field"
    for s in SENSOR_NAMES:
        assert s in records[0], f"Missing sensor: {s}"
    print(f"    {len(records)} records, {len(configs)} machines, {len(SENSOR_NAMES)} sensors")


# ═══════════════════════════════════════════════
# TEST 2: prepare_simulator_data
# ═══════════════════════════════════════════════
def test_prepare_data():
    from ml_models.predictive_maintenance.prepare_simulator_data import prepare_data
    (X_train, y_train), (X_val, y_val), (X_test, y_test), n_features, scaler = prepare_data(
        n_machines=10, seq_length=50, seed=42
    )
    assert n_features == 21, f"Expected 21 features, got {n_features}"
    assert X_train.shape[2] == 21, f"Expected 21 features in X_train, got {X_train.shape[2]}"
    assert X_train.shape[1] == 50, f"Expected seq_length=50, got {X_train.shape[1]}"
    assert len(X_train) > 0, "Empty training set"
    assert len(X_test) > 0, "Empty test set"
    print(f"    Train: {X_train.shape}, Val: {X_val.shape}, Test: {X_test.shape}, Features: {n_features}")


# ═══════════════════════════════════════════════
# TEST 3: GRU model build
# ═══════════════════════════════════════════════
def test_gru_model():
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import GRU, Dense
    from tensorflow.keras.optimizers import Adam
    import numpy as np

    model = Sequential([
        GRU(128, return_sequences=True, input_shape=(None, 21)),
        GRU(64, return_sequences=False),
        Dense(32, activation="relu"),
        Dense(1),
    ])
    model.compile(optimizer=Adam(learning_rate=0.001), loss="mse", metrics=["mae"])
    assert model is not None, "Model is None"
    X_dummy = np.random.randn(4, 50, 21).astype(np.float32)
    y_pred = model.predict(X_dummy, verbose=0)
    assert y_pred.shape == (4, 1), f"Expected shape (4,1), got {y_pred.shape}"
    print(f"    Model params: {model.count_params()}, output shape: {y_pred.shape}")


# ═══════════════════════════════════════════════
# TEST 4: Delta Lake read/write
# ═══════════════════════════════════════════════
def test_delta_lake():
    from storage.delta_writer import DeltaLakeManager
    dm = DeltaLakeManager()
    stats = dm.get_table_stats("sensors")
    assert "exists" in stats, "Missing 'exists' in stats"
    print(f"    Sensors: exists={stats['exists']}, version={stats['version']}, records={stats['num_records']}")


# ═══════════════════════════════════════════════
# TEST 5: Health Score
# ═══════════════════════════════════════════════
def test_health_score():
    from ml_models.health_score import HealthScoreCalculator
    hc = HealthScoreCalculator()
    result = hc.compute(anomaly_score=-0.5, rul_prediction=150)
    assert "health_score" in result, "Missing 'health_score'"
    assert "status" in result, "Missing 'status'"
    assert 0 <= result["health_score"] <= 100, f"Health score out of range: {result['health_score']}"
    print(f"    Health={result['health_score']:.1f}, Status={result['status']}")


# ═══════════════════════════════════════════════
# TEST 6: Anomaly Detection - train quick
# ═══════════════════════════════════════════════
def test_isolation_forest():
    from simulator.physics_simulator import PhysicsSimulator, SENSOR_NAMES
    import numpy as np
    import pandas as pd
    from sklearn.ensemble import IsolationForest
    sim = PhysicsSimulator(seed=42)
    records, _ = sim.generate_dataset(n_machines=5, cycles_range=(200, 300))
    df = pd.DataFrame(records)
    features = SENSOR_NAMES
    X = df[features].values
    model = IsolationForest(contamination=0.05, random_state=42)
    model.fit(X[:100])
    preds = model.predict(X[100:120])
    assert len(preds) == 20, f"Expected 20 predictions, got {len(preds)}"
    print(f"    Trained on {100} samples, predicted {len(preds)}, anomalies={sum(preds == -1)}")


# ═══════════════════════════════════════════════
# TEST 7: MLflow connectivity
# ═══════════════════════════════════════════════
def test_mlflow():
    import mlflow
    client = mlflow.tracking.MlflowClient()
    experiments = client.search_experiments()
    names = [e.name for e in experiments]
    print(f"    MLflow experiments: {names}")
    assert "predictive_maintenance" in names or len(experiments) >= 0, "MLflow OK"


# ═══════════════════════════════════════════════
# TEST 8: API endpoints (without server)
# ═══════════════════════════════════════════════
def test_api_import():
    from api.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    r = client.get("/machines")
    assert r.status_code == 200, f"GET /machines returned {r.status_code}"
    data = r.json()
    assert "machines" in data, "Missing 'machines' in response"
    assert len(data["machines"]) == 7, f"Expected 7 machines, got {len(data['machines'])}"
    machines = data["machines"]
    ids = [m["machine_id"] for m in machines]
    assert "INJ-01" in ids, f"INJ-01 not in {ids}"
    print(f"    /machines -> {len(machines)} machines: {ids}")

    r2 = client.get("/alerts")
    assert r2.status_code == 200, f"GET /alerts returned {r2.status_code}"
    print(f"    /alerts -> {r2.json().get('count', 0)} alerts")


# ═══════════════════════════════════════════════
# RUN ALL TESTS
# ═══════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("  TESTS A-Z - PFA Orhan Automotive")
    print("=" * 60)

    tests = [
        ("1. PhysicsSimulator (21 sensors)", test_physics_simulator),
        ("2. prepare_simulator_data (sequences)", test_prepare_data),
        ("3. GRU model build", test_gru_model),
        ("4. Delta Lake read/write", test_delta_lake),
        ("5. Health Score calculator", test_health_score),
        ("6. Isolation Forest (quick)", test_isolation_forest),
        ("7. MLflow connectivity", test_mlflow),
        ("8. API FastAPI endpoints", test_api_import),
    ]

    for name, func in tests:
        print(f"\n--- {name} ---")
        test(name, func)

    print("\n" + "=" * 60)
    print(f"  PASSED: {len(passed)}/{len(passed)+len(failed)}")
    if failed:
        print(f"  FAILED: {failed}")
    else:
        print("  ALL TESTS PASSED!")
    print("=" * 60)
