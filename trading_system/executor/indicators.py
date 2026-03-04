"""
Real-time Indicator Computation for Trading Daemon.

Maintains a rolling window of OHLCV data and computes indicators on-demand.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from collections import deque
import logging

logger = logging.getLogger(__name__)

# Global price history buffers (per symbol)
# In production, this might live in the Engine or a shared state object
_PRICE_HISTORY: Dict[str, deque] = {}
_INITIALIZED_SYMBOLS: set()

# Lookback buffer size (enough for longest indicator period)
MAX_BARS_LOOKBACK = 100


def _ensure_history(symbol: str, broker=None) -> Optional[pd.DataFrame]:
    """
    Ensure we have price history for the symbol.
    If empty, fetch last 100 bars from yfinance (preferred) or broker.
    """
    global _PRICE_HISTORY
    
    if symbol in _PRICE_HISTORY and len(_PRICE_HISTORY[symbol]) >= 20:
        # We already have sufficient history
        return _get_dataframe(symbol)
    
    # Need to initialize
    logger.info(f"[Indicators] Initializing price history for {symbol}...")
    
    # Prefer yfinance for historical data (Alpaca paper trading often returns only 1 bar)
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="6mo")
        if not hist.empty:
            _PRICE_HISTORY[symbol] = deque()
            for idx, row in hist.iterrows():
                _PRICE_HISTORY[symbol].append({
                    "timestamp": idx.isoformat(),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": int(row["Volume"])
                })
            logger.info(f"[Indicators] Fetched {len(_PRICE_HISTORY[symbol])} bars from yfinance for {symbol}")
            return _get_dataframe(symbol)
    except Exception as e:
        logger.warning(f"[Indicators] yfinance failed: {e}")
    
    # Fallback: try broker (Alpaca)
    if broker:
        try:
            bars = broker.get_bars(symbol, limit=100, timeframe="1Day")
            if bars and len(bars) > 1:
                _PRICE_HISTORY[symbol] = deque()
                for bar in bars:
                    _PRICE_HISTORY[symbol].append({
                        "timestamp": bar.get("t") or bar.get("timestamp"),
                        "open": float(bar.get("o", bar.get("open"))),
                        "high": float(bar.get("h", bar.get("high"))),
                        "low": float(bar.get("l", bar.get("low"))),
                        "close": float(bar.get("c", bar.get("close"))),
                        "volume": int(bar.get("v", bar.get("volume", 0)))
                    })
                logger.info(f"[Indicators] Fetched {len(_PRICE_HISTORY[symbol])} bars from broker for {symbol}")
                return _get_dataframe(symbol)
            else:
                logger.warning(f"[Indicators] Broker returned insufficient bars: {len(bars) if bars else 0}")
        except Exception as e:
            logger.warning(f"[Indicators] Failed to fetch from broker: {e}")
    
    logger.error(f"[Indicators] Could not initialize history for {symbol}")
    return None


def _get_dataframe(symbol: str) -> pd.DataFrame:
    """Convert deque to DataFrame for indicator calculation."""
    global _PRICE_HISTORY
    if symbol not in _PRICE_HISTORY:
        return pd.DataFrame()
    return pd.DataFrame(list(_PRICE_HISTORY[symbol]))


def add_sma(df: pd.DataFrame, col_name: str, source: str, period: int) -> pd.DataFrame:
    if source not in df.columns or df.empty:
        return df
    df[col_name] = df[source].rolling(window=period).mean()
    return df


def add_ema(df: pd.DataFrame, col_name: str, source: str, period: int) -> pd.DataFrame:
    if source not in df.columns or df.empty:
        return df
    df[col_name] = df[source].ewm(span=period, adjust=False).mean()
    return df


def add_rsi(df: pd.DataFrame, col_name: str, source: str, period: int) -> pd.DataFrame:
    if source not in df.columns or df.empty:
        return df
    delta = df[source].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    df[col_name] = 100 - (100 / (1 + rs))
    return df


def add_macd(df: pd.DataFrame, col_name: str, source: str, fast_period: int, slow_period: int, signal_period: int) -> pd.DataFrame:
    if source not in df.columns or df.empty:
        return df
    fast_ema = df[source].ewm(span=fast_period, adjust=False).mean()
    slow_ema = df[source].ewm(span=slow_period, adjust=False).mean()
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    df[col_name] = macd_line
    df[col_name + "_signal"] = signal_line
    df[col_name + "_hist"] = macd_line - signal_line
    return df


def add_atr(df: pd.DataFrame, col_name: str, period: int) -> pd.DataFrame:
    if "high" not in df.columns or df.empty:
        return df
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df[col_name] = tr.rolling(window=period).mean()
    return df


def add_bb(df: pd.DataFrame, col_name: str, source: str, period: int, std_dev: float) -> pd.DataFrame:
    if source not in df.columns or df.empty:
        return df
    sma = df[source].rolling(window=period).mean()
    std = df[source].rolling(window=period).std()
    # Store lower band as main value (for comparison in rules)
    df[col_name] = sma - (std * std_dev)
    df[col_name + "_upper"] = sma + (std * std_dev)
    df[col_name + "_middle"] = sma
    df[col_name + "_lower"] = sma - (std * std_dev)
    return df


def add_stoch(df: pd.DataFrame, col_name: str, k_period: int, d_period: int) -> pd.DataFrame:
    if "low" not in df.columns or df.empty:
        return df
    low_min = df['low'].rolling(window=k_period).min()
    high_max = df['high'].rolling(window=k_period).max()
    k = 100 * (df['close'] - low_min) / (high_max - low_min)
    d = k.rolling(window=d_period).mean()
    df[col_name] = k
    df[col_name + "_d"] = d
    return df


def compute_indicators(market_data: dict, indicators_def: list, symbol: str = None, broker=None) -> dict:
    """
    Compute indicator values for real-time trading.
    
    Maintains a rolling window of price history per symbol.
    If history is empty, initializes from broker or yfinance.
    
    Args:
        market_data: dict with {open, high, low, close, volume, timestamp}
        indicators_def: list of {id, type, params} definitions
        symbol: (optional) ticker symbol to maintain history for
        broker: (optional) broker instance to fetch initial history
    
    Returns:
        dict mapping indicator_id -> current value
    """
    global _PRICE_HISTORY
    
    # Extract symbol from market_data if not provided
    if not symbol and "symbol" in market_data:
        symbol = market_data["symbol"]
    
    if not symbol:
        logger.warning("[Indicators] No symbol provided, cannot compute real-time indicators")
        return {}
    
    # Update history buffer with latest bar if available
    if "close" in market_data:
        if symbol not in _PRICE_HISTORY:
            _PRICE_HISTORY[symbol] = deque(maxlen=MAX_BARS_LOOKBACK)
        
        # Only add if timestamp is newer than last bar (avoid duplicates)
        new_bar = {
            "timestamp": market_data.get("timestamp"),
            "open": market_data.get("open"),
            "high": market_data.get("high"),
            "low": market_data.get("low"),
            "close": market_data.get("close"),
            "volume": market_data.get("volume", 0)
        }
        
        # Add if we don't have history or new close is different from last
        if not _PRICE_HISTORY[symbol] or new_bar["close"] != list(_PRICE_HISTORY[symbol])[-1]["close"]:
            _PRICE_HISTORY[symbol].append(new_bar)
    
    # Ensure we have enough history (seed if empty)
    df = _ensure_history(symbol, broker)
    if df is None or df.empty:
        logger.warning(f"[Indicators] No price history available for {symbol}")
        return {}
    
    # Make a copy so we don't mutate the cached buffer
    df = df.copy()
    
    # Compute each indicator
    for ind in indicators_def:
        ind_id = ind.get("id")
        ind_type = ind.get("type", "").upper()
        params = ind.get("params", {})
        
        if ind_type == "SMA":
            add_sma(df, ind_id, "close", params.get("period", 14))
        elif ind_type == "EMA":
            add_ema(df, ind_id, "close", params.get("period", 14))
        elif ind_type == "RSI":
            add_rsi(df, ind_id, "close", params.get("period", 14))
        elif ind_type == "MACD":
            add_macd(df, ind_id, "close", 
                     params.get("fast_period", 12), 
                     params.get("slow_period", 26), 
                     params.get("signal_period", 9))
        elif ind_type == "ATR":
            add_atr(df, ind_id, params.get("period", 14))
        elif ind_type in ("BB", "BBANDS"):
            add_bb(df, ind_id, "close", params.get("period", 20), params.get("std_dev", 2.0))
        elif ind_type == "STOCH":
            add_stoch(df, ind_id, params.get("k_period", 14), params.get("d_period", 3))
    
    # Return latest values only
    result = {}
    if not df.empty:
        last_row = df.iloc[-1]
        for ind in indicators_def:
            ind_id = ind.get("id")
            if ind_id in df.columns:
                val = last_row.get(ind_id)
                if pd.notna(val):
                    result[ind_id] = float(val)
            
            # Also include BBANDS sub-values
            if ind.get("type", "").upper() in ("BB", "BBANDS"):
                for suffix in ["_upper", "_middle", "_lower"]:
                    col = ind_id + suffix
                    if col in df.columns:
                        val = last_row.get(col)
                        if pd.notna(val):
                            result[col] = float(val)
    
    return result
