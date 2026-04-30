# %%
import glob
import random
import os
import numpy as np
import pandas as pd
import tensorflow as tf
import joblib

from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Input, Dense
from tensorflow.keras.callbacks import EarlyStopping
from tensorflow.keras.optimizers import Adam, SGD
from tensorflow.keras.utils import set_random_seed

from scikeras.wrappers import KerasRegressor

from sklearn.model_selection import RandomizedSearchCV, train_test_split
from sklearn.preprocessing import MinMaxScaler

from scipy.stats import uniform, randint


# =========================
# CONFIG
# =========================
SEED = 0
PATIENCE = 25
DATASET_PATH = "../captures/capture_1.csv"

DROP_COLS = ["src_ip", "dst_ip", "src_port", "dst_port", "protocol", "label"]

random.seed(SEED)
np.random.seed(SEED)
set_random_seed(SEED)


# =========================
# DATA LOADING
# =========================
def load_data(path):
    df = pd.read_csv(path).dropna()

    df_normal = df[df["label"] == "normal"].drop(columns=DROP_COLS, errors="ignore")
    df_malicious = df[df["label"] == "malicious"].drop(columns=DROP_COLS, errors="ignore")

    print(f"Normal: {len(df_normal)} | Malicious: {len(df_malicious)}")
    return df_normal, df_malicious


# =========================
# PREPROCESSING
# =========================
def preprocess(df_normal, df_malicious):
    X = df_normal.values.astype("float32")

    # Split BEFORE scaling (avoid leakage)
    X_train, X_temp = train_test_split(X, test_size=0.30, random_state=SEED)
    X_val, X_test = train_test_split(X_temp, test_size=0.50, random_state=SEED)

    scaler = MinMaxScaler()
    X_train = scaler.fit_transform(X_train)
    X_val = scaler.transform(X_val)
    X_test = scaler.transform(X_test)

    joblib.dump(scaler, "scaler.pkl")
    print("Scaler saved to scaler.pkl")

    if len(df_malicious) > 0:
        X_anom = scaler.transform(df_malicious.values.astype("float32"))
    else:
        X_anom = None

    return X_train, X_val, X_test, X_anom, scaler


# =========================
# MODEL
# =========================
def create_model(input_dim, hidden_units=32, coding_dim=8, learning_rate=1e-3, optimizer=Adam):
    model = Sequential([
        Input(shape=(input_dim,)),
        Dense(hidden_units, activation="relu"),
        Dense(coding_dim, activation="relu"),
        Dense(hidden_units, activation="relu"),
        Dense(input_dim, activation="sigmoid"),
    ])

    model.compile(
        optimizer=optimizer(learning_rate=learning_rate),
        loss="mse"
    )
    return model


# =========================
# TRAINING
# =========================
def train_model(X_train, X_val):
    input_dim = X_train.shape[1]

    early_stopping = EarlyStopping(
        monitor="val_loss",
        patience=PATIENCE,
        restore_best_weights=True,
        verbose=1
    )

    model = KerasRegressor(
        model=create_model,
        model__input_dim=input_dim,
        callbacks=[early_stopping],
        verbose=0
    )

    param_dist = {
        "model__learning_rate": uniform(1e-4, 1e-2),
        "model__hidden_units": randint(16, 128),
        "model__coding_dim": randint(2, 16),
        "batch_size": [64, 128, 256],
        "model__optimizer": [Adam, SGD],
        "epochs": [50, 100]
    }

    search = RandomizedSearchCV(
        model,
        param_distributions=param_dist,
        n_iter=10,
        cv=3,
        scoring="neg_mean_squared_error",
        random_state=SEED,
        verbose=1,
        n_jobs=-1
    )

    search.fit(X_train, X_train, validation_data=(X_val, X_val))

    print("Best params:", search.best_params_)

    best_model = search.best_estimator_.model_
    best_model.save("autoencoder_model.h5")

    return best_model


# =========================
# EVALUATION
# =========================
def print_statistics(label, value, unit=""):
    print(f"{label:<20}: {value:.6f} {unit}")

def compute_threshold(model, X_val, fpr_target=0.05):
    recon = model.predict(X_val)
    errors = np.mean(np.square(X_val - recon), axis=1)

    threshold = np.percentile(errors, 100 * (1 - fpr_target))
    print_statistics("Threshold", threshold)

    with open("anomaly_threshold.txt", "w") as f:
        f.write(f"{threshold:.6f}\n")

    return threshold


def evaluate(model, X_test, X_anom, threshold):
    # FPR
    recon_test = model.predict(X_test)
    err_test = np.mean(np.square(X_test - recon_test), axis=1)

    fpr = np.mean(err_test > threshold)
    print_statistics("False Positive Rate", fpr)

    # TPR
    if X_anom is not None:
        recon_anom = model.predict(X_anom)
        err_anom = np.mean(np.square(X_anom - recon_anom), axis=1)

        tpr = np.mean(err_anom > threshold)
        print_statistics("True Positive Rate", tpr)
    else:
        print("True Positive Rate   : N/A (no anomalies)")


# =========================
# MAIN
# =========================
def main():
    df_normal, df_malicious = load_data(DATASET_PATH)

    X_train, X_val, X_test, X_anom, scaler = preprocess(df_normal, df_malicious)

    model = train_model(X_train, X_val)

    threshold = compute_threshold(model, X_val)

    evaluate(model, X_test, X_anom, threshold)


if __name__ == "__main__":
    main()