import numpy as np


class HealthScoreCalculator:
    """
    Calcule un Health Score de 0 (critique) à 100 (excellent).

    Formule:
      anomaly_component = 100 * (1 - anomaly_score_normalisé)
      rul_component = min(rul_predicted / rul_max, 1) * 100
      health_score = 0.6 * anomaly_component + 0.4 * rul_component

    Poids: 60% anomaly, 40% RUL — car la détection temps réel
    est plus immédiate pour l'opérateur que la prédiction long-terme.
    """

    RUL_MAX = 300

    def compute(self, anomaly_score, rul_prediction):
        anomaly_norm = 1 / (1 + np.exp(-anomaly_score / 10))
        anomaly_component = 100 * (1 - anomaly_norm)
        anomaly_component = max(0, min(100, anomaly_component))

        rul_ratio = min(rul_prediction / self.RUL_MAX, 1)
        rul_component = rul_ratio * 100

        health_score = 0.6 * anomaly_component + 0.4 * rul_component
        health_score = round(max(0, min(100, health_score)), 1)

        if health_score >= 70:
            status = "normal"
        elif health_score >= 40:
            status = "warning"
        else:
            status = "critical"

        return {
            "anomaly_score": round(anomaly_score, 4),
            "rul_prediction": round(rul_prediction, 2),
            "health_score": health_score,
            "status": status,
        }


def test_degradation():
    calc = HealthScoreCalculator()
    print("=== Test de dégradation progressive ===")
    for step in range(10):
        anomaly = -5 + step * 2
        rul = 200 - step * 20
        result = calc.compute(anomaly, rul)
        print(f"Etape {step}: anomaly={anomaly:.1f}, rul={rul:.0f} -> "
              f"health={result['health_score']}, status={result['status']}")


if __name__ == "__main__":
    test_degradation()
