#!/usr/bin/env python3
"""
Bot de trading DEMO (paper trading) multi-stratégies, piloté par Claude.

- Tourne en continu, trade uniquement pendant les heures de marché US.
- Chaque stratégie a un portefeuille virtuel -> comparaison équitable en parallèle.
- La stratégie la plus performante (rendement ajusté du drawdown) est "copiée"
  sur ton compte Alpaca PAPER (argent fictif).
- Arrêt à tout moment : Ctrl+C, ou `python bot.py stop` (depuis un autre terminal).

Commandes :
    python bot.py run        # lance le bot
    python bot.py stop       # demande l'arrêt propre
    python bot.py status     # affiche le classement
    python bot.py flatten    # ferme toutes les positions du compte paper
    python bot.py reset      # efface l'état (repart de zéro)
"""
import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# ----------------------------- CONFIG ---------------------------------------
SYMBOLS = [s.strip() for s in os.getenv("SYMBOLS", "SPY,QQQ,AAPL,MSFT,NVDA").split(",")]
START_CASH = float(os.getenv("START_CASH", 10_000))        # capital virtuel / stratégie
MAX_POS_PCT = float(os.getenv("MAX_POS_PCT", 0.20))        # max 20 % du capital par ligne
SLIPPAGE = 0.0005                                          # 0,05 % de frais/slippage simulés
BAR_MINUTES = int(os.getenv("BAR_MINUTES", 15))
LOOP_SECONDS = int(os.getenv("LOOP_SECONDS", 60))
MIN_TRADES_TO_RANK = int(os.getenv("MIN_TRADES_TO_RANK", 10))  # évite de classer sur la chance
MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", 0.03))      # coupe-circuit : -3 %/jour
MIRROR_LEADER = os.getenv("MIRROR_LEADER", "true").lower() == "true"
ENABLE_CLAUDE = os.getenv("ENABLE_CLAUDE", "true").lower() == "true"
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")

BASE = Path(__file__).parent
STOP_FILE = BASE / "STOP"
STATE_FILE = BASE / "state.json"
LOG_FILE = BASE / "bot.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger("bot")


# ----------------------------- PORTEFEUILLE VIRTUEL -------------------------
@dataclass
class Portfolio:
    name: str
    cash: float = START_CASH
    positions: dict = field(default_factory=dict)   # symbol -> qty
    n_trades: int = 0
    peak: float = START_CASH
    max_dd: float = 0.0
    last_prices: dict = field(default_factory=dict)

    def equity(self) -> float:
        return self.cash + sum(q * self.last_prices.get(s, 0) for s, q in self.positions.items())

    def mark(self, prices: dict):
        self.last_prices.update(prices)
        eq = self.equity()
        self.peak = max(self.peak, eq)
        self.max_dd = max(self.max_dd, (self.peak - eq) / self.peak)

    def buy(self, sym: str, price: float):
        if sym in self.positions:
            return
        budget = min(self.cash, self.equity() * MAX_POS_PCT)
        if budget < 10:
            return
        px = price * (1 + SLIPPAGE)
        qty = budget / px
        self.cash -= qty * px
        self.positions[sym] = qty
        self.n_trades += 1

    def sell(self, sym: str, price: float):
        qty = self.positions.pop(sym, 0)
        if qty:
            self.cash += qty * price * (1 - SLIPPAGE)
            self.n_trades += 1

    def ret(self) -> float:
        return self.equity() / START_CASH - 1

    def score(self) -> float | None:
        if self.n_trades < MIN_TRADES_TO_RANK:
            return None
        return self.ret() - 0.5 * self.max_dd   # pénalise les gros drawdowns


# ----------------------------- INDICATEURS ----------------------------------
def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, 1e-9))


# ----------------------------- STRATÉGIES -----------------------------------
# Chaque stratégie : f(sym, close: Series, in_pos: bool) -> "buy" | "sell" | "hold"
def strat_sma_cross(sym, close, in_pos):
    fast, slow = close.rolling(10).mean(), close.rolling(30).mean()
    if len(close) < 31:
        return "hold"
    if fast.iloc[-1] > slow.iloc[-1] and not in_pos:
        return "buy"
    if fast.iloc[-1] < slow.iloc[-1] and in_pos:
        return "sell"
    return "hold"


