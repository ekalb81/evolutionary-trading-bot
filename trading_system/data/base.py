"""
Base data provider interface for the evolutionary trading system.
All data providers must implement this interface.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

import pandas as pd


class BaseDataProvider(ABC):
    """
    Abstract base class for data providers.
    
    All data providers must implement the get_bars method
    returning standardized OHLCV data.
    """
    
    def __init__(self, cache=None):
        """
        Initialize the data provider.
        
        Args:
            cache: Optional DataCache instance for caching
        """
        self.cache = cache
    
    @abstractmethod
    def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Get OHLCV bars for a symbol.
        
        Args:
            symbol: Stock symbol (e.g., 'AAPL', 'MSFT')
            timeframe: Timeframe (e.g., '1d', '1h', '5m', '1m')
            start_date: Start date for data retrieval
            end_date: End date for data retrieval
            
        Returns:
            DataFrame with columns:
                - timestamp: Datetime index
                - open: Opening price
                - high: High price
                - low: Low price
                - close: Closing price
                - volume: Trading volume
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the provider name."""
        pass
    
    def get_multiple_bars(
        self,
        symbols: list[str],
        timeframe: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict[str, pd.DataFrame]:
        """
        Get bars for multiple symbols.
        
        Args:
            symbols: List of stock symbols
            timeframe: Timeframe
            start_date: Start date
            end_date: End date
            
        Returns:
            Dictionary mapping symbol to DataFrame
        """
        result = {}
        for symbol in symbols:
            df = self.get_bars(symbol, timeframe, start_date, end_date)
            if df is not None and not df.empty:
                result[symbol] = df
        return result
