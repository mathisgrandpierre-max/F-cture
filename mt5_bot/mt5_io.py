"""
mt5_io.py - Tout ce qui parle à MetaTrader 5 (paquet Python 'MetaTrader5', Windows uniquement).
⚠️ Ce module n'a pas pu être testé contre un vrai terminal MT5 dans l'environnement où il a été écrit :
   teste-le d'abord en démo avec 0,01 lot (voir GUIDE.md, étape 'premier test').
"""
import logging
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

import config as C

log = logging.getLogger("bot")
mt5 = None


def connect():
    """Se connecte au terminal MT5 déjà ouvert et REFUSE tout compte réel."""
    global mt5
    import MetaTrader5 as _mt5
    mt5 = _mt5
    if not mt5.initialize():
        raise RuntimeError(f"Connexion MT5 impossible: {mt5.last_error()} (terminal ouvert ? trading algo activé ?)")
    acc = mt5.account_info()
    if acc.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO and not C.ALLOW_REAL_ACCOUNT:
        mt5.shutdown()
        raise RuntimeError("Compte RÉEL détecté : refus (ALLOW_REAL_ACCOUNT=False). Ce bot est limité à la démo.")
    if not mt5.terminal_info().trade_allowed:
        raise RuntimeError("Le bouton 'Algo Trading' est désactivé dans MT5.")
    log.info("Connecté: compte %s (%s) %s %.2f", acc.login, acc.server, acc.currency, acc.balance)
    return acc


def broker_symbol(symbol: str) -> str:
    s = symbol + C.SYMBOL_SUFFIX
    mt5.symbol_select(s, True)
    return s


def server_offset_hours(symbol: str) -> int:
    """Décalage heure serveur - UTC, déduit du dernier tick (gère le changement d'heure été/hiver)."""
    tick = mt5.symbol_info_tick(broker_symbol(symbol))
    if tick is None or time.time() - tick.time > 6 * 3600 + 3 * 86400:
        return C.SERVER_UTC_OFFSET_HOURS
    off = round((tick.time - time.time()) / 3600)
    return off if -1 <= off <= 4 else C.SERVER_UTC_OFFSET_HOURS


def _to_df(rates, symbol) -> pd.DataFrame:
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s") - pd.Timedelta(hours=server_offset_hours(symbol))
    return df.set_index("time")[["open", "high", "low", "close", "spread"]]


def fetch_history(symbol: str, years: int = C.HISTORY_YEARS) -> pd.DataFrame:
    """Historique H1 des 'years' dernières années (heure convertie en UTC)."""
    tf = getattr(mt5, f"TIMEFRAME_{C.TIMEFRAME}")
    end = datetime.now(timezone.utc) + timedelta(days=1)
    rates = mt5.copy_rates_range(broker_symbol(symbol), tf, end - timedelta(days=365 * years), end)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"Pas d'historique pour {symbol}: {mt5.last_error()}")
    return _to_df(rates, symbol)


def recent_closed_bars(symbol: str, n: int = 600) -> pd.DataFrame:
    """Les n dernières bougies CLÔTURÉES (la bougie en cours est exclue)."""
    tf = getattr(mt5, f"TIMEFRAME_{C.TIMEFRAME}")
    rates = mt5.copy_rates_from_pos(broker_symbol(symbol), tf, 0, n + 1)
    if rates is None:
        raise RuntimeError(f"copy_rates_from_pos {symbol}: {mt5.last_error()}")
    return _to_df(rates, symbol).iloc[:-1]


def account():
    return mt5.account_info()


def my_positions():
    return [p for p in (mt5.positions_get() or []) if p.magic == C.MAGIC_NUMBER]


def symbol_info(symbol: str):
    return mt5.symbol_info(broker_symbol(symbol))


def tick(symbol: str):
    return mt5.symbol_info_tick(broker_symbol(symbol))


def margin_ok(symbol: str, direction: int, lots: float, price: float) -> bool:
    """Vérifie que la marge nécessaire reste sous MAX_MARGIN_USAGE de la marge libre."""
    typ = mt5.ORDER_TYPE_BUY if direction > 0 else mt5.ORDER_TYPE_SELL
    need = mt5.order_calc_margin(typ, broker_symbol(symbol), lots, price)
    return need is not None and need <= account().margin_free * C.MAX_MARGIN_USAGE


def open_market(symbol: str, direction: int, lots: float, sl: float, tp: float = 0.0, comment: str = "bot"):
    """Ordre au marché AVEC stop-loss. Si le broker accepte l'ordre sans SL, on ferme immédiatement."""
    if not sl:
        raise ValueError("stop-loss obligatoire")
    s = broker_symbol(symbol)
    t = mt5.symbol_info_tick(s)
    req = dict(action=mt5.TRADE_ACTION_DEAL, symbol=s, volume=lots,
               type=mt5.ORDER_TYPE_BUY if direction > 0 else mt5.ORDER_TYPE_SELL,
               price=t.ask if direction > 0 else t.bid, sl=sl, tp=tp, deviation=20,
               magic=C.MAGIC_NUMBER, comment=comment[:30], type_time=mt5.ORDER_TIME_GTC,
               type_filling=_filling(s))
    res = mt5.order_send(req)
    if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
        log.error("Ordre refusé %s: %s", symbol, res)
        return None
    pos = next((p for p in my_positions() if p.ticket == res.order or p.identifier == res.order), None)
    if pos is not None and not pos.sl:
        log.error("Position sans SL détectée -> fermeture immédiate")
        close_position(pos)
        return None
    return res


def _filling(s):
    mode = mt5.symbol_info(s).filling_mode
    return mt5.ORDER_FILLING_FOK if mode & 1 else mt5.ORDER_FILLING_IOC if mode & 2 else mt5.ORDER_FILLING_RETURN


def close_position(pos):
    t = mt5.symbol_info_tick(pos.symbol)
    buy = pos.type == mt5.POSITION_TYPE_BUY
    req = dict(action=mt5.TRADE_ACTION_DEAL, symbol=pos.symbol, volume=pos.volume, position=pos.ticket,
               type=mt5.ORDER_TYPE_SELL if buy else mt5.ORDER_TYPE_BUY, price=t.bid if buy else t.ask,
               deviation=20, magic=C.MAGIC_NUMBER, comment="close", type_time=mt5.ORDER_TIME_GTC,
               type_filling=_filling(pos.symbol))
    res = mt5.order_send(req)
    ok = res is not None and res.retcode == mt5.TRADE_RETCODE_DONE
    if not ok:
        log.error("Fermeture refusée %s: %s", pos.symbol, res)
    return ok


def closed_position_result(position_id: int):
    """Résultat réel d'une position clôturée (profit + commission + swap) et prix/heure de sortie."""
    deals = mt5.history_deals_get(position=position_id) or []
    if len(deals) < 2:
        return None
    out = deals[-1]
    pnl = sum(d.profit + d.commission + d.swap + d.fee for d in deals)
    reason = {mt5.DEAL_REASON_SL: "SL", mt5.DEAL_REASON_TP: "TP"}.get(out.reason, "signal/manuel")
    return dict(pnl=pnl, exit=out.price, exit_time=datetime.fromtimestamp(out.time, timezone.utc).replace(tzinfo=None), reason=reason)