def strat_rsi_reversion(sym, close, in_pos):
    if len(close) < 20:
        return "hold"
    r = rsi(close).iloc[-1]
    if r < 30 and not in_pos:
        return "buy"
    if r > 55 and in_pos:
        return "sell"
    return "hold"


def strat_breakout(sym, close, in_pos):
    if len(close) < 25:
        return "hold"
    hi, lo = close.iloc[-21:-1].max(), close.iloc[-11:-1].min()
    if close.iloc[-1] > hi and not in_pos:
        return "buy"
    if close.iloc[-1] < lo and in_pos:
        return "sell"
    return "hold"


_claude_client = None
_claude_cache: dict = {}


def strat_claude(sym, close, in_pos):
    """Claude analyse les derniers prix et répond buy/sell/hold (JSON)."""
    global _claude_client
    key = (sym, str(close.index[-1]))
    if key in _claude_cache:
        return _claude_cache[key]
    try:
        if _claude_client is None:
            import anthropic
            _claude_client = anthropic.Anthropic()
        closes = [round(x, 2) for x in close.tail(40).tolist()]
        prompt = (
            f"Tu es un moteur de décision pour un bot de PAPER TRADING (argent fictif).\n"
            f"Symbole: {sym}. Barres de {BAR_MINUTES} min, 40 dernières clôtures: {closes}.\n"
            f"Position ouverte: {in_pos}.\n"
            f"Si aucune position: réponds buy ou hold. Si position: sell ou hold.\n"
            f'Réponds UNIQUEMENT en JSON: {{"action":"buy|sell|hold","reason":"<10 mots"}}'
        )
        msg = _claude_client.messages.create(
            model=CLAUDE_MODEL, max_tokens=80,
            messages=[{"role": "user", "content": prompt}],
        )
        txt = msg.content[0].text.strip().strip("`").replace("json", "", 1)
        action = json.loads(txt).get("action", "hold")
        action = action if action in ("buy", "sell", "hold") else "hold"
    except Exception as e:
        log.warning("Claude indisponible (%s) -> hold", e)
        action = "hold"
    _claude_cache[key] = action
    return action


STRATEGIES = {
    "sma_cross": strat_sma_cross,
    "rsi_reversion": strat_rsi_reversion,
    "breakout": strat_breakout,
}
if ENABLE_CLAUDE:
    STRATEGIES["claude"] = strat_claude


# ----------------------------- ÉTAT -----------------------------------------
def load_state() -> dict:
    if STATE_FILE.exists():
        raw = json.loads(STATE_FILE.read_text())
        return {n: Portfolio(**p) for n, p in raw["portfolios"].items() if n in STRATEGIES} | {
            n: Portfolio(name=n) for n in STRATEGIES if n not in raw["portfolios"]
        }
    return {n: Portfolio(name=n) for n in STRATEGIES}


def save_state(pf: dict):
    STATE_FILE.write_text(json.dumps({"portfolios": {n: asdict(p) for n, p in pf.items()}}, indent=2))


def leaderboard(pf: dict) -> list:
    rows = sorted(pf.values(), key=lambda p: (p.score() is None, -(p.score() or 0), -p.ret()))
    return rows


def print_board(pf: dict):
    print("\n=== CLASSEMENT (paper) ===")
    for i, p in enumerate(leaderboard(pf), 1):
        s = p.score()
        print(f"{i}. {p.name:14} equity={p.equity():>10.2f}  ret={p.ret()*100:+6.2f}%  "
              f"maxDD={p.max_dd*100:5.2f}%  trades={p.n_trades:3d}  "
              f"{'score=%.3f' % s if s is not None else '(pas assez de trades)'}")


def current_leader(pf: dict) -> Portfolio | None:
    for p in leaderboard(pf):
        if p.score() is not None:
            return p
    return None


# ----------------------------- ALPACA (PAPER UNIQUEMENT) --------------------
def clients():
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.trading.client import TradingClient
    key, sec = os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"]
    # paper=True est codé en dur : le bot ne peut PAS toucher un compte réel.
    return TradingClient(key, sec, paper=True), StockHistoricalDataClient(key, sec)


def fetch_bars(data_client) -> dict:
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    from alpaca.data.enums import DataFeed
    req = StockBarsRequest(
        symbol_or_symbols=SYMBOLS,
        timeframe=TimeFrame(BAR_MINUTES, TimeFrameUnit.Minute),
        start=datetime.now(timezone.utc) - timedelta(days=10),
        feed=DataFeed.IEX,  # gratuit
    )
    df = data_client.get_stock_bars(req).df
    return {s: df.xs(s, level="symbol")["close"] for s in SYMBOLS if s in df.index.get_level_values("symbol")}


