"""
engine.py - Moteur de backtest réaliste.

Coûts pris en compte : spread (achat à l'ask, vente au bid), commission, swap (frais de nuit),
slippage (glissement : écart entre le prix voulu et le prix obtenu).
Règles anti-triche : signal calculé à la clôture, exécuté à l'ouverture suivante ; si le stop ET
le take-profit sont touchés dans la même bougie, on suppose le stop (hypothèse pessimiste).
"""
import numpy as np
import pandas as pd

import indicators as ind
from config import SymbolSpec

TRADE_COLS = ["entry_time", "exit_time", "dir", "lots", "entry", "exit", "pnl", "pnl_pct", "r", "reason"]


def entry_mask(index: pd.DatetimeIndex, spec: SymbolSpec) -> np.ndarray:
    """True quand on a le droit d'OUVRIR un trade (session de marché adaptée à la paire, pas de week-end)."""
    h = index.hour.to_numpy()
    wd = index.weekday.to_numpy()
    a, b = spec.session_utc
    ok = (h >= a) & (h < b)
    if spec.asset_class != "crypto":
        ok &= wd < 5
        ok &= ~((wd == 4) & (h >= spec.close_friday_hour - 2))   # pas de nouvelle entrée en fin de vendredi
    return ok


def run_backtest(df: pd.DataFrame, sig: np.ndarray, spec: SymbolSpec, lo: int, hi: int,
                 sl_atr: float = 2.0, rr: float = 0.0, risk_pct: float = 0.01,
                 start_equity: float = 10_000.0, atr_n: int = 14, max_leverage: float = 10.0) -> pd.DataFrame:
    """Simule la stratégie sur les barres [lo, hi). Retourne un DataFrame de trades clôturés."""
    o, h, l = df["open"].to_numpy(), df["high"].to_numpy(), df["low"].to_numpy()
    atr = ind.atr(df, atr_n).to_numpy()
    if "spread" in df:
        spr = df["spread"].to_numpy() * spec.point
    else:
        spr = np.full(len(df), spec.default_spread_pips * spec.pip_size)
    idx = df.index
    mask = entry_mask(idx, spec)
    wd, hr = idx.weekday.to_numpy(), idx.hour.to_numpy()
    day = idx.normalize().to_numpy().astype("datetime64[D]").astype(np.int64)
    slip = spec.slippage_pips * spec.pip_size

    trades, equity = [], start_equity
    pos = 0
    entry = sl = tp = lots = risk_money = swap = 0.0
    t_in = None
    blocked = 0                       # direction bloquée après un stop (évite de re-rentrer en boucle)
    for j in range(max(lo, 1), hi):
        s = int(sig[j - 1])
        if blocked and s != blocked:
            blocked = 0
        exited_intrabar = False
        if pos != 0:
            if day[j] != day[j - 1]:                       # passage de minuit : swap (x3 le mercredi)
                swap += (spec.swap_long_pips if pos > 0 else spec.swap_short_pips) * spec.pip_value * lots * (3 if wd[j] == 2 else 1)
            ex, why = None, ""
            if pos > 0:                                    # long : sorties au BID
                if o[j] <= sl:
                    ex, why = o[j] - slip, "SL(gap)"
                elif l[j] <= sl:
                    ex, why = sl - slip, "SL"
                elif tp and h[j] >= tp:
                    ex, why = tp, "TP"
            else:                                          # short : sorties à l'ASK = bid + spread
                if o[j] + spr[j] >= sl:
                    ex, why = o[j] + spr[j] + slip, "SL(gap)"
                elif h[j] + spr[j] >= sl:
                    ex, why = sl + slip, "SL"
                elif tp and l[j] + spr[j] <= tp:
                    ex, why = tp, "TP"
            if ex is not None:
                exited_intrabar = True
            elif s != pos or (spec.asset_class != "crypto" and wd[j] == 4 and hr[j] >= spec.close_friday_hour):
                ex = o[j] - slip if pos > 0 else o[j] + spr[j] + slip
                why = "signal" if s != pos else "vendredi"
            if ex is not None:
                gross = (ex - entry) * pos / spec.pip_size * spec.pip_value * lots
                pnl = gross - 2 * spec.commission_per_lot * lots + swap
                trades.append((t_in, idx[j], pos, lots, entry, ex, pnl, pnl / equity, pnl / risk_money, why))
                equity += pnl
                if why.startswith("SL"):
                    blocked = pos
                pos, swap = 0, 0.0
        if pos == 0 and not exited_intrabar and s != 0 and s != blocked and mask[j] and not np.isnan(atr[j - 1]):
            sl_dist = sl_atr * atr[j - 1]
            eff_pips = (sl_dist + spr[j] + 2 * slip) / spec.pip_size       # le risque inclut spread + slippage
            risk_money = risk_pct * equity
            lots = np.floor(risk_money / (eff_pips * spec.pip_value) / spec.lot_step) * spec.lot_step
            lots = min(lots, np.floor(max_leverage * equity / spec.notional_per_lot / spec.lot_step) * spec.lot_step)
            if lots < spec.min_lot or equity <= 0:
                continue
            pos = s
            entry = o[j] + spr[j] + slip if s > 0 else o[j] - slip         # long à l'ask, short au bid
            sl = entry - pos * sl_dist
            tp = entry + pos * sl_dist * rr if rr > 0 else 0.0
            t_in, swap = idx[j], 0.0
    return pd.DataFrame(trades, columns=TRADE_COLS)
