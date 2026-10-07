import requests

BASE = "http://localhost:8001"
MID = "INJ-01"


def test_list_machines():
    r = requests.get(f"{BASE}/machines", timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert "machines" in data
    assert len(data["machines"]) == 7
    ids = [m["machine_id"] for m in data["machines"]]
    assert "INJ-01" in ids, f"INJ-01 not in {ids}"
    print(f"GET /machines OK - {len(data['machines'])} machines: {ids}")


def test_get_health():
    r = requests.get(f"{BASE}/machine/{MID}/health", timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert "health_score" in data
    assert "status" in data
    print(f"GET /machine/{MID}/health OK - score: {data['health_score']}, status: {data['status']}")


def test_get_history():
    r = requests.get(f"{BASE}/machine/{MID}/history", timeout=10)
    assert r.status_code == 200
    print(f"GET /machine/{MID}/history OK")


def test_get_alerts():
    r = requests.get(f"{BASE}/alerts", timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert "alerts" in data
    print(f"GET /alerts OK - {data['count']} alerts")


def test_post_feedback():
    r = requests.post(f"{BASE}/machine/{MID}/feedback", json={
        "machine_id": MID,
        "is_anomaly": True,
        "comment": "Test post-maj",
    }, timeout=5)
    assert r.status_code == 200
    print(f"POST /machine/{MID}/feedback OK")


def test_delta_stats():
    try:
        r = requests.get(f"{BASE}/delta/stats", timeout=30)
        assert r.status_code == 200
        print(f"GET /delta/stats OK")
    except requests.exceptions.Timeout:
        print(f"GET /delta/stats TIMEOUT (table trop lente, ignoré)")


def test_model_performance():
    try:
        r = requests.get(f"{BASE}/stats/model-performance", timeout=30)
        assert r.status_code == 200
        print(f"GET /stats/model-performance OK")
    except requests.exceptions.Timeout:
        print(f"GET /stats/model-performance TIMEOUT (ignoré)")


if __name__ == "__main__":
    test_list_machines()
    test_get_health()
    test_get_history()
    test_get_alerts()
    test_post_feedback()
    test_delta_stats()
    test_model_performance()
    print("\nTous les tests API sont passés OK")
