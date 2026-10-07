import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sensor_simulator import SensorSimulator

sim = SensorSimulator()
records = []

for _ in range(100):
    for mid in sim.machine_ids:
        records.append(sim.generate_reading(mid))

df = pd.DataFrame(records)

fig, axes = plt.subplots(4, 1, figsize=(12, 10), sharex=True)
sensors = ["temperature", "vibration", "pressure", "courant_moteur"]
colors = ["red", "blue", "green", "orange"]

for ax, sensor, color in zip(axes, sensors, colors):
    for mid in sim.machine_ids:
        subset = df[df["machine_id"] == mid]
        ax.plot(subset.index, subset[sensor], label=mid, alpha=0.7, color=color)
    anomalies = df[df["_is_anomaly_ground_truth"] == True]
    ax.scatter(anomalies.index, anomalies[sensor], color="black", s=50, zorder=5, label="Anomalie")
    ax.set_ylabel(sensor.replace("_", " ").title())
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)

plt.suptitle("Donnees capteurs simulees - Anomalies en noir", fontsize=14)
plt.tight_layout()
output_path = os.path.join(os.path.dirname(__file__), "..", "data", "simulator_plot.png")
plt.savefig(output_path)
print(f"Graphique sauvegardé: {output_path}")
