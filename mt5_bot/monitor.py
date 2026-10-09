"""monitor.py - Surveille la forme d'une stratégie en réel (démo) et décide de la désactiver."""
import pandas as pd

import config as C
import metrics as M


def check_health(trades: pd.DataFrame, expected_dd: float):
    """trades = trades clôturés de CETTE stratégie sur CE symbole (journal). Retourne (sain, raison).
    Règles : sur les HEALTH_WINDOW_TRADES derniers trades, profit factor < HEALTH_MIN_PF -> désactivation ;
    drawdown live > HEALTH_DD_MULTIPLIER x drawdown de test -> désactivation."""
    if len(trades) < 10:
        return True, "pas assez de trades pour juger"
    w = trades.tail(C.HEALTH_WINDOW_TRADES)
    m = M.compute(w, C.START_EQUITY, 30)
    if len(w) >= 20 and m["pf"] < C.HEALTH_MIN_PF:
        return False, f"profit factor {m['pf']:.2f} < {C.HEALTH_MIN_PF} sur les {len(w)} derniers trades"
    dd = M.max_drawdown(w, C.START_EQUITY)
    limit = max(expected_dd * C.HEALTH_DD_MULTIPLIER, 0.05)
    if dd > limit:
        return False, f"drawdown live {dd:.1%} > {limit:.1%} (1,5 x drawdown de test)"
    return True, "ok"
