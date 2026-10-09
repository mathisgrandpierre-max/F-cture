"""data_tools.py - Chargement / sauvegarde des historiques CSV."""
import pandas as pd

import config as C


def load_csv(symbol: str) -> pd.DataFrame:
    """Colonnes attendues : time (UTC), open, high, low, close, [spread en points]."""
    df = pd.read_csv(C.DATA_DIR / f"{symbol}_{C.TIMEFRAME}.csv", parse_dates=["time"], index_col="time")
    return df[~df.index.duplicated()].sort_index()


def save_csv(symbol: str, df: pd.DataFrame):
    C.DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(C.DATA_DIR / f"{symbol}_{C.TIMEFRAME}.csv")
