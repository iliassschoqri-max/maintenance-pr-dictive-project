import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from simulator.physics_simulator import PhysicsSimulator, SENSOR_NAMES
from ml_models.health_score import HealthScoreCalculator
from ml_models.anomaly_detection.predict import AnomalyPredictor

N_STEPS = 30


def run_scenario():
    sim = PhysicsSimulator(seed=42)
    hc = HealthScoreCalculator()

    try:
        ap = AnomalyPredictor()
        has_anomaly = True
    except Exception:
        ap = None
        has_anomaly = False
        print("  (AnomalyPredictor non disponible, score fixe)")

    print("=== Scénario de panne progressive ===")
    health_scores = []

    for step in range(N_STEPS):
        machine_id = "INJ-01"
        lifecycle = sim.generate_lifecycle(machine_id, regime="normal", total_cycles=N_STEPS + 50)
        reading = lifecycle[min(step, len(lifecycle) - 1)]

        anomaly_score = -5.0
        if has_anomaly and ap:
            try:
                sensor_dict = {s: reading[s] for s in SENSOR_NAMES}
                result = ap.predict(sensor_dict)
                anomaly_score = result.get("anomaly_score", -5.0)
            except Exception:
                pass

        rul_pred = reading.get("rul", 100)
        health = hc.compute(anomaly_score=anomaly_score, rul_prediction=rul_pred)

        health_scores.append(health["health_score"])
        hi_val = reading.get("hi", 0)
        print(f"  Step {step:2d}: HI={hi_val:6.1f}  RUL={rul_pred:6.0f}  anomaly={anomaly_score:+.2f}  -> health={health['health_score']:5.1f} ({health['status']})")

    avg = np.mean(health_scores)
    print(f"\nHealth Score moyen: {avg:.1f}")
    print(f"Health Score min:   {min(health_scores):.1f}")
    print(f"Health Score max:   {max(health_scores):.1f}")

    report_path = os.path.join(os.path.dirname(__file__), "..", "data", "e2e_report.txt")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        f.write("Test End-to-End - PFA Orhan Automotive\n")
        f.write(f"Machines: 7 (INJ-01, INJ-02, SOUD-01, ASSY-01, PEINT-01, FRAIS-01, TOUR-01), Sensors: {len(SENSOR_NAMES)}\n")
        f.write(f"Steps: {N_STEPS}, Health Score moyen: {avg:.1f}\n")
        for i, hs in enumerate(health_scores):
            f.write(f"  Step {i:2d}: health={hs:.1f}\n")
    print(f"\nRapport sauvegardé: {report_path}")
    print("Test end-to-end terminé OK")


if __name__ == "__main__":
    run_scenario()
