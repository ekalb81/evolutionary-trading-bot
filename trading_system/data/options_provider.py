"""
Alpaca Options Data Provider.

Fetches options chains and contract details for underlying symbols.
"""

import os
import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta

try:
    import alpaca_trade_api as tradeapi
except ImportError:
    tradeapi = None


class OptionsProvider:
    """Fetch options data from Alpaca"""
    
    def __init__(self, api_key: str = None, secret_key: str = None, paper: bool = True):
        if not tradeapi:
            raise ImportError("alpaca_trade_api required")
            
        self.api_key = api_key or os.getenv("ALPACA_API_KEY")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY")
        
        if not self.api_key or not self.secret_key:
            raise ValueError("Alpaca keys required")
            
        base_url = "https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets"
        self.client = tradeapi.REST(self.api_key, self.secret_key, base_url)
        
    def get_options_chain(
        self,
        underlying_symbol: str,
        expiration_date: str = None,
        right: str = None,  # "call" or "put"
        limit: int = 100
    ) -> List[Dict]:
        """
        Get available options contracts for an underlying symbol.
        
        Args:
            underlying_symbol: Stock symbol (e.g., 'AAPL')
            expiration_date: Filter by specific expiration (YYYY-MM-DD)
            right: Filter by 'call' or 'put'
            limit: Max contracts to return
            
        Returns:
            List of contract dicts with: symbol, expiration, strike, right, bid, ask, last
        """
        try:
            # Alpaca v2 options endpoint
            # Note: This is for data plans that include options
            contracts = self.client.get_option_contracts(
                underlying_symbol=underlying_symbol,
                expiration_date=expiration_date,
                right=right,
                limit=limit
            )
            
            results = []
            for c in contracts:
                results.append({
                    "symbol": c.symbol,
                    "underlying": c.underlying_symbol,
                    "expiration": c.expiration_date,
                    "strike": float(c.strike_price),
                    "right": c.type,  # "call" or "put"
                    "bid": float(c.bid_price) if c.bid_price else None,
                    "ask": float(c.ask_price) if c.ask_price else None,
                    "last": float(c.last_price) if c.last_price else None,
                    "open_interest": c.open_interest,
                    "volume": c.volume,
                })
                
            return results
            
        except Exception as e:
            print(f"[OptionsProvider] Error fetching chain for {underlying_symbol}: {e}")
            return []
            
    def select_contract(
        self,
        underlying_symbol: str,
        target_dte: int = 45,
        target_delta: float = 0.50
    ) -> Optional[Dict]:
        """
        Select the best contract matching DTE and Delta targets.
        
        This is a heuristic matching function that finds the closest
        expiration and strike based on delta approximation.
        """
        chain = self.get_options_chain(underlying_symbol, limit=500)
        if not chain:
            return None
            
        # Filter to Calls (default for now)
        calls = [c for c in chain if c["right"] == "call"]
        if not calls:
            return None
            
        # Group by expiration
        expirations = {}
        for c in calls:
            exp = c["expiration"]
            if exp not in expirations:
                expirations[exp] = []
            expirations[exp].append(c)
            
        # Find expiration closest to target DTE
        today = datetime.now().date()
        closest_exp = None
        min_dte_diff = float('inf')
        
        for exp_str, contracts in expirations.items():
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
            dte = (exp_date - today).days
            
            if dte >= 1:  # Must not be expired
                diff = abs(dte - target_dte)
                if diff < min_dte_diff:
                    min_dte_diff = diff
                    closest_exp = exp_str
                    
        if not closest_exp:
            return None
            
        # From that expiration, find strike closest to ATM
        exp_contracts = expirations[closest_exp]
        
        # We need underlying price to find ATM
        # For now, approximate ATM as the middle strike
        strikes = sorted([c["strike"] for c in exp_contracts])
        if not strikes:
            return None
        atm_strike = strikes[len(strikes) // 2]
        
        # Pick the contract closest to ATM
        best = min(exp_contracts, key=lambda c: abs(c["strike"] - atm_strike))
        
        return best


# Quick test
if __name__ == "__main__":
    import os
    os.environ.setdefault("ALPACA_API_KEY", os.getenv("ALPACA_API_KEY", ""))
    os.environ.setdefault("ALPACA_SECRET_KEY", os.getenv("ALPACA_SECRET_KEY", ""))
    
    provider = OptionsProvider()
    contract = provider.select_contract("AAPL", target_dte=30)
    print(f"Selected: {contract}")
