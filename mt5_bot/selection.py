"""
selection.py - Choix automatique de la stratégie la plus ROBUSTE (pas la plus rentable en brut).

Méthode :
 1. Les derniers HOLDOUT_FRACTION des données sont mis de côté (jamais regardés pendant le choix).
 2. Walk-forward : on optimise les paramètres sur 180 jours (entraînement), puis on mesure sur les 60 jours
    suivants (test, jamais vus) ; on fait glisser la fenêtre. Seuls les résultats de TEST comptent.
 3. Anti-biais de sélection : plus on teste de combinaisons, plus on trouve de "gagnantes" par pur hasard.
    Le Sharpe du test doit dépasser le meilleur Sharpe attendu du seul hasard (approche 'Sharpe déflaté').
 4. Filtres chiffrés (profit factor, drawdown, nb de trades, % de fenêtres gagnantes, Monte-Carlo).
 5. Test final unique sur le holdout. Si rien ne passe : AUCUNE stratégie active (le bot reste à plat).
"""
import json
from collections import Counter
from datetime import datetime, timezone
from statistics import NormalDist

import numpy as np
import pandas as pd

import config as C
import metrics as M
from engine import run_backtest
from strategies import STRATEGIES, compute_signal, param_grid


def robust_score(m: dict) -> float:
    """Note de robustesse. Pénalise : peu de trades, drawdown élevé, profit factor plafonné à 3
    (un PF de 10 sur 12 trades est de la chance, pas un talent)."""
    if m["n"] < C.MIN_TRADES_TRAIN or m["pf"] <= 1.0 or m["net"] <= 0:
        return -1.0
    size = min(1.0, m["n"] / 60)
    dd_pen = 1 - min(m["dd"] / 0.30, 1.0)
    return (min(m["pf"], 3.0) - 1.0) * size * dd_pen


def sharpe_hurdle(n_trials: int, years: float) -> float:
    """Sharpe qu'une stratégie SANS aucun talent atteindrait au mieux en essayant n_trials combinaisons
    (espérance du maximum de n_trials gaussiennes, Bailey & López de Prado simplifié)."""
    if n_trials < 2 or years <= 0:
        return 0.0
    nd, g = NormalDist(), 0.5772156649
    emax = (1 - g) * nd.inv_cdf(1 - 1 / n_trials) + g * nd.inv_cdf(1 - 1 / (n_trials * np.e))
    return emax / np.sqrt(years)


def _signals(df, strategy, grid):
    return [compute_signal(strategy, df, p) for p in grid]


def walk_forward(df, spec, strategy, end_idx):
    """Walk-forward sur df[:end_idx]. Retourne (trades de test concaténés, table des fenêtres, n_combinaisons)."""
    grid = param_grid(strategy, spec.asset_class)
    sigs = _signals(df, strategy, grid)
    bars_per_day = 24
    tr, te = C.WF_TRAIN_DAYS * bars_per_day, C.WF_TEST_DAYS * bars_per_day
    folds, all_trades, start = [], [], 0
    while start + tr + te <= end_idx:
        a, b, c = start, start + tr, start + tr + te
        best, best_score = None, -9.0
        for p, s in zip(grid, sigs):
            t = run_backtest(df, s, spec, a, b, p["sl_atr"], p["rr"], C.RISK_PER_TRADE, C.START_EQUITY)
            sc = robust_score(M.compute(t, C.START_EQUITY, C.WF_TRAIN_DAYS)) if len(t) else -1.0
            if sc > best_score:
                best, best_score = (p, s), sc
        if best is not None and best_score > 0:
            p, s = best
            t = run_backtest(df, s, spec, b, c, p["sl_atr"], p["rr"], C.RISK_PER_TRADE, C.START_EQUITY)
            all_trades.append(t)
            folds.append(dict(start=str(df.index[b]), params=p, pnl=float(t["pnl"].sum()) if len(t) else 0.0, n=len(t)))
        else:                                  # aucune combinaison fiable à l'entraînement -> on reste à plat
            folds.append(dict(start=str(df.index[b]), params=None, pnl=0.0, n=0))
        start += te
    trades = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame(columns=["pnl"])
    return trades, folds, len(grid)


