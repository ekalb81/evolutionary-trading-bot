import pandas as pd
import numpy as np

def add_sma(df, col_name, source, period):
    df[col_name] = df[source].rolling(window=period).mean()

def add_ema(df, col_name, source, period):
    df[col_name] = df[source].ewm(span=period, adjust=False).mean()

def add_rsi(df, col_name, source, period):
    delta = df[source].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    # Simple moving average for first value, then Wilder's smoothing (EMA)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    df[col_name] = 100 - (100 / (1 + rs))

def add_macd(df, col_name, source, fast_period, slow_period, signal_period):
    fast_ema = df[source].ewm(span=fast_period, adjust=False).mean()
    slow_ema = df[source].ewm(span=slow_period, adjust=False).mean()
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    df[col_name] = macd_line # Usually we might need the histogram or signal, but let's provide the main line
    df[col_name + "_signal"] = signal_line
    # If genome uses value_type="oscillator" we assume we give back the macd line

def add_atr(df, col_name, period):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df[col_name] = tr.rolling(window=period).mean()

def add_bb(df, col_name, source, period, std_dev):
    sma = df[source].rolling(window=period).mean()
    std = df[source].rolling(window=period).std()
    
    # BB usually returns upper, middle, lower. Let's return lower as the main if used in condition?
    # In genome template generated: "Price below lower BB (BB value is the lower band)"
    df[col_name] = sma - (std * std_dev) 
    df[col_name + "_upper"] = sma + (std * std_dev)
    df[col_name + "_middle"] = sma

def add_stoch(df, col_name, k_period, d_period):
    low_min = df['low'].rolling(window=k_period).min()
    high_max = df['high'].rolling(window=k_period).max()
    
    k = 100 * (df['close'] - low_min) / (high_max - low_min)
    d = k.rolling(window=d_period).mean()
    
    df[col_name] = k
    df[col_name + "_d"] = d

def compute_indicator(df, indicator_def):
    ind_type = indicator_def['type']
    ind_id = indicator_def['id']
    params = indicator_def['params']
    
    source = 'close' # Default to close unless otherwise specified
    
    if ind_type == 'SMA':
        add_sma(df, ind_id, source, params['period'])
    elif ind_type == 'EMA':
        add_ema(df, ind_id, source, params['period'])
    elif ind_type == 'RSI':
        add_rsi(df, ind_id, source, params['period'])
    elif ind_type == 'MACD':
        add_macd(df, ind_id, source, params['fast_period'], params['slow_period'], params['signal_period'])
    elif ind_type == 'ATR':
        add_atr(df, ind_id, params['period'])
    elif ind_type == 'BB':
        add_bb(df, ind_id, source, params['period'], params['std_dev'])
    elif ind_type == 'STOCH':
        add_stoch(df, ind_id, params['k_period'], params['d_period'])
