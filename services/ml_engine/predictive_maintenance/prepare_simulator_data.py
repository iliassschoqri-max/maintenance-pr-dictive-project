"""
Préparation des données du simulateur physique pour l'entraînement GRU.

Génère des données via PhysicsSimulator, crée des séquences glissantes,
et split train/val/test par machine (unseen machines pour le test).
"""
import os
import sys

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from simulator.physics_simulator import PhysicsSimulator, SENSOR_NAMES

SEQ_LENGTH = 50
N_MACHINES = 200
CYCLES_RANGE = (150, 300)
RANDOM_SEED = 42

FEATURE_COLUMNS = SENSOR_NAMES
N_FEATURES = len(FEATURE_COLUMNS)


def generate_data(n_machines=N_MACHINES, cycles_range=CYCLES_RANGE, seed=RANDOM_SEED):
    print(f"Génération de {n_machines} machines (seed={seed})...")
    sim = PhysicsSimulator(seed=seed)
    records, configs = sim.generate_dataset(
        n_machines=n_machines, cycles_range=cycles_range,
    )
    df = pd.DataFrame(records)
    print(f"  {len(df)} enregistrements, {df['unit'].nunique()} unités")
    return df, configs


def create_sequences(df, seq_length=SEQ_LENGTH):
    X, y = [], []
    for unit_id in df["unit"].unique():
        unit_data = df[df["unit"] == unit_id].sort_values("cycle")
        sensor_values = unit_data[FEATURE_COLUMNS].values
        rul_values = unit_data["rul"].values
        for i in range(len(sensor_values) - seq_length + 1):
            X.append(sensor_values[i:i + seq_length])
            y.append(rul_values[i + seq_length - 1])
    return np.array(X), np.array(y)


def prepare_data(n_machines=N_MACHINES, seq_length=SEQ_LENGTH, seed=RANDOM_SEED):
    df, configs = generate_data(n_machines=n_machines, seed=seed)

    units = df["unit"].unique()
    np.random.RandomState(seed).shuffle(units)
    n_train = int(len(units) * 0.6)
    n_val = int(len(units) * 0.2)

    train_units = units[:n_train]
    val_units = units[n_train:n_train + n_val]
    test_units = units[n_train + n_val:]

    print(f"  Train: {len(train_units)} unités, Val: {len(val_units)}, Test: {len(test_units)}")

    train_df = df[df["unit"].isin(train_units)]
    val_df = df[df["unit"].isin(val_units)]
    test_df = df[df["unit"].isin(test_units)]

    X_train, y_train = create_sequences(train_df, seq_length)
    X_val, y_val = create_sequences(val_df, seq_length)
    X_test, y_test = create_sequences(test_df, seq_length)

    orig_shape_train = X_train.shape
    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train.reshape(-1, N_FEATURES)).reshape(orig_shape_train)
    X_val = scaler.transform(X_val.reshape(-1, N_FEATURES)).reshape(X_val.shape)
    X_test = scaler.transform(X_test.reshape(-1, N_FEATURES)).reshape(X_test.shape)

    print(f"  X_train: {X_train.shape}, y_train: {y_train.shape}")
    print(f"  X_val:   {X_val.shape}, y_val:   {y_val.shape}")
    print(f"  X_test:  {X_test.shape}, y_test:  {y_test.shape}")
    print(f"  RUL range: train=[{y_train.min():.1f}, {y_train.max():.1f}], "
          f"test=[{y_test.min():.1f}, {y_test.max():.1f}]")

    return (X_train, y_train), (X_val, y_val), (X_test, y_test), N_FEATURES, scaler


if __name__ == "__main__":
    prepare_data()