def sync_alpaca(trading, leader: Portfolio, prices: dict):
    """Aligne le compte paper Alpaca sur les positions de la stratégie leader."""
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    held = {p.symbol: p for p in trading.get_all_positions()}
    equity = float(trading.get_account().equity)
    for sym in SYMBOLS:
        want = sym in leader.positions
        have = sym in held
        if want and not have:
            notional = round(equity * MAX_POS_PCT, 2)
            trading.submit_order(MarketOrderRequest(
                symbol=sym, notional=notional, side=OrderSide.BUY, time_in_force=TimeInForce.DAY))
            log.info("PAPER BUY %s %.2f$ (leader=%s)", sym, notional, leader.name)
        elif have and not want:
            trading.close_position(sym)
            log.info("PAPER CLOSE %s (leader=%s)", sym, leader.name)


def daily_loss_breaker(trading) -> bool:
    acc = trading.get_account()
    loss = 1 - float(acc.equity) / float(acc.last_equity)
    if loss >= MAX_DAILY_LOSS:
        log.error("COUPE-CIRCUIT: -%.1f%% aujourd'hui -> fermeture + pause", loss * 100)
        trading.close_all_positions(cancel_orders=True)
        return True
    return False


# ----------------------------- BOUCLE PRINCIPALE ----------------------------
_running = True


def _handle_signal(*_):
    global _running
    _running = False
    log.info("Arrêt demandé (signal).")


def should_stop() -> bool:
    return (not _running) or STOP_FILE.exists()


def sleep_interruptible(seconds: int):
    for _ in range(seconds):
        if should_stop():
            return
        time.sleep(1)


def run():
    STOP_FILE.unlink(missing_ok=True)
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    trading, data = clients()
    pf = load_state()
    last_bar_ts = None
    paused_today = None
    log.info("Bot démarré (PAPER). Stratégies: %s | Symboles: %s", list(STRATEGIES), SYMBOLS)

    while not should_stop():
        try:
            clock = trading.get_clock()
            if not clock.is_open:
                log.info("Marché fermé. Prochaine ouverture: %s", clock.next_open)
                sleep_interruptible(300)
                continue
            if paused_today == datetime.now().date():
                sleep_interruptible(300)
                continue

            bars = fetch_bars(data)
            if not bars:
                sleep_interruptible(LOOP_SECONDS)
                continue
            ts = max(s.index[-1] for s in bars.values())
            if ts != last_bar_ts:                       # nouvelle barre -> on décide
                last_bar_ts = ts
                prices = {s: float(c.iloc[-1]) for s, c in bars.items()}
                for name, fn in STRATEGIES.items():
                    p = pf[name]
                    for sym, close in bars.items():
                        sig = fn(sym, close, sym in p.positions)
                        if sig == "buy":
                            p.buy(sym, prices[sym])
                        elif sig == "sell":
                            p.sell(sym, prices[sym])
                    p.mark(prices)
                save_state(pf)
                print_board(pf)
                leader = current_leader(pf)
                if MIRROR_LEADER and leader:
                    if daily_loss_breaker(trading):
                        paused_today = datetime.now().date()
                    else:
                        sync_alpaca(trading, leader, prices)
        except Exception as e:                           # le bot ne doit jamais mourir sur une erreur réseau
            log.exception("Erreur de cycle: %s", e)
            sleep_interruptible(30)
        sleep_interruptible(LOOP_SECONDS)

    save_state(pf)
    log.info("Bot arrêté proprement. Positions paper conservées (utilise `flatten` pour fermer).")


# ----------------------------- CLI ------------------------------------------
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "run":
        run()
    elif cmd == "stop":
        STOP_FILE.write_text("stop")
        print("Signal d'arrêt envoyé (fichier STOP créé).")
    elif cmd == "status":
        print_board(load_state())
    elif cmd == "flatten":
        clients()[0].close_all_positions(cancel_orders=True)
        print("Toutes les positions PAPER fermées.")
    elif cmd == "reset":
        STATE_FILE.unlink(missing_ok=True)
        STOP_FILE.unlink(missing_ok=True)
        print("État réinitialisé.")
    else:
        print(__doc__)
