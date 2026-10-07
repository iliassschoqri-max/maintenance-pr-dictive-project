"""Test rapide apres ajout de 2 machines (FRAIS-01, TOUR-01) - sans TensorFlow"""
import os, sys

ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, ROOT)
os.environ["MLFLOW_ALLOW_FILE_STORE"] = "true"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

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


def test_physics_simulator_7_machines():
    from simulator.physics_simulator import PhysicsSimulator, SENSOR_NAMES
    sim = PhysicsSimulator(seed=42)
    assert len(sim.machine_ids) == 7, "Expected 7 machines"
    assert "FRAIS-01" in sim.machine_ids
    assert "TOUR-01" in sim.machine_ids
    records, configs = sim.generate_dataset(n_machines=7, cycles_range=(200, 300))
    assert len(records) > 0
    assert len(configs) == 7
    ids = [c["machine_id"] for c in configs]
    assert "FRAIS-01" in ids
    assert "TOUR-01" in ids
    print(f"    {len(records)} records, {len(configs)} machines, {len(SENSOR_NAMES)} sensors")
    print(f"    IDs: {ids}")


def test_sensor_simulator_7_machines():
    from simulator.sensor_simulator import SensorSimulator
    sim = SensorSimulator()
    assert len(sim.machine_ids) == 7
    assert "FRAIS-01" in sim.machine_ids
    assert "TOUR-01" in sim.machine_ids
    for mid in sim.machine_ids:
        reading = sim.generate_reading(mid)
        assert reading["machine_id"] == mid
    print(f"    {len(sim.machine_ids)} machines OK")


def test_api_7_machines():
    from api.main import app, MACHINES
    assert len(MACHINES) == 7
    assert "FRAIS-01" in MACHINES
    assert "TOUR-01" in MACHINES
    assert MACHINES["FRAIS-01"]["type"] == "fraisage_cnc"
    assert MACHINES["TOUR-01"]["type"] == "tour_cnc"
    from fastapi.testclient import TestClient
    client = TestClient(app)
    r = client.get("/machines")
    assert r.status_code == 200
    data = r.json()
    assert len(data["machines"]) == 7
    ids = [m["machine_id"] for m in data["machines"]]
    assert "FRAIS-01" in ids
    assert "TOUR-01" in ids
    print(f"    /machines -> {len(data['machines'])} machines: {ids}")


def test_health_score():
    from ml_models.health_score import HealthScoreCalculator
    hc = HealthScoreCalculator()
    r1 = hc.compute(anomaly_score=-0.5, rul_prediction=150)
    r2 = hc.compute(anomaly_score=2.0, rul_prediction=30)
    assert 0 <= r1["health_score"] <= 100
    assert r2["health_score"] < r1["health_score"]
    print(f"    normal={r1['health_score']}, degraded={r2['health_score']}")


def test_full_lifecycle_all_7():
    from simulator.physics_simulator import PhysicsSimulator, SENSOR_NAMES
    sim = PhysicsSimulator(seed=42)
    for mid in sim.machine_ids:
        lifecycle = sim.generate_lifecycle(mid, regime="normal", total_cycles=50)
        assert len(lifecycle) == 50
        assert lifecycle[0]["hi"] > lifecycle[-1]["hi"]
        for s in SENSOR_NAMES:
            assert s in lifecycle[0]
    print(f"    All {len(sim.machine_ids)} lifecycles OK")


def test_delta_lake():
    from storage.delta_writer import DeltaLakeManager
    dm = DeltaLakeManager()
    stats = dm.get_table_stats("sensors")
    assert "exists" in stats
    print(f"    Sensors: exists={stats['exists']}, version={stats['version']}")


def test_anomaly_detection_quick():
    from simulator.physics_simulator import PhysicsSimulator, SENSOR_NAMES
    import numpy as np
    import pandas as pd
    from sklearn.ensemble import IsolationForest
    sim = PhysicsSimulator(seed=42)
    records, _ = sim.generate_dataset(n_machines=7, cycles_range=(200, 300))
    df = pd.DataFrame(records)
    X = df[SENSOR_NAMES].values
    model = IsolationForest(contamination=0.05, random_state=42)
    model.fit(X[:100])
    preds = model.predict(X[100:120])
    assert len(preds) == 20
    print(f"    Trained on 100, predicted {len(preds)}, anomalies={sum(preds == -1)}")


def test_api_endpoints():
    from api.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    endpoints = [
        "/machines",
        "/alerts",
        "/machine/FRAIS-01/health",
        "/machine/TOUR-01/health",
        "/machine/INJ-01/health",
        "/stats/model-performance",
        "/delta/stats",
        "/report/csv?type=summary",
    ]
    for ep in endpoints:
        r = client.get(ep)
        assert r.status_code == 200, f"{ep} returned {r.status_code}"
    print(f"    {len(endpoints)} endpoints OK")


def test_mlflow():
    import mlflow
    client = mlflow.tracking.MlflowClient()
    experiments = client.search_experiments()
    names = [e.name for e in experiments]
    print(f"    MLflow experiments: {names}")


if __name__ == "__main__":
    print("=" * 60)
    print("  TESTS RAPIDES - Apres ajout FRAIS-01 + TOUR-01")
    print("=" * 60)

    tests = [
        ("1. PhysicsSimulator (7 machines)", test_physics_simulator_7_machines),
        ("2. SensorSimulator (7 machines)", test_sensor_simulator_7_machines),
        ("3. API MACHINES dict", test_api_7_machines),
        ("4. Health Score", test_health_score),
        ("5. Full lifecycle (7 machines)", test_full_lifecycle_all_7),
        ("6. Delta Lake", test_delta_lake),
        ("7. Isolation Forest (quick)", test_anomaly_detection_quick),
        ("8. API endpoints (8 endpoints)", test_api_endpoints),
        ("9. MLflow", test_mlflow),
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
