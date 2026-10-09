"""reporting.py - Journal des trades (CSV) et rapports hebdomadaire / mensuel."""
import csv
from datetime import datetime, timedelta, timezone

import pandas as pd

import config as C
import metrics as M

JOURNAL = C.LOG_DIR / "trades.csv"
COLS = ["entry_time", "exit_time", "symbol", "strategy", "dir", "lots", "entry", "exit", "pnl", "pnl_pct", "r", "reason"]


def journal_trade(row: dict):
    """Ajoute un trade clôturé au journal."""
    C.LOG_DIR.mkdir(exist_ok=True)
    new = not JOURNAL.exists()
    with open(JOURNAL, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in COLS})


def load_journal() -> pd.DataFrame:
    if not JOURNAL.exists():
        return pd.DataFrame(columns=COLS)
    return pd.read_csv(JOURNAL, parse_dates=["entry_time", "exit_time"])


def build_report(period: str, now: datetime | None = None) -> str:
    """period = 'weekly' (7 derniers jours) ou 'monthly' (30 derniers jours). Retourne un texte prêt à envoyer."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    days = 7 if period == "weekly" else 30
    j = load_journal()
    j = j[j["exit_time"] >= now - timedelta(days=days)] if len(j) else j
    lines = [f"RAPPORT {'HEBDOMADAIRE' if days == 7 else 'MENSUEL'} - {now:%Y-%m-%d}"]
    if j.empty:
        lines.append("Aucun trade clôturé sur la période.")
    else:
        m = M.compute(j, C.START_EQUITY, days)
        lines += [f"Trades: {m['n']} | Gagnants: {m['win']:.0%} | Résultat net: {m['net']:+.2f} {C.ACCOUNT_CURRENCY}",
                  f"Profit factor: {m['pf']:.2f} | Drawdown (sur la période): {m['dd']:.1%} | Espérance: {m['exp_r']:+.2f} R",
                  "Détail par stratégie / symbole:"]
        for (sym, strat), g in j.groupby(["symbol", "strategy"]):
            mg = M.compute(g, C.START_EQUITY, days)
            lines.append(f"  {sym:7} {strat:15} n={mg['n']:3d} net={mg['net']:+8.2f} PF={mg['pf']:.2f}")
    lines.append("Rappel : une démo est plus indulgente que le réel. Ceci n'est pas un conseil financier.")
    text = "\n".join(lines)
    C.REPORT_DIR.mkdir(exist_ok=True)
    (C.REPORT_DIR / f"{period}_{now:%Y%m%d}.txt").write_text(text)
    return text