def evaluate_symbol(df: pd.DataFrame, spec) -> dict:
    """Évalue toutes les stratégies sur un symbole et renvoie le classement + la décision."""
    n = len(df)
    split = int(n * (1 - C.HOLDOUT_FRACTION))
    rows, n_trials = [], 0
    for name in STRATEGIES:
        trades, folds, ng = walk_forward(df, spec, name, split)
        n_trials += ng
        years = max(len(folds), 1) * C.WF_TEST_DAYS / 365
        m = M.compute(trades, C.START_EQUITY, len(folds) * C.WF_TEST_DAYS) if len(trades) else M.compute(trades, C.START_EQUITY, 1)
        active = [f for f in folds if f["params"] is not None]
        m["pos_folds"] = float(np.mean([f["pnl"] > 0 for f in folds])) if folds else 0.0
        m["mc_dd"] = M.monte_carlo_dd(trades, C.MC_SIMULATIONS) if len(trades) >= 5 else 1.0
        chosen = Counter(json.dumps(f["params"], sort_keys=True) for f in active).most_common(1)
        rows.append(dict(strategy=name, metrics=m, folds=len(folds), years=years,
                         params=json.loads(chosen[0][0]) if chosen else None))
    for r in rows:                                          # le seuil dépend du NOMBRE TOTAL d'essais
        r["hurdle"] = sharpe_hurdle(n_trials, r["years"])
        m = r["metrics"]
        r["score"] = robust_score(m) * min(m["pos_folds"] / C.MIN_POSITIVE_FOLDS, 1.0)
        fails = []
        if m["n"] < C.MIN_TRADES_OOS: fails.append(f"trades {m['n']}<{C.MIN_TRADES_OOS}")
        if m["pf"] < C.MIN_PROFIT_FACTOR: fails.append(f"PF {m['pf']:.2f}<{C.MIN_PROFIT_FACTOR}")
        if m["dd"] > C.MAX_DRAWDOWN: fails.append(f"DD {m['dd']:.0%}>{C.MAX_DRAWDOWN:.0%}")
        if m["pos_folds"] < C.MIN_POSITIVE_FOLDS: fails.append(f"fenêtres gagnantes {m['pos_folds']:.0%}")
        if m["mc_dd"] > C.MAX_MC_DRAWDOWN: fails.append(f"DD Monte-Carlo {m['mc_dd']:.0%}")
        if m["sharpe"] < r["hurdle"]: fails.append(f"Sharpe {m['sharpe']:.2f}<seuil hasard {r['hurdle']:.2f}")
        if r["params"] is None: fails.append("aucun paramètre fiable")
        r["fails"] = fails
    rows.sort(key=lambda r: r["score"], reverse=True)
    decision = {"status": "NONE", "reason": "aucune stratégie robuste : le bot reste à plat sur ce symbole"}
    for r in rows:                                          # holdout : une seule chance, dans l'ordre du classement
        if r["fails"]:
            continue
        p = r["params"]
        sig = compute_signal(r["strategy"], df, p)
        t = run_backtest(df, sig, spec, split, n, p["sl_atr"], p["rr"], C.RISK_PER_TRADE, C.START_EQUITY)
        h = M.compute(t, C.START_EQUITY, (n - split) / 24)
        r["holdout"] = h
        if h["n"] >= 10 and h["pf"] >= C.MIN_HOLDOUT_PF and h["net"] > 0:
            decision = {"status": "ACTIVE", "strategy": r["strategy"], "params": p,
                        "expected_dd": r["metrics"]["dd"], "expected_pf": r["metrics"]["pf"]}
            break
        r["fails"].append(f"holdout refusé (n={h['n']}, PF={h['pf']:.2f})")
    return dict(symbol=spec.name, decision=decision, ranking=rows, n_trials=n_trials,
                bars=n, generated=datetime.now(timezone.utc).isoformat())


def run_selection(data: dict) -> dict:
    """data = {symbole: DataFrame}. Écrit state/selection.json et retourne le résultat."""
    out = {"generated": datetime.now(timezone.utc).isoformat(), "symbols": {}}
    for sym, df in data.items():
        out["symbols"][sym] = evaluate_symbol(df, C.SYMBOLS[sym])
    C.STATE_DIR.mkdir(exist_ok=True)
    (C.STATE_DIR / "selection.json").write_text(json.dumps(out, indent=2, default=str))
    return out


def format_report(out: dict) -> str:
    lines = []
    for sym, r in out["symbols"].items():
        d = r["decision"]
        lines.append(f"\n=== {sym} -> {d['status']} {d.get('strategy', '')} {d.get('params', '')}")
        for x in r["ranking"]:
            m = x["metrics"]
            lines.append(f"  {x['strategy']:15} score={x['score']:.3f} n={m['n']:4d} PF={m['pf']:.2f} "
                         f"DD={m['dd']:.0%} Sharpe={m['sharpe']:.2f} (seuil {x['hurdle']:.2f}) "
                         f"fenêtres+={m['pos_folds']:.0%}  {'OK' if not x['fails'] else 'REFUSÉ: ' + '; '.join(x['fails'])}")
    return "\n".join(lines)
