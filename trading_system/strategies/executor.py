"""
Paper Trading Executor for evolved strategies.

Runs on Alpaca and logs all trades + signals to memory for orchestrator monitoring.
Supports signal extension: if a strong signal exists past max_hold, reports back to parent.
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce


class StrategyState:
    """Track per-symbol: active position, entry price, entry time, signal strength"""
    def __init__(self):
        self.active_positions = {}  # symbol -> {entry_price, entry_bar, qty, entry_signal_strength}
        self.signal_extensions = {}  # symbol -> {bar_count, latest_signal_strength, reason}
        
    def is_open(self, symbol: str) -> bool:
        return symbol in self.active_positions
    
    def get_position(self, symbol: str) -> Optional[Dict]:
        return self.active_positions.get(symbol)
    
    def open_position(self, symbol: str, entry_price: float, entry_bar: int, qty: int, signal_strength: float = 1.0):
        self.active_positions[symbol] = {
            'entry_price': entry_price,
            'entry_bar': entry_bar,
            'qty': qty,
            'entry_signal_strength': signal_strength,
            'bars_held': 0,
        }
        if symbol in self.signal_extensions:
            del self.signal_extensions[symbol]
    
    def close_position(self, symbol: str) -> Optional[Dict]:
        if symbol in self.active_positions:
            pos = self.active_positions.pop(symbol)
            if symbol in self.signal_extensions:
                del self.signal_extensions[symbol]
            return pos
        return None
    
    def flag_signal_extension(self, symbol: str, bars_held: int, signal_strength: float, reason: str):
        """Called if exit signal hasn't fired but we detect a strong reason to hold"""
        self.signal_extensions[symbol] = {
            'bars_held': bars_held,
            'signal_strength': signal_strength,
            'reason': reason,
            'timestamp': datetime.utcnow().isoformat(),
        }


