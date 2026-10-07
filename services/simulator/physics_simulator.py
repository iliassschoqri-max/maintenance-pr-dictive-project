"""
Physics-Based Digital Twin Simulator for Predictive Maintenance.

Génère des données de capteurs industriels réalistes avec :
- 21 capteurs physiques (température, vibration, pression, courant, etc.)
- Health Index (HI) dégradant de 100% à 0%
- RUL (Remaining Useful Life) ground truth calculé depuis le HI
- 4 régimes de dégradation (normal, accéléré, step, intermittent)
- Noise réaliste et corrélation inter-capteurs
"""
import json
import math
import random
import time
from datetime import datetime, timezone

import numpy as np


N_SENSORS = 21

SENSOR_NAMES = [
    "temperature_bearing", "temperature_motor", "temperature_hydraulic",
    "temperature_ambient", "vibration_axial", "vibration_radial",
    "vibration_vertical", "pressure_hydraulic", "pressure_pneumatic",
    "pressure_lubrication", "current_motor", "current_servo",
    "rpm_spindle", "rpm_fan", "torque_output", "power_consumption",
    "acoustic_emission", "oil_particle_count", "coolant_flow",
    "electrical_resistance", "displacement_linear",
]

DEGRADATION_REGIMES = ["normal", "accelerated", "step", "intermittent"]

