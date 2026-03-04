"""
Yahoo Finance data provider with caching support.
Fetches historical market data using yfinance library.
"""
from datetime import datetime
from typing import Optional

import pandas as pd
import yfinance as yf

from .base import BaseDataProvider
from .cache import DataCache


class YFinanceProvider(BaseDataProvider):
    """
    Data provider using Yahoo Finance API.
    
    Handles stock splits and dividends by using adjusted close prices.
    Caches all data locally in Parquet format.
    """
    
    # Map our timeframe to yfinance interval
    TIMEFRAME_MAP = {
        '1m': '1m',
        '5m': '5m',
        '15m': '15m',
        '30m': '30m',
        '1h': '1h',
        '1d': '1d',
        '1wk': '1wk',
        '1mo': '1mo',
    }
    
    def __init__(self, cache: Optional[DataCache] = None):
        super().__init__(cache)
        self._cache = cache if cache else DataCache()
    
    @property
    def name(self) -> str:
        return "yfinance"
    
    def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Get OHLCV bars from Yahoo Finance.
        
        Args:
            symbol: Stock symbol (e.g., 'AAPL')
            timeframe: Timeframe (e.g., '1d', '1h', '5m')
            start_date: Start date for data retrieval
            end_date: End date for data retrieval (default: now)
            
        Returns:
            DataFrame with columns [timestamp, open, high, low, close, volume]
        """
        # Check cache first
        cached = self._cache.get_cached_bars(
            provider=self.name,
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
        )
        if cached is not None and not cached.empty:
            return cached
        
        # Map timeframe
        interval = self.TIMEFRAME_MAP.get(timeframe, '1d')
        
        # Set default dates
        if end_date is None:
            end_date = datetime.now()
        if start_date is None:
            # Default to 2 years for daily data
            start_date = datetime(end_date.year - 2, end_date.month, end_date.day)
        
        # Fetch from yfinance
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(
                start=start_date,
                end=end_date,
                interval=interval,
                auto_adjust=True,  # Handle splits and dividends
                actions=False,  # Don't need dividends/splits data
            )
        except Exception as e:
            print(f"Error fetching {symbol} from yfinance: {e}")
            return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        if df.empty:
            return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Convert to our format
        df = df.reset_index()
        
        # Handle timezone - yfinance returns timezone-aware timestamps
        if df['Date'].dt.tz is not None:
            df['Date'] = df['Date'].dt.tz_localize(None)
        
        df = df.rename(columns={
            'Date': 'timestamp',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume',
        })
        
        # Select and order columns
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        
        # Ensure correct types
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Save to cache
        self._cache.save_bars(
            provider=self.name,
            symbol=symbol,
            timeframe=timeframe,
            df=df,
            merge=True,
        )
        
        # Return filtered data if dates specified
        result = df.copy()
        if start_date is not None:
            result = result[result['timestamp'] >= pd.to_datetime(start_date)]
        if end_date is not None:
            result = result[result['timestamp'] <= pd.to_datetime(end_date)]
        
        return result
