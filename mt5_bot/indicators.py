"""indicators.py - Indicateurs techniques (tous calculés uniquement avec le PASSÉ)."""
import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    """Moyenne mobile simple : moyenne des n dernières clôtures."""
    return s.rolling(n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """RSI : oscillateur 0-100 ; <30 = survendu (baisse excessive), >70 = suracheté."""
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, 1e-12))


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0):
    """Bandes de Bollinger : moyenne +/- k écarts-types ; mesure l'étirement du prix."""
    mid = close.rolling(n).mean()
    sd = close.rolling(n).std()
    return mid, mid + k * sd, mid - k * sd


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """ATR (Average True Range) : amplitude moyenne d'une bougie = mesure de la volatilité.
    Sert à placer le stop-loss proportionnellement à la volatilité du moment."""
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def donchian(df: pd.DataFrame, n: int):
    """Canal de Donchian : plus haut / plus bas des n bougies PRÉCÉDENTES (shift(1) = pas de triche)."""
    return df["high"].rolling(n).max().shift(1), df["low"].rolling(n).min().shift(1)


def state_machine(long_in, long_out, short_in, short_out) -> np.ndarray:
    """Transforme des événements d'entrée/sortie (booléens) en position cible : +1, -1 ou 0."""
    li, lo, si, so = (np.asarray(x, dtype=bool) for x in (long_in, long_out, short_in, short_out))
    out = np.zeros(len(li), dtype=np.int8)
    pos = 0
    for i in range(len(li)):
        if pos == 1 and lo[i]:
            pos = 0
        elif pos == -1 and so[i]:
            pos = 0
        if pos == 0:
            if li[i] and not si[i]:
                pos = 1
            elif si[i] and not li[i]:
                pos = -1
        out[i] = pos
    return out
