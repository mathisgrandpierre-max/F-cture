"""
risk.py - Gestion du risque STRICTE et NON DÉSACTIVABLE.

Les plafonds ci-dessous sont codés en dur : config.py peut seulement les RESSERRER (min(config, plafond)).
Aucune fonction du bot ne peut ouvrir un trade sans passer par RiskManager.can_open() et sans stop-loss.
"""
import csv
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config as C
from engine import entry_mask

import pandas as pd

HARD_MAX_RISK_PER_TRADE = 0.01   # 1 % max risqué par trade
HARD_MAX_DAILY_LOSS = 0.05
HARD_MAX_MONTHLY_LOSS = 0.15
HARD_MAX_OPEN_TRADES = 5


def _eff(value, cap):
    return min(value, cap)


RISK_PER_TRADE = _eff(C.RISK_PER_TRADE, HARD_MAX_RISK_PER_TRADE)
MAX_DAILY_LOSS = _eff(C.MAX_DAILY_LOSS, HARD_MAX_DAILY_LOSS)
MAX_MONTHLY_LOSS = _eff(C.MAX_MONTHLY_LOSS, HARD_MAX_MONTHLY_LOSS)
MAX_OPEN_TRADES = _eff(C.MAX_OPEN_TRADES, HARD_MAX_OPEN_TRADES)


def position_size(equity, sl_distance, spread, slippage, tick_size, tick_value,
                  vol_min, vol_step, vol_max, risk_pct=RISK_PER_TRADE) -> float:
    """Taille de position en lots pour que la perte SI LE STOP EST TOUCHÉ soit <= risk_pct x capital.
    Le spread et le slippage sont ajoutés à la distance de stop (ils aggravent la perte réelle).
    On arrondit TOUJOURS vers le bas ; si le minimum du broker dépasse le risque autorisé -> 0 (pas de trade)."""
    if sl_distance <= 0 or tick_size <= 0 or tick_value <= 0 or equity <= 0:
        return 0.0
    risk_pct = min(risk_pct, HARD_MAX_RISK_PER_TRADE)
    loss_per_lot = (sl_distance + spread + 2 * slippage) / tick_size * tick_value
    lots = math.floor(equity * risk_pct / loss_per_lot / vol_step + 1e-9) * vol_step
    lots = min(lots, vol_max)
    return round(lots, 8) if lots >= vol_min else 0.0


def currencies_of(symbol: str) -> set:
    s = symbol.upper().replace(C.SYMBOL_SUFFIX.upper(), "")
    return {s[:3], s[3:6]} | ({"USD"} if s[3:6] == "USD" else set())


def news_blocked(symbol: str, now: datetime, path: Path = C.NEWS_FILE):
    """Bloque si une news 'high' concerne une devise du symbole dans ±NEWS_BLACKOUT_MIN minutes.
    Fichier absent ou trop ancien -> on bloque (principe de précaution)."""
    if not path.exists():
        return True, f"calendrier news absent ({path.name})"
    age = now.timestamp() - path.stat().st_mtime
    if age > C.NEWS_FILE_MAX_AGE_DAYS * 86400:
        return True, f"calendrier news trop ancien (> {C.NEWS_FILE_MAX_AGE_DAYS} j)"
    cur = currencies_of(symbol)
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if (row.get("impact") or "").lower() != "high" or (row.get("currency") or "").upper() not in cur:
                continue
            t = datetime.fromisoformat(row["time_utc"]).replace(tzinfo=timezone.utc)
            if abs((t - now).total_seconds()) <= C.NEWS_BLACKOUT_MIN * 60:
                return True, f"news {row['currency']} {row.get('event', '')} à {t:%H:%M} UTC"
    return False, ""


class RiskManager:
    """Suit le capital de début de jour / de mois et décide si le bot a le droit de trader."""

    def __init__(self, path: Path = C.STATE_DIR / "risk_state.json"):
        self.path = path
        self.s = {"day": None, "day_equity": None, "month": None, "month_equity": None,
                  "halt_until": None, "halt_reason": "", "trades_today": 0}
        if path.exists():
            self.s.update(json.loads(path.read_text()))

    def _save(self):
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(json.dumps(self.s, indent=2))

    def update(self, equity: float, now: datetime) -> str:
        """À appeler à chaque cycle. Retourne un message si un arrêt vient d'être déclenché (sinon '')."""
        day, month = now.strftime("%Y-%m-%d"), now.strftime("%Y-%m")
        if self.s["day"] != day:
            self.s.update(day=day, day_equity=equity, trades_today=0)
        if self.s["month"] != month:
            self.s.update(month=month, month_equity=equity)
        msg = ""
        if not self.is_halted(now):
            d = 1 - equity / self.s["day_equity"]
            m = 1 - equity / self.s["month_equity"]
            if m >= MAX_MONTHLY_LOSS:
                first_next = (now.replace(day=1) + timedelta(days=32)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                msg = f"PERTE MENSUELLE {m:.1%} >= {MAX_MONTHLY_LOSS:.0%} : arrêt jusqu'au mois prochain"
                self.s.update(halt_until=first_next.isoformat(), halt_reason=msg)
            elif d >= MAX_DAILY_LOSS:
                tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                msg = f"PERTE JOURNALIÈRE {d:.1%} >= {MAX_DAILY_LOSS:.0%} : arrêt jusqu'à demain"
                self.s.update(halt_until=tomorrow.isoformat(), halt_reason=msg)
        self._save()
        return msg

    def is_halted(self, now: datetime) -> bool:
        h = self.s["halt_until"]
        return bool(h) and now.replace(tzinfo=None) < datetime.fromisoformat(h).replace(tzinfo=None)

    def can_open(self, symbol: str, now: datetime, open_count: int, sl, spread_pips: float, normal_spread_pips: float):
        """Toutes les vérifications avant ouverture. Retourne (ok, raison)."""
        spec = C.SYMBOLS[symbol.replace(C.SYMBOL_SUFFIX, "")]
        if sl is None or sl <= 0:
            return False, "stop-loss obligatoire"
        if self.is_halted(now):
            return False, self.s["halt_reason"]
        if open_count >= MAX_OPEN_TRADES:
            return False, f"{open_count} trades ouverts (max {MAX_OPEN_TRADES})"
        if self.s["trades_today"] >= C.MAX_TRADES_PER_DAY:
            return False, "max de trades par jour atteint"
        if spread_pips > C.MAX_SPREAD_MULT * normal_spread_pips:
            return False, f"spread anormal {spread_pips:.1f} pips"
        if not entry_mask(pd.DatetimeIndex([now.replace(tzinfo=None)]), spec)[0]:
            return False, "hors session / week-end"
        blocked, why = news_blocked(symbol.replace(C.SYMBOL_SUFFIX, ""), now)
        if blocked:
            return False, why
        return True, ""

    def register_open(self):
        self.s["trades_today"] += 1
        self._save()
