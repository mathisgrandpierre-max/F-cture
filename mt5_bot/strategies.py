"""
strategies.py - 4 stratégies. Chacune renvoie une position CIBLE par bougie (+1 achat, -1 vente, 0 neutre)
calculée à la CLÔTURE de la bougie ; l'exécution se fait à l'ouverture de la suivante (aucune triche).

Le stop-loss (sl_atr x ATR) et le take-profit (rr x stop) sont gérés par le moteur / le broker.
"""
from itertools import product

import numpy as np
import pandas as pd

import indicators as ind


def sma_cross(df, fast=20, slow=100, buffer_atr=0.3, **_):
    """TENDANCE : achat quand la moyenne rapide passe au-dessus de la lente (écart > buffer x ATR
    pour éviter les faux signaux en marché plat), vente dans le cas inverse."""
    f, s, a = ind.sma(df["close"], fast), ind.sma(df["close"], slow), ind.atr(df)
    gap = (f - s) / a
    return ind.state_machine(gap > buffer_atr, gap < 0, gap < -buffer_atr, gap > 0)


def rsi_bollinger(df, bb_n=20, bb_k=2.0, rsi_n=14, rsi_low=30, **_):
    """RETOUR À LA MOYENNE : achat quand le prix sort sous la bande basse ET RSI survendu ;
    sortie au retour sur la moyenne. Symétrique pour la vente (RSI > 100 - rsi_low)."""
    c = df["close"]
    mid, up, lo = ind.bollinger(c, bb_n, bb_k)
    r = ind.rsi(c, rsi_n)
    return ind.state_machine((c < lo) & (r < rsi_low), c >= mid, (c > up) & (r > 100 - rsi_low), c <= mid)


def range_breakout(df, n=48, exit_n=24, **_):
    """CASSURE : achat quand la clôture dépasse le plus haut des n dernières bougies, vente sous le plus bas.
    Sortie quand le prix repasse le canal court (exit_n). Les horaires de session sont filtrés par le moteur."""
    hi, lo = ind.donchian(df, n)
    xhi, xlo = ind.donchian(df, exit_n)
    c = df["close"]
    return ind.state_machine(c > hi, c < xlo, c < lo, c > xhi)


def momentum_atr(df, roc_n=24, thr_atr=1.5, vol_n=100, **_):
    """MOMENTUM + VOLATILITÉ : on suit le mouvement des roc_n dernières bougies seulement s'il est grand
    (> thr x ATR) ET que la volatilité est au-dessus de sa médiane (le marché 'bouge'). Sortie quand le momentum s'inverse."""
    c, a = df["close"], ind.atr(df)
    mom = (c - c.shift(roc_n)) / a
    vol_ok = a > a.rolling(vol_n).median()
    return ind.state_machine((mom > thr_atr) & vol_ok, mom < 0, (mom < -thr_atr) & vol_ok, mom > 0)


STRATEGIES = {
    "sma_cross": sma_cross,
    "rsi_bollinger": rsi_bollinger,
    "range_breakout": range_breakout,
    "momentum_atr": momentum_atr,
}

# Grilles de paramètres volontairement PETITES (moins de combinaisons = moins de surapprentissage).
# sl_atr = distance du stop en multiples d'ATR ; rr = take-profit en multiples du stop (0 = pas de TP).
_GRIDS = {
    "sma_cross": dict(fast=[10, 20], slow=[50, 100], buffer_atr=[0.3], sl_atr=[2.0, 3.0], rr=[0.0]),
    "rsi_bollinger": dict(bb_n=[20], bb_k=[2.0, 2.5], rsi_low=[25, 30], sl_atr=[2.0, 3.0], rr=[0.0]),
    "range_breakout": dict(n=[24, 48, 96], exit_n=[12, 24], sl_atr=[2.0, 3.0], rr=[0.0]),
    "momentum_atr": dict(roc_n=[12, 24, 48], thr_atr=[1.5, 2.5], sl_atr=[2.0, 3.0], rr=[0.0]),
}
# Adaptation à la classe d'actif : le Bitcoin est bien plus volatil -> stops plus larges ; 24h/24 -> fenêtres plus longues.
_CRYPTO_OVERRIDES = {
    "sma_cross": dict(fast=[20, 50], slow=[100, 200], sl_atr=[3.0, 4.0]),
    "rsi_bollinger": dict(sl_atr=[3.0, 4.0]),
    "range_breakout": dict(n=[48, 96, 192], exit_n=[24, 48], sl_atr=[3.0, 4.0]),
    "momentum_atr": dict(roc_n=[24, 48, 96], sl_atr=[3.0, 4.0]),
}


def param_grid(strategy: str, asset_class: str) -> list[dict]:
    """Liste de toutes les combinaisons de paramètres à tester pour cette stratégie et cette classe d'actif."""
    g = dict(_GRIDS[strategy])
    if asset_class == "crypto":
        g.update(_CRYPTO_OVERRIDES[strategy])
    keys = list(g)
    combos = [dict(zip(keys, v)) for v in product(*g.values())]
    if strategy == "sma_cross":
        combos = [c for c in combos if c["fast"] < c["slow"]]
    if strategy == "range_breakout":
        combos = [c for c in combos if c["exit_n"] < c["n"]]
    return combos


def compute_signal(strategy: str, df: pd.DataFrame, params: dict) -> np.ndarray:
    return STRATEGIES[strategy](df, **params)