MACHINE_PROFILES = {
    "INJ-01": {
        "type": "injection_plastique",
        "sensor_baselines": {
            "temperature_bearing": 65.0, "temperature_motor": 72.0,
            "temperature_hydraulic": 55.0, "temperature_ambient": 25.0,
            "vibration_axial": 0.032, "vibration_radial": 0.028,
            "vibration_vertical": 0.025, "pressure_hydraulic": 5.0,
            "pressure_pneumatic": 3.2, "pressure_lubrication": 2.1,
            "current_motor": 12.5, "current_servo": 3.8,
            "rpm_spindle": 1450.0, "rpm_fan": 880.0,
            "torque_output": 45.0, "power_consumption": 3.2,
            "acoustic_emission": 42.0, "oil_particle_count": 15.0,
            "coolant_flow": 8.5, "electrical_resistance": 0.12,
            "displacement_linear": 0.05,
        },
        "sensor_noise_pct": 0.02,
        "degradation_sensitivity": {
            "temperature_bearing": 0.35, "vibration_axial": 0.30,
            "vibration_radial": 0.25, "oil_particle_count": 0.20,
            "current_motor": 0.15, "acoustic_emission": 0.10,
            "pressure_lubrication": 0.12, "electrical_resistance": 0.08,
        },
    },
    "INJ-02": {
        "type": "injection_plastique",
        "sensor_baselines": {
            "temperature_bearing": 68.0, "temperature_motor": 75.0,
            "temperature_hydraulic": 58.0, "temperature_ambient": 25.0,
            "vibration_axial": 0.035, "vibration_radial": 0.030,
            "vibration_vertical": 0.027, "pressure_hydraulic": 5.2,
            "pressure_pneumatic": 3.4, "pressure_lubrication": 2.2,
            "current_motor": 13.0, "current_servo": 4.0,
            "rpm_spindle": 1480.0, "rpm_fan": 900.0,
            "torque_output": 47.0, "power_consumption": 3.4,
            "acoustic_emission": 44.0, "oil_particle_count": 18.0,
            "coolant_flow": 8.2, "electrical_resistance": 0.13,
            "displacement_linear": 0.055,
        },
        "sensor_noise_pct": 0.025,
        "degradation_sensitivity": {
            "temperature_bearing": 0.33, "vibration_axial": 0.28,
            "vibration_radial": 0.24, "oil_particle_count": 0.22,
            "current_motor": 0.18, "acoustic_emission": 0.12,
            "pressure_lubrication": 0.14, "electrical_resistance": 0.09,
        },
    },
    "SOUD-01": {
        "type": "soudure",
        "sensor_baselines": {
            "temperature_bearing": 60.0, "temperature_motor": 68.0,
            "temperature_hydraulic": 50.0, "temperature_ambient": 25.0,
            "vibration_axial": 0.040, "vibration_radial": 0.035,
            "vibration_vertical": 0.032, "pressure_hydraulic": 4.5,
            "pressure_pneumatic": 3.0, "pressure_lubrication": 1.8,
            "current_motor": 14.0, "current_servo": 5.2,
            "rpm_spindle": 1200.0, "rpm_fan": 750.0,
            "torque_output": 52.0, "power_consumption": 4.1,
            "acoustic_emission": 55.0, "oil_particle_count": 12.0,
            "coolant_flow": 6.0, "electrical_resistance": 0.10,
            "displacement_linear": 0.045,
        },
        "sensor_noise_pct": 0.03,
        "degradation_sensitivity": {
            "temperature_bearing": 0.30, "vibration_axial": 0.35,
            "vibration_radial": 0.30, "oil_particle_count": 0.18,
            "current_motor": 0.25, "acoustic_emission": 0.15,
            "pressure_lubrication": 0.10, "electrical_resistance": 0.12,
        },
    },
    "ASSY-01": {
        "type": "assemblage",
        "sensor_baselines": {
            "temperature_bearing": 58.0, "temperature_motor": 65.0,
            "temperature_hydraulic": 48.0, "temperature_ambient": 25.0,
            "vibration_axial": 0.045, "vibration_radial": 0.040,
            "vibration_vertical": 0.038, "pressure_hydraulic": 4.8,
            "pressure_pneumatic": 3.5, "pressure_lubrication": 2.0,
            "current_motor": 11.0, "current_servo": 3.5,
            "rpm_spindle": 1600.0, "rpm_fan": 950.0,
            "torque_output": 38.0, "power_consumption": 2.8,
            "acoustic_emission": 48.0, "oil_particle_count": 10.0,
            "coolant_flow": 9.0, "electrical_resistance": 0.11,
            "displacement_linear": 0.06,
        },
        "sensor_noise_pct": 0.02,
        "degradation_sensitivity": {
            "temperature_bearing": 0.28, "vibration_axial": 0.40,
            "vibration_radial": 0.35, "oil_particle_count": 0.15,
            "current_motor": 0.20, "acoustic_emission": 0.18,
            "pressure_lubrication": 0.12, "electrical_resistance": 0.07,
        },
    },
    "PEINT-01": {
        "type": "peinture",
        "sensor_baselines": {
            "temperature_bearing": 70.0, "temperature_motor": 78.0,
            "temperature_hydraulic": 60.0, "temperature_ambient": 25.0,
            "vibration_axial": 0.025, "vibration_radial": 0.022,
            "vibration_vertical": 0.020, "pressure_hydraulic": 5.5,
            "pressure_pneumatic": 4.0, "pressure_lubrication": 2.5,
            "current_motor": 10.5, "current_servo": 3.2,
            "rpm_spindle": 1100.0, "rpm_fan": 700.0,
            "torque_output": 35.0, "power_consumption": 2.5,
            "acoustic_emission": 38.0, "oil_particle_count": 8.0,
            "coolant_flow": 10.0, "electrical_resistance": 0.14,
            "displacement_linear": 0.04,
        },
        "sensor_noise_pct": 0.018,
        "degradation_sensitivity": {
            "temperature_bearing": 0.38, "vibration_axial": 0.25,
            "vibration_radial": 0.20, "oil_particle_count": 0.25,
            "current_motor": 0.15, "acoustic_emission": 0.10,
            "pressure_lubrication": 0.15, "electrical_resistance": 0.10,
        },
    },
    "FRAIS-01": {
        "type": "fraisage_cnc",
        "sensor_baselines": {
            "temperature_bearing": 62.0, "temperature_motor": 70.0,
            "temperature_hydraulic": 52.0, "temperature_ambient": 24.0,
            "vibration_axial": 0.038, "vibration_radial": 0.033,
            "vibration_vertical": 0.030, "pressure_hydraulic": 6.0,
            "pressure_pneumatic": 3.8, "pressure_lubrication": 2.3,
            "current_motor": 15.0, "current_servo": 4.5,
            "rpm_spindle": 2200.0, "rpm_fan": 1100.0,
            "torque_output": 55.0, "power_consumption": 4.5,
            "acoustic_emission": 52.0, "oil_particle_count": 20.0,
            "coolant_flow": 12.0, "electrical_resistance": 0.11,
            "displacement_linear": 0.07,
        },
        "sensor_noise_pct": 0.022,
        "degradation_sensitivity": {
            "temperature_bearing": 0.32, "vibration_axial": 0.38,
            "vibration_radial": 0.33, "oil_particle_count": 0.22,
            "current_motor": 0.20, "acoustic_emission": 0.18,
            "pressure_lubrication": 0.14, "electrical_resistance": 0.10,
        },
    },
    "TOUR-01": {
        "type": "tour_cnc",
        "sensor_baselines": {
            "temperature_bearing": 58.0, "temperature_motor": 65.0,
            "temperature_hydraulic": 48.0, "temperature_ambient": 24.0,
            "vibration_axial": 0.030, "vibration_radial": 0.027,
            "vibration_vertical": 0.024, "pressure_hydraulic": 5.0,
            "pressure_pneumatic": 3.5, "pressure_lubrication": 2.0,
            "current_motor": 13.5, "current_servo": 4.0,
            "rpm_spindle": 1800.0, "rpm_fan": 950.0,
            "torque_output": 48.0, "power_consumption": 3.8,
            "acoustic_emission": 45.0, "oil_particle_count": 16.0,
            "coolant_flow": 9.5, "electrical_resistance": 0.12,
            "displacement_linear": 0.055,
        },
        "sensor_noise_pct": 0.02,
        "degradation_sensitivity": {
            "temperature_bearing": 0.34, "vibration_axial": 0.30,
            "vibration_radial": 0.28, "oil_particle_count": 0.20,
            "current_motor": 0.22, "acoustic_emission": 0.14,
            "pressure_lubrication": 0.12, "electrical_resistance": 0.09,
        },
    },
}