class StrategyExecutor:
    def __init__(self, strategy_genome: Dict, api_key: str, secret_key: str, base_url: str = None, paper: bool = True):
        """
        Args:
            strategy_genome: The evolved strategy config (entry_rule, exit_rule, indicators, risk_mgmt, etc.)
            api_key: Alpaca API key
            secret_key: Alpaca secret key
            base_url: Alpaca base URL (defaults to paper trading)
            paper: If True, use paper trading endpoint
        """
        self.strategy = strategy_genome
        self.paper = paper
        
        # Initialize Alpaca client
        if base_url is None:
            base_url = "https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets"
        
        self.client = TradingClient(
            api_key=api_key,
            secret_key=secret_key,
            base_url=base_url,
        )
        
        self.state = StrategyState()
        self.trade_log = []
        self.extension_log = []
        
        # Extract strategy parameters
        self.max_hold_bars = strategy_genome.get('risk_management', {}).get('max_hold_bars', 5)
        self.stop_loss_pct = strategy_genome.get('risk_management', {}).get('stop_loss_pct', 0.07)
        self.take_profit_pct = strategy_genome.get('risk_management', {}).get('take_profit_pct', 0.197)
        self.position_size_pct = strategy_genome.get('position_sizing', {}).get('max_pct', 0.10)
        
        # Override max_hold to 3-5 days per user spec
        self.max_hold_bars = 3  # Conservative default; can be 4-5 if needed
        self.max_hold_bars_hard_limit = 5  # Allow extension up to this
        
        print(f"[Executor] Strategy loaded. Max hold: {self.max_hold_bars} bars, hard limit: {self.max_hold_bars_hard_limit} bars")
    
    def get_account_value(self) -> float:
        account = self.client.get_account()
        return float(account.equity)
    
    def calculate_position_size(self, symbol: str, current_price: float) -> int:
        """Volatility-adjusted position sizing"""
        account_value = self.get_account_value()
        risk_amount = account_value * self.position_size_pct
        
        # Position size = risk_amount / (stop_loss_pct * current_price)
        qty = int(risk_amount / (self.stop_loss_pct * current_price))
        
        # Cap at 100 shares per symbol for safety
        qty = min(qty, 100)
        return max(qty, 1)
    
    def place_market_order(self, symbol: str, qty: int, side: str) -> Optional[str]:
        """Place a market order. Returns order ID on success."""
        try:
            req = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY if side == 'buy' else OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            )
            order = self.client.submit_order(req)
            return order.id
        except Exception as e:
            print(f"[Error] Failed to place {side} order for {symbol}: {e}")
            return None
    
    def open_position(self, symbol: str, current_price: float, bar_idx: int, signal_strength: float = 1.0) -> bool:
        """Open a long position if not already open"""
        if self.state.is_open(symbol):
            return False
        
        qty = self.calculate_position_size(symbol, current_price)
        order_id = self.place_market_order(symbol, qty, 'buy')
        
        if order_id:
            self.state.open_position(symbol, current_price, bar_idx, qty, signal_strength)
            self.trade_log.append({
                'timestamp': datetime.utcnow().isoformat(),
                'symbol': symbol,
                'action': 'ENTRY',
                'price': current_price,
                'qty': qty,
                'bar': bar_idx,
                'signal_strength': signal_strength,
                'order_id': order_id,
            })
            print(f"[Trade] ENTRY {symbol} @ ${current_price:.2f}, qty={qty}, signal_strength={signal_strength:.2f}")
            return True
        return False
    
    def close_position(self, symbol: str, current_price: float, bar_idx: int, reason: str = 'exit_signal') -> bool:
        """Close the position for a symbol"""
        pos = self.state.get_position(symbol)
        if not pos:
            return False
        
        qty = pos['qty']
        order_id = self.place_market_order(symbol, qty, 'sell')
        
        if order_id:
            self.state.close_position(symbol)
            pnl_pct = (current_price - pos['entry_price']) / pos['entry_price']
            pnl_amount = pnl_pct * current_price * qty
            
            self.trade_log.append({
                'timestamp': datetime.utcnow().isoformat(),
                'symbol': symbol,
                'action': 'EXIT',
                'entry_price': pos['entry_price'],
                'exit_price': current_price,
                'qty': qty,
                'bars_held': bar_idx - pos['entry_bar'],
                'pnl_pct': pnl_pct,
                'pnl_amount': pnl_amount,
                'reason': reason,
                'order_id': order_id,
            })
            print(f"[Trade] EXIT {symbol} @ ${current_price:.2f}, PnL: {pnl_pct:.2%} ({reason})")
            return True
        return False
    
    def check_extension_signal(self, symbol: str, bars_held: int, entry_price: float, 
                              current_price: float, signal_strength: float) -> bool:
        """
        Detect if there's a strong reason to hold past max_hold_bars.
        
        Args:
            symbol: Ticker
            bars_held: How many bars we've been holding
            entry_price: Entry price
            current_price: Current price
            signal_strength: Strength of remaining bullish signal (0-1)
        
        Returns:
            True if we should extend, False otherwise
        """
        if bars_held < self.max_hold_bars:
            return False  # Not at the limit yet
        
        if bars_held >= self.max_hold_bars_hard_limit:
            return False  # Hard limit hit
        
        pnl_pct = (current_price - entry_price) / entry_price
        
        # Extension logic:
        # 1. If we're still in profit AND signal strength is strong, consider extending
        # 2. If we're barely above breakeven but signal is very strong, hold
        reasons = []
        
        if pnl_pct > 0.05 and signal_strength > 0.7:
            reasons.append(f"Profitable (+{pnl_pct:.1%}) with strong signal ({signal_strength:.2f})")
        
        if pnl_pct > 0 and signal_strength > 0.85:
            reasons.append(f"In profit with very strong signal ({signal_strength:.2f})")
        
        if reasons:
            reason = "; ".join(reasons)
            self.state.flag_signal_extension(symbol, bars_held, signal_strength, reason)
            self.extension_log.append({
                'timestamp': datetime.utcnow().isoformat(),
                'symbol': symbol,
                'bars_held': bars_held,
                'entry_price': entry_price,
                'current_price': current_price,
                'pnl_pct': pnl_pct,
                'signal_strength': signal_strength,
                'reason': reason,
                'action': 'HOLD_EXTENSION_FLAGGED',
            })
            print(f"[Extension] {symbol} flagged for review: {reason}")
            return True
        
        return False
    
    def process_bar(self, bar_idx: int, symbol: str, ohlcv: Dict, 
                   entry_signal: bool, exit_signal: bool, signal_strength: float = 1.0):
        """
        Process a single OHLCV bar for a symbol.
        
        Args:
            bar_idx: Bar index (date-based counter)
            symbol: Ticker
            ohlcv: {'open': float, 'high': float, 'low': float, 'close': float, 'volume': int}
            entry_signal: Does entry rule fire?
            exit_signal: Does exit rule fire?
            signal_strength: Confidence 0-1 (for future multi-indicator systems)
        """
        close_price = ohlcv['close']
        
        # If we don't have a position, check for entry
        if not self.state.is_open(symbol):
            if entry_signal:
                self.open_position(symbol, close_price, bar_idx, signal_strength)
            return
        
        # We have an open position
        pos = self.state.get_position(symbol)
        bars_held = bar_idx - pos['entry_bar']
        
        entry_price = pos['entry_price']
        pnl_pct = (close_price - entry_price) / entry_price
        
        # Check hard stops
        if pnl_pct <= -self.stop_loss_pct:
            self.close_position(symbol, close_price, bar_idx, f'STOP_LOSS ({pnl_pct:.1%})')
            return
        
        if pnl_pct >= self.take_profit_pct:
            self.close_position(symbol, close_price, bar_idx, f'TAKE_PROFIT ({pnl_pct:.1%})')
            return
        
        # Check max hold time (with extension logic)
        if bars_held >= self.max_hold_bars:
            # Check if we should flag for extension
            should_extend = self.check_extension_signal(symbol, bars_held, entry_price, close_price, signal_strength)
            
            if should_extend:
                # Don't close yet, but report to orchestrator
                return
            
            if bars_held >= self.max_hold_bars_hard_limit:
                self.close_position(symbol, close_price, bar_idx, f'MAX_HOLD_HARD_LIMIT ({bars_held} bars)')
                return
        
        # Check exit signal
        if exit_signal:
            self.close_position(symbol, close_price, bar_idx, 'EXIT_SIGNAL')
            return
    
    def save_session_log(self, filename: str = None):
        """Save trade log and extension log to disk"""
        if filename is None:
            filename = f"/data/workspace/trading_system/logs/session_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        report = {
            'session_start': datetime.utcnow().isoformat(),
            'total_trades': len([t for t in self.trade_log if t['action'] == 'EXIT']),
            'total_extensions_flagged': len(self.extension_log),
            'trade_log': self.trade_log,
            'extension_log': self.extension_log,
            'open_positions': self.state.active_positions,
            'pending_extensions': self.state.signal_extensions,
        }
        
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"[Log] Session saved to {filename}")
        return filename
    
    def get_orchestrator_update(self) -> Dict:
        """Return a snapshot for the parent orchestrator to decide on extension holds"""
        return {
            'timestamp': datetime.utcnow().isoformat(),
            'open_positions': self.state.active_positions,
            'pending_extensions': self.state.signal_extensions,
            'recent_trades': self.trade_log[-5:] if self.trade_log else [],
        }


if __name__ == '__main__':
    # Example usage (would be called from orchestrator)
    import sys
    
    api_key = os.getenv('ALPACA_API_KEY')
    secret_key = os.getenv('ALPACA_SECRET_KEY')
    
    if not api_key or not secret_key:
        print("Error: Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables")
        sys.exit(1)
    
    # Load the winning strategy
    with open('/data/workspace/data/evolution/gen_006/population.json') as f:
        pop = json.load(f)
    
    strategy = None
    for s in pop:
        if s.get('id', '').startswith('9b8e6de4'):
            strategy = s
            break
    
    if not strategy:
        print("Error: Could not find GEN6_9b8e6de4 strategy")
        sys.exit(1)
    
    executor = StrategyExecutor(strategy, api_key, secret_key, paper=True)
    print(f"✓ Executor initialized. Account value: ${executor.get_account_value():,.2f}")
