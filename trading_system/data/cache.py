"""
Data caching layer for the evolutionary trading system.
Handles storage and retrieval of market data in Parquet format.
"""
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd


class DataCache:
    """
    Manages local caching of market data in Parquet format.
    
    Directory structure:
        data/
            raw/           # Raw API responses (future)
            processed/     # Cleaned Parquet files (cached bars)
    """
    
    def __init__(self, base_path: str = "data"):
        self.base_path = Path(base_path)
        self.processed_path = self.base_path / "processed"
        self.raw_path = self.base_path / "raw"
        
        # Ensure directories exist
        self.processed_path.mkdir(parents=True, exist_ok=True)
        self.raw_path.mkdir(parents=True, exist_ok=True)
    
    def _get_cache_key(self, provider: str, symbol: str, timeframe: str) -> str:
        """Generate cache key for a symbol/timeframe combination."""
        return f"{provider}_{symbol}_{timeframe}".replace("/", "_")
    
    def _get_cache_path(self, provider: str, symbol: str, timeframe: str) -> Path:
        """Get the path to the cache file."""
        cache_key = self._get_cache_key(provider, symbol, timeframe)
        return self.processed_path / f"{cache_key}.parquet"
    
    def get_cached_bars(
        self,
        provider: str,
        symbol: str,
        timeframe: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Optional[pd.DataFrame]:
        """
        Retrieve cached bars if available and covering the requested date range.
        
        Args:
            provider: Data provider name (e.g., 'yfinance', 'alpaca')
            symbol: Stock symbol
            timeframe: Timeframe (e.g., '1d', '1h', '5m')
            start_date: Start of requested date range
            end_date: End of requested date range
            
        Returns:
            DataFrame with cached data or None if not found/incomplete
        """
        cache_path = self._get_cache_path(provider, symbol, timeframe)
        
        if not cache_path.exists():
            return None
        
        try:
            df = pd.read_parquet(cache_path)
        except Exception:
            return None
        
        if df.empty:
            return None
        
        # Ensure timestamp column exists
        if 'timestamp' not in df.columns:
            return None
        
        # Convert timestamp to datetime if needed
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Check if cached data covers the requested range
        cached_start = df['timestamp'].min()
        cached_end = df['timestamp'].max()
        
        # If specific dates requested, check coverage
        if start_date is not None or end_date is not None:
            if start_date is not None and cached_start > pd.to_datetime(start_date):
                return None
            if end_date is not None and cached_end < pd.to_datetime(end_date):
                return None
        
        # Filter to requested range if dates specified
        if start_date is not None or end_date is not None:
            mask = pd.Series(True, index=df.index)
            if start_date is not None:
                mask &= df['timestamp'] >= pd.to_datetime(start_date)
            if end_date is not None:
                mask &= df['timestamp'] <= pd.to_datetime(end_date)
            df = df[mask]
        
        return df
    
    def save_bars(
        self,
        provider: str,
        symbol: str,
        timeframe: str,
        df: pd.DataFrame,
        merge: bool = True,
    ) -> None:
        """
        Save bars to cache.
        
        Args:
            provider: Data provider name
            symbol: Stock symbol
            timeframe: Timeframe
            df: DataFrame with columns [timestamp, open, high, low, close, volume]
            merge: If True, merge with existing cache; if False, replace
        """
        cache_path = self._get_cache_path(provider, symbol, timeframe)
        
        # Ensure required columns
        required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        df = df[required_cols].copy()
        
        # Ensure timestamp is datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Remove duplicates and sort
        df = df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
        
        # Merge with existing if requested
        if merge and cache_path.exists():
            try:
                existing = pd.read_parquet(cache_path)
                existing['timestamp'] = pd.to_datetime(existing['timestamp'])
                
                # Combine and remove duplicates
                combined = pd.concat([existing, df], ignore_index=True)
                combined = combined.drop_duplicates(subset=['timestamp'])
                combined = combined.sort_values('timestamp')
                df = combined
            except Exception:
                # If merge fails, use new data
                pass
        
        # Ensure correct column order
        df = df[required_cols]
        
        # Save to parquet
        df.to_parquet(cache_path, index=False)
    
    def clear_cache(
        self,
        provider: Optional[str] = None,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
    ) -> int:
        """
        Clear cache for specific provider/symbol/timeframe.
        
        Returns:
            Number of files deleted
        """
        if provider is None and symbol is None and timeframe is None:
            # Clear all
            count = len(list(self.processed_path.glob("*.parquet")))
            shutil.rmtree(self.processed_path)
            self.processed_path.mkdir(parents=True, exist_ok=True)
            return count
        
        # Clear specific
        cache_path = self._get_cache_path(provider or "", symbol or "", timeframe or "")
        if cache_path.exists():
            cache_path.unlink()
            return 1
        return 0
    
    def get_cache_info(self) -> pd.DataFrame:
        """Get information about cached data."""
        records = []
        for f in self.processed_path.glob("*.parquet"):
            try:
                df = pd.read_parquet(f)
                records.append({
                    'file': f.name,
                    'rows': len(df),
                    'start': df['timestamp'].min() if not df.empty else None,
                    'end': df['timestamp'].max() if not df.empty else None,
                })
            except Exception:
                records.append({
                    'file': f.name,
                    'rows': 0,
                    'start': None,
                    'end': None,
                })
        return pd.DataFrame(records)
