"""
Abstract broker interface for the trading system.

This defines the contract that any broker implementation must fulfill.
If you switch to a different broker (e.g., Interactive Brokers, Tradier),
implement this interface and the rest of the system works unchanged.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from enum import Enum


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class TimeInForce(Enum):
    DAY = "day"
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"


@dataclass
class OHLCV:
    """Single bar of OHLCV data"""
    timestamp: str  # ISO 8601
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class Position:
    """Represents an active position"""
    symbol: str
    qty: int
    entry_price: float
    current_price: float
    unrealized_pl: float
    unrealized_plpc: float  # Percent
    avg_entry_price: float


@dataclass
class Order:
    """Represents a submitted order"""
    id: str
    symbol: str
    side: OrderSide
    qty: int
    status: str  # pending, filled, cancelled, rejected
    filled_qty: int
    filled_avg_price: Optional[float]
    order_type: str  # market, limit, stop, bracket


@dataclass
class BracketOrderRequest:
    """
    A bracket order: primary order with take-profit and stop-loss legs.
    
    The broker executes the primary order. When it fills, the TP and SL
    legs are automatically submitted. If either triggers, the other is cancelled.
    """
    symbol: str
    side: OrderSide
    qty: int
    
    # Primary order
    order_type: str = "market"  # market, limit
    limit_price: Optional[float] = None
    
    # Take profit (profit target)
    take_profit_limit_price: Optional[float] = None
    
    # Stop loss (risk management)
    stop_loss_stop_price: Optional[float] = None
    stop_loss_limit_price: Optional[float] = None  # For stop-limit orders
    
    # Time in force
    time_in_force: TimeInForce = TimeInForce.DAY


@dataclass
class TrailingStopOrderRequest:
    """
    A trailing stop order. The stop price moves with the market,
    locking in profit as the price moves favorably.
    """
    symbol: str
    side: OrderSide  # SELL for long positions
    qty: int
    
    trail_type: str = "percent"  # percent or abs
    trail_percent: Optional[float] = None  # e.g., 2.0 for 2%
    trail_abs: Optional[float] = None  # Dollar amount
    
    time_in_force: TimeInForce = TimeInForce.GTC


class BrokerInterface(ABC):
    """
    Abstract interface for broker implementations.
    
    All broker-specific logic lives in subclasses. The trading engine
    only knows about this interface.
    """
    
    @abstractmethod
    def get_account(self) -> Dict[str, Any]:
        """Get account equity, cash, buying power, etc."""
        pass
    
    @abstractmethod
    def get_positions(self) -> List[Position]:
        """Get all open positions"""
        pass
    
    @abstractmethod
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol"""
        pass
    
    @abstractmethod
    def submit_bracket_order(self, order: BracketOrderRequest) -> Order:
        """
        Submit a bracket order (entry + TP + SL).
        
        Returns the primary order. TP and SL are handled by the broker.
        """
        pass
    
    @abstractmethod
    def replace_with_trailing_stop(self, symbol: str, trail_percent: float) -> Order:
        """
        Replace a position's stop-loss with a trailing stop.
        
        This is used when the orchestrator decides to extend a winning
        position: cancel the static SL and replace with a trailing stop.
        """
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order"""
        pass
    
    @abstractmethod
    def close_position(self, symbol: str, qty: Optional[int] = None) -> Order:
        """
        Close all or part of a position.
        
        If qty is None, close the entire position.
        """
        pass
    
    @abstractmethod
    def get_latest_quote(self, symbol: str) -> Dict[str, float]:
        """Get latest bid/ask for a symbol"""
        pass
    
    @abstractmethod
    async def stream_trades(self, callback):
        """
        Start a WebSocket stream of trade updates.
        
        callback: async function that receives trade update dicts
        """
        pass
    
    @abstractmethod
    async def stream_quotes(self, callback):
        """
        Start a WebSocket stream of quote updates.
        
        callback: async function that receives quote update dicts
        """
        pass

    @abstractmethod
    def get_bars(self, symbol: str, limit: int = 100, timeframe: str = "1Day") -> List[Dict]:
        """Fetch historical bars for indicator seeding."""
        pass
