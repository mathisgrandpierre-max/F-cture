"""metrics.py - Mesures de performance à partir de la liste des trades."""
import numpy as np
import pandas as pd


def equity_curve(trades: pd.DataFrame, start: float) -> np.ndarray:
    return start + np.cumsum(trades["pnl"].to_numpy()) if len(trades) else np.array([start])


def max_drawdown(trades: pd.DataFrame, start: float) -> float:
    """Drawdown max : plus grosse baisse (en %) entre un sommet du capital et le creux suivant."""
    eq = np.concatenate([[start], equity_curve(trades, start)])
    peak = np.maximum.accumulate(eq)
    return float(((peak - eq) / peak).max())


def compute(trades: pd.DataFrame, start: float, days: float) -> dict:
    """Résumé chiffré. 'days' = durée de la période testée (pour annualiser le Sharpe)."""
    n = len(trades)
    if n == 0:
        return dict(n=0, net=0.0, pf=0.0, dd=0.0, sharpe=0.0, win=0.0, exp_r=0.0, pos_months=0.0)
    p = trades["pnl"]
    gw, gl = p[p > 0].sum(), -p[p < 0].sum()
    pf = float(gw / gl) if gl > 0 else (99.0 if gw > 0 else 0.0)   # profit factor : gains bruts / pertes brutes
    daily = trades.set_index("exit_time")["pnl_pct"].resample("D").sum()
    full = daily.reindex(pd.date_range(trades["entry_time"].min().normalize(),
                                       trades["exit_time"].max().normalize(), freq="D"), fill_value=0.0)
    sd = full.std()
    sharpe = float(full.mean() / sd * np.sqrt(365)) if sd > 0 else 0.0   # Sharpe : rendement moyen / risque, annualisé
    monthly = p.groupby(trades["exit_time"].dt.to_period("M")).sum()
    return dict(n=n, net=float(p.sum()), pf=min(pf, 99.0), dd=max_drawdown(trades, start), sharpe=sharpe,
                win=float((p > 0).mean()), exp_r=float(trades["r"].mean()),
                pos_months=float((monthly > 0).mean()))


def monte_carlo_dd(trades: pd.DataFrame, sims: int = 1000, q: float = 0.95, seed: int = 0) -> float:
    """Mélange l'ordre des trades 'sims' fois : donne le drawdown qu'on peut raisonnablement subir
    si le hasard range les gains et les pertes dans un mauvais ordre (95e centile)."""
    if len(trades) < 5:
        return 1.0
    rng = np.random.default_rng(seed)
    r = trades["pnl_pct"].to_numpy()
    dds = np.empty(sims)
    for k in range(sims):
        eq = np.concatenate([[1.0], np.cumprod(1 + rng.permutation(r))])
        dds[k] = ((np.maximum.accumulate(eq) - eq) / np.maximum.accumulate(eq)).max()
    return float(np.quantile(dds, q))