class HealthIndex:
    """Modélise la dégradation de l'état de santé d'une machine."""

    def __init__(self, initial_hi=100.0):
        self.hi = initial_hi
        self.initial_hi = initial_hi
        self.cycle = 0
        self.total_cycles = 0
        self.regime = "normal"
        self.step_faults = []
        self.intermittent_state = False
        self.intermittent_counter = 0

    def configure(self, regime, total_cycles, params=None):
        self.regime = regime
        self.total_cycles = total_cycles
        self.params = params or {}
        self.hi = self.initial_hi
        self.cycle = 0

        if regime == "step":
            n_faults = random.randint(1, 3)
            fault_cycles = sorted(random.sample(
                range(total_cycles // 3, total_cycles), n_faults
            ))
            fault_drops = [random.uniform(5, 15) for _ in range(n_faults)]
            self.step_faults = list(zip(fault_cycles, fault_drops))

    def step(self):
        if self.total_cycles == 0:
            return self.hi

        progress = self.cycle / self.total_cycles

        if self.regime == "normal":
            alpha = self.params.get("alpha", 0.005)
            noise = random.gauss(0, 0.3)
            self.hi = self.initial_hi - (self.initial_hi * alpha * self.cycle) + noise

        elif self.regime == "accelerated":
            beta = self.params.get("beta", 0.00005)
            noise = random.gauss(0, 0.5)
            self.hi = self.initial_hi * math.exp(-beta * self.cycle ** 2) + noise

        elif self.regime == "step":
            base_alpha = self.params.get("alpha", 0.002)
            self.hi = self.initial_hi - (self.initial_hi * base_alpha * self.cycle)
            for fault_cycle, drop in self.step_faults:
                if self.cycle >= fault_cycle:
                    self.hi -= drop
            noise = random.gauss(0, 0.4)
            self.hi += noise

        elif self.regime == "intermittent":
            alpha = self.params.get("alpha", 0.003)
            self.hi = self.initial_hi - (self.initial_hi * alpha * self.cycle)
            self.intermittent_counter += 1
            if self.intermittent_counter % 30 == 0:
                self.intermittent_state = not self.intermittent_state
            if self.intermittent_state:
                self.hi -= random.uniform(3, 8)
            noise = random.gauss(0, 0.6)
            self.hi += noise

        self.hi = max(0.0, min(self.initial_hi, self.hi))
        self.cycle += 1
        return self.hi

    def get_rul(self):
        if self.hi <= 0:
            return 0.0
        if self.total_cycles == 0:
            return 0.0
        remaining_pct = self.hi / self.initial_hi
        remaining_cycles = remaining_pct * self.total_cycles
        return round(max(0.0, remaining_cycles), 2)


class PhysicsSimulator:
    """Simulateur physique avec 21 capteurs et dégradation réaliste."""

    def __init__(self, seed=None):
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)
        self.machine_ids = list(MACHINE_PROFILES.keys())
        self._health_states = {}
        self._lifecycle_counters = {}

    def _init_machine(self, machine_id, regime=None, total_cycles=None):
        if regime is None:
            regime = random.choice(DEGRADATION_REGIMES)
        if total_cycles is None:
            total_cycles = random.randint(150, 350)

        hi = HealthIndex(100.0)
        params = {}
        if regime == "normal":
            params["alpha"] = random.uniform(0.003, 0.008)
        elif regime == "accelerated":
            params["beta"] = random.uniform(0.00003, 0.00008)
        elif regime == "step":
            params["alpha"] = random.uniform(0.001, 0.004)
        elif regime == "intermittent":
            params["alpha"] = random.uniform(0.002, 0.005)

        hi.configure(regime, total_cycles, params)
        self._health_states[machine_id] = hi
        self._lifecycle_counters[machine_id] = 0
        return hi

    def _compute_sensor_value(self, sensor_name, baseline, hi_value, noise_pct,
                              profile, prev_sensors=None):
        degradation_pct = 1.0 - (hi_value / 100.0)
        sensitivity = profile.get("degradation_sensitivity", {}).get(sensor_name, 0.0)
        degradation_effect = degradation_pct * sensitivity * baseline

        if "temperature" in sensor_name:
            value = baseline + degradation_effect * 2.5
            if prev_sensors and "temperature_bearing" in prev_sensors:
                bearing_temp = prev_sensors["temperature_bearing"]
                if "motor" in sensor_name:
                    value += (bearing_temp - profile["sensor_baselines"]["temperature_bearing"]) * 0.1
        elif "vibration" in sensor_name:
            value = baseline * (1 + degradation_effect * 3.0)
            if prev_sensors and "vibration_axial" in prev_sensors:
                axial = prev_sensors["vibration_axial"]
                if "radial" in sensor_name:
                    value += (axial - profile["sensor_baselines"]["vibration_axial"]) * 0.15
        elif "pressure" in sensor_name:
            value = baseline + degradation_effect * 0.8
            if "lubrication" in sensor_name:
                temp_factor = 1.0
                if prev_sensors and "temperature_bearing" in prev_sensors:
                    temp_factor = prev_sensors["temperature_bearing"] / profile["sensor_baselines"]["temperature_bearing"]
                value *= temp_factor
        elif "current" in sensor_name:
            value = baseline * (1 + degradation_effect * 1.5)
        elif "rpm" in sensor_name:
            value = baseline * (1 - degradation_effect * 0.3)
        elif "torque" in sensor_name:
            value = baseline * (1 + degradation_effect * 1.2)
        elif "power" in sensor_name:
            value = baseline * (1 + degradation_effect * 2.0)
        elif "acoustic" in sensor_name:
            value = baseline + degradation_effect * 40.0
        elif "oil_particle" in sensor_name:
            value = baseline + degradation_effect * 80.0
        elif "coolant" in sensor_name:
            value = baseline * (1 - degradation_effect * 0.5)
        elif "resistance" in sensor_name:
            value = baseline * (1 + degradation_effect * 1.0)
        elif "displacement" in sensor_name:
            value = baseline + degradation_effect * 0.3
        else:
            value = baseline * (1 + degradation_effect * 0.5)

        noise = random.gauss(0, baseline * noise_pct)
        value += noise
        value = round(float(max(value, 0)), 4)
        return value

    def generate_lifecycle(self, machine_id, regime=None, total_cycles=None):
        if machine_id not in MACHINE_PROFILES:
            raise ValueError(f"Machine {machine_id} inconnue")

        profile = MACHINE_PROFILES[machine_id]
        hi = self._init_machine(machine_id, regime, total_cycles)
        noise_pct = profile.get("sensor_noise_pct", 0.02)

        records = []
        prev_sensors = None

        for cycle in range(hi.total_cycles):
            hi_value = hi.step()
            rul = hi.get_rul()

            reading = {
                "machine_id": machine_id,
                "machine_type": profile["type"],
                "cycle": cycle + 1,
                "hi": round(hi_value, 2),
                "rul": rul,
                "regime": hi.regime,
            }

            for sensor_name in SENSOR_NAMES:
                baseline = profile["sensor_baselines"].get(sensor_name, 0.0)
                value = self._compute_sensor_value(
                    sensor_name, baseline, hi_value, noise_pct, profile, prev_sensors
                )
                reading[sensor_name] = value

            prev_sensors = {k: v for k, v in reading.items() if k in SENSOR_NAMES}
            records.append(reading)

        return records

    def generate_dataset(self, n_machines=100, cycles_range=(150, 300),
                         regime_distribution=None):
        if regime_distribution is None:
            regime_distribution = {
                "normal": 0.50, "accelerated": 0.20,
                "step": 0.15, "intermittent": 0.15,
            }

        all_records = []
        machine_configs = []

        for i in range(n_machines):
            machine_id = self.machine_ids[i % len(self.machine_ids)]
            unit_id = i + 1

            regime = random.choices(
                list(regime_distribution.keys()),
                weights=list(regime_distribution.values()),
            )[0]
            total_cycles = random.randint(cycles_range[0], cycles_range[1])

            records = self.generate_lifecycle(machine_id, regime, total_cycles)
            for rec in records:
                rec["unit"] = unit_id
            all_records.extend(records)

            machine_configs.append({
                "unit": unit_id,
                "machine_id": machine_id,
                "regime": regime,
                "total_cycles": total_cycles,
            })

        return all_records, machine_configs

    def stream(self, interval_seconds=2, kafka_producer=None, topic=None):
        print(f"Simulateur physique démarré - {len(self.machine_ids)} machines")
        try:
            while True:
                for machine_id in self.machine_ids:
                    if machine_id not in self._lifecycle_counters:
                        self._init_machine(machine_id)
                    counter = self._lifecycle_counters[machine_id]
                    hi = self._health_states[machine_id]
                    if counter >= hi.total_cycles:
                        self._init_machine(machine_id)

                    hi_value = hi.step()
                    rul = hi.get_rul()
                    profile = MACHINE_PROFILES[machine_id]
                    noise_pct = profile.get("sensor_noise_pct", 0.02)

                    reading = {
                        "machine_id": machine_id,
                        "machine_type": profile["type"],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "cycle": counter + 1,
                        "hi": round(hi_value, 2),
                        "rul": rul,
                        "regime": hi.regime,
                    }

                    for sensor_name in SENSOR_NAMES:
                        baseline = profile["sensor_baselines"].get(sensor_name, 0.0)
                        degradation_pct = 1.0 - (hi_value / 100.0)
                        sensitivity = profile.get("degradation_sensitivity", {}).get(sensor_name, 0.0)
                        degradation_effect = degradation_pct * sensitivity * baseline
                        noise = random.gauss(0, baseline * noise_pct)
                        value = round(float(max(baseline + degradation_effect + noise, 0)), 4)
                        reading[sensor_name] = value

                    self._lifecycle_counters[machine_id] = counter + 1

                    if kafka_producer:
                        kafka_producer.send(topic or "sensors-raw", value=reading)
                        kafka_producer.flush()
                    else:
                        print(json.dumps(reading, indent=2))

                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            print("\nSimulateur physique arrêté.")


def test_generation():
    print("=== Test de génération ===")
    sim = PhysicsSimulator(seed=42)

    records, configs = sim.generate_dataset(n_machines=10, cycles_range=(200, 300))
    print(f"Total records: {len(records)}")
    print(f"Machines: {len(configs)}")

    for cfg in configs[:3]:
        machine_records = [r for r in records if r["unit"] == cfg["unit"]]
        print(f"\nUnit {cfg['unit']} ({cfg['machine_id']}): regime={cfg['regime']}, "
              f"cycles={cfg['total_cycles']}, actual_records={len(machine_records)}")
        print(f"  HI start: {machine_records[0]['hi']}, HI end: {machine_records[-1]['hi']}")
        print(f"  RUL start: {machine_records[0]['rul']}, RUL end: {machine_records[-1]['rul']}")
        print(f"  Sensors: {[k for k in machine_records[0].keys() if k.startswith(('temp','vib','press','current'))][:5]}...")

    print("\n=== Premier enregistrement ===")
    print(json.dumps(records[0], indent=2))


if __name__ == "__main__":
    test_generation()
