"""Données SYNTHÉTIQUES pour les tests (jamais pour juger une vraie stratégie)."""
import numpy as np
import pandas as pd


def make_prices(n_days=900, phi=0.0, seed=1, start=1.10, vol=0.0004, spread_pts=8, freq="h"):
    """Marche aléatoire (phi=0) ou avec autocorrélation des rendements (phi>0 = tendance, phi<0 = rappel)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2022-01-03", periods=n_days * 24, freq=freq)
    idx = idx[idx.weekday < 5]
    n = len(idx)
    eps = rng.normal(0, vol, n)
    r = np.zeros(n)
    for i in range(1, n):
        r[i] = phi * r[i - 1] + eps[i]
    close = start * np.exp(np.cumsum(r))
    open_ = np.concatenate([[start], close[:-1]])
    wick = np.abs(rng.normal(0, vol * 0.5, n)) * close
    high = np.maximum(open_, close) + wick
    low = np.minimum(open_, close) - wick
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                         "spread": spread_pts}, index=pd.DatetimeIndex(idx, name="time"))


def make_trending(n_days=900, seed=3, start=1.10, vol=0.0004, drift_sd=0.00012, persistence=0.985, spread_pts=8):
    """Prix avec tendances persistantes (dérive lente qui change de signe) : une stratégie de tendance a un vrai avantage."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2022-01-03", periods=n_days * 24, freq="h")
    idx = idx[idx.weekday < 5]
    n = len(idx)
    mu = np.zeros(n)
    sd_innov = drift_sd * np.sqrt(1 - persistence ** 2)
    for i in range(1, n):
        mu[i] = persistence * mu[i - 1] + rng.normal(0, sd_innov)
    r = mu + rng.normal(0, vol, n)
    close = start * np.exp(np.cumsum(r))
    open_ = np.concatenate([[start], close[:-1]])
    wick = np.abs(rng.normal(0, vol * 0.5, n)) * close
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) + wick,
                         "low": np.minimum(open_, close) - wick, "close": close, "spread": spread_pts},
                        index=pd.DatetimeIndex(idx, name="time"))
