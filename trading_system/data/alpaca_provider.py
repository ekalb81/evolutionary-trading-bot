"""
Alpaca data provider with caching support.
Fetches real-time and historical market data using Alpaca API.
"""
import os
from datetime import datetime
from typing import Optional

import pandas as pd

from .base import BaseDataProvider
from .cache import DataCache


class AlpacaDataProvider(BaseDataProvider):
    """
    Data provider using Alpaca API.
    
    Supports both paper trading and live data.
    Caches data locally for backtesting replay.
    """
    
    TIMEFRAME_MAP = {
        '1m': '1Min',
        '5m': '5Min',
        '15m': '15Min',
        '30m': '30Min',
        '1h': '1Hour',
        '1d': '1Day',
    }
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        base_url: Optional[str] = None,
        cache: Optional[DataCache] = None,
    ):
        """
        Initialize Alpaca data provider.
        
        Args:
            api_key: Alpaca API key (or env var ALPACA_API_KEY)
            secret_key: Alpaca secret key (or env var ALPACA_SECRET_KEY)
            base_url: API base URL (paper: https://paper-api.alpaca.markets, live: https://api.alpaca.markets)
            cache: Optional DataCache instance
        """
        super().__init__(cache)
        self._cache = cache if cache else DataCache()
        
        # Get credentials from env if not provided
        self.api_key = api_key or os.getenv('ALPACA_API_KEY')
        self.secret_key = secret_key or os.getenv('ALPACA_SECRET_KEY')
        self.base_url = base_url or os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
        
        self._client = None
    
    @property
    def name(self) -> str:
        return "alpaca"
    
    def _get_client(self):
        """Lazy initialization of Alpaca client."""
        if self._client is not None:
            return self._client
        
        if not self.api_key or not self.secret_key:
            raise ValueError(
                "Alpaca API credentials not provided. "
                "Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables "
                "or pass them to the constructor."
            )
        
        try:
            import alpaca
            from alpaca.data import CryptoDataClient, StockDataClient
            from alpaca.data.enums import Adjustment
        except ImportError:
            raise ImportError("alpaca-py package not installed. Run: pip install alpaca-py")
        
        # Use StockDataClient for equities
        self._client = StockDataClient(
            self.api_key,
            self.secret_key,
        )
        
        return self._client
    
    def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        adjustment: str = 'split',  # split, dividend, all, none
    ) -> pd.DataFrame:
        """
        Get OHLCV bars from Alpaca.
        
        Args:
            symbol: Stock symbol (e.g., 'AAPL')
            timeframe: Timeframe (e.g., '1d', '1h', '5m')
            start_date: Start date for data retrieval
            end_date: End date for data retrieval (default: now)
            adjustment: Adjustment type ('split', 'dividend', 'all', 'none')
            
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
        
        # Get client
        try:
            client = self._get_client()
        except ValueError as e:
            print(f"Alpaca credentials error: {e}")
            return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Map timeframe
        alpaca_tf = self.TIMEFRAME_MAP.get(timeframe, '1Day')
        
        # Set default dates
        if end_date is None:
            end_date = datetime.now()
        if start_date is None:
            start_date = datetime(end_date.year - 2, end_date.month, end_date.day)
        
        # Fetch from Alpaca
        try:
            from alpaca.data import StockBarsRequest
            from alpaca.data.enums import Adjustment
            
            # Map adjustment
            adj_map = {
                'split': Adjustment.SPLIT,
                'dividend': Adjustment.DIVIDEND,
                'all': Adjustment.ALL,
                'none': Adjustment.NONE,
            }
            
            request = StockBarsRequest(
                symbol_or_symbols=[symbol],
                timeframe=alpaca_tf,
                start=start_date,
                end=end_date,
                adjustment=adj_map.get(adjustment, Adjustment.ALL),
                limit=10000,  # Max allowed
            )
            
            response = client.get_stock_bars(request)
            
            # Convert to DataFrame
            if hasattr(response, 'data') and symbol in response.data:
                df_data = response.data[symbol]
                if not df_data:
                    return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                
                # Convert bars to records
                records = []
                for bar in df_data:
                    records.append({
                        'timestamp': bar.timestamp,
                        'open': bar.open,
                        'high': bar.high,
                        'low': bar.low,
                        'close': bar.close,
                        'volume': bar.volume,
                    })
                df = pd.DataFrame(records)
            else:
                return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                
        except Exception as e:
            print(f"Error fetching {symbol} from Alpaca: {e}")
            return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        if df.empty:
            return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Handle timezone - Alpaca returns timezone-aware timestamps (ET)
        if df['timestamp'].dt.tz is not None:
            df['timestamp'] = df['timestamp'].dt.tz_localize(None)
        
        # Ensure correct types
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Select and order columns
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        
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
    
    def get_latest_quote(self, symbol: str) -> Optional[dict]:
        """
        Get latest quote for a symbol (real-time).
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dictionary with quote data or None
        """
        try:
            client = self._get_client()
            from alpaca.data import LatestQuoteRequest
            
            request = LatestQuoteRequest(symbol_or_symbols=[symbol])
            response = client.get_latest_quote(request)
            
            if symbol in response.data:
                quote = response.data[symbol]
                return {
                    'symbol': symbol,
                    'bid_price': quote.bid_price,
                    'ask_price': quote.ask_price,
                    'bid_size': quote.bid_size,
                    'ask_size': quote.ask_size,
                    'timestamp': quote.timestamp,
                }
        except Exception as e:
            print(f"Error fetching latest quote for {symbol}: {e}")
        
        return None
