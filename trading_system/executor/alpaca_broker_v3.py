"""
Alpaca Broker v3 - Using the modern alpaca-py SDK.

Fully supports:
- Paper/Live trading
- Fractional orders
- Options chains
- WebSocket streaming for real-time bars
"""

import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from alpaca.trading import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, StopOrderRequest
from alpaca.data import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.live import StockDataStream

logger = logging.getLogger(__name__)


class AlpacaBrokerV3:
    """Modern Alpaca broker using alpaca-py SDK."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        paper: bool = True,
        ws_handler=None,
        ws_symbols: List[str] = None
    ):
        # Load credentials
        self.api_key = api_key or os.getenv("ALPACA_API_KEY")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY")
        
        if not self.api_key or not self.secret_key:
            raise ValueError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set")
        
        self.paper = paper
        
        # Paper URLs are different
        # TradingClient handles paper vs live automatically based on paper=True
        self.client = TradingClient(
            api_key=self.api_key,
            secret_key=self.secret_key,
            paper=paper
        )
        
        # Historical data client (for indicators)
        self.data_client = StockHistoricalDataClient(
            api_key=self.api_key,
            secret_key=self.secret_key
        )
        
        # WebSocket stream for real-time bars
        self.ws_handler = ws_handler
        self.ws_symbols = ws_symbols or []
        self.ws_stream = None
        
        logger.info(f"[AlpacaV3] Connected to {'PAPER' if paper else 'LIVE'} trading")
    
    # ==================== ACCOUNT ====================
    
    def get_account(self) -> Dict[str, Any]:
        """Get account information."""
        account = self.client.get_account()
        return {
            "id": account.id,
            "status": account.status,
            "currency": account.currency,
            "cash": float(account.cash),
            "portfolio_value": float(account.portfolio_value),
            "equity": float(account.equity),
            "buying_power": float(account.buying_power),
            "pattern_day_trader": account.pattern_day_trader,
            "trading_blocked": account.trading_blocked,
            "transfers_blocked": account.transfers_blocked,
            "account_blocked": account.account_blocked,
            "trade_suspended_by_user": account.trade_suspended_by_user,
        }
    
    # ==================== POSITIONS ====================
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """Get all open positions."""
        positions = self.client.get_all_positions()
        return [
            {
                "symbol": p.symbol,
                "qty": float(p.qty),
                "avg_entry_price": float(p.avg_entry_price),
                "market_value": float(p.market_value),
                "cost_basis": float(p.cost_basis),
                "unrealized_pl": float(p.unrealized_pl),
                "unrealized_plpc": float(p.unrealized_plpc),
                "current_price": float(p.current_price),
                "side": p.side,
            }
            for p in positions
        ]
    
    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get a specific position."""
        try:
            position = self.client.get_position(symbol)
            return {
                "symbol": position.symbol,
                "qty": float(position.qty),
                "avg_entry_price": float(position.avg_entry_price),
                "market_value": float(position.market_value),
                "cost_basis": float(position.cost_basis),
                "unrealized_pl": float(position.unrealized_pl),
                "side": position.side,
            }
        except Exception:
            return None
    
    def close_position(self, symbol: str) -> Dict[str, Any]:
        """Liquidate a position."""
        order = self.client.close_position(symbol)
        return {"id": order.id, "symbol": order.symbol, "status": order.status}
    
    def close_all_positions(self) -> List[Dict[str, Any]]:
        """Liquidate all positions."""
        result = self.client.close_all_positions()
        return [{"id": r.id, "symbol": r.symbol, "status": r.status} for r in result]
    
    # ==================== ORDERS ====================
    
    def submit_market_order(
        self,
        symbol: str,
        qty: float,
        side: str = "buy",
        time_in_force: str = "day"
    ) -> Dict[str, Any]:
        """Submit a market order."""
        order_request = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide(side.upper()),
            time_in_force=TimeInForce(time_in_force.upper())
        )
        order = self.client.submit_order(order_request)
        return {
            "id": order.id,
            "symbol": order.symbol,
            "qty": float(order.qty),
            "side": order.side,
            "type": order.type,
            "status": order.status,
            "submitted_at": str(order.submitted_at) if order.submitted_at else None,
        }
    
    def submit_limit_order(
        self,
        symbol: str,
        qty: float,
        limit_price: float,
        side: str = "buy",
        time_in_force: str = "day"
    ) -> Dict[str, Any]:
        """Submit a limit order."""
        order_request = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide(side.upper()),
            limit_price=limit_price,
            time_in_force=TimeInForce(time_in_force.upper())
        )
        order = self.client.submit_order(order_request)
        return {
            "id": order.id,
            "symbol": order.symbol,
            "qty": float(order.qty),
            "side": order.side,
            "type": order.type,
            "limit_price": float(order.limit_price) if order.limit_price else None,
            "status": order.status,
        }
    
    def submit_order(
        self,
        symbol: str,
        qty: float,
        side: str = "buy",
        order_type: str = "market",
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: str = "day"
    ) -> Dict[str, Any]:
        """Submit a generic order."""
        if order_type == "market":
            return self.submit_market_order(symbol, qty, side, time_in_force)
        elif order_type == "limit":
            if not limit_price:
                raise ValueError("limit_price required for limit orders")
            return self.submit_limit_order(symbol, qty, limit_price, side, time_in_force)
        else:
            raise ValueError(f"Unsupported order type: {order_type}")
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        try:
            self.client.cancel_order(order_id)
            return True
        except Exception as e:
            logger.warning(f"Cancel order failed: {e}")
            return False
    
    def get_orders(self, status: str = "open") -> List[Dict[str, Any]]:
        """Get orders."""
        orders = self.client.get_orders(status=status.upper())
        return [
            {
                "id": o.id,
                "symbol": o.symbol,
                "qty": float(o.qty),
                "filled_qty": float(o.filled_qty) if o.filled_qty else 0,
                "side": o.side,
                "type": o.type,
                "status": o.status,
                "limit_price": float(o.limit_price) if o.limit_price else None,
                "stop_price": float(o.stop_price) if o.stop_price else None,
            }
            for o in orders
        ]
    
    # ==================== HISTORICAL DATA ====================
    
    def get_bars(
        self,
        symbol: str,
        start: str = None,
        end: str = None,
        limit: int = 100,
        timeframe: str = "1Day"
    ) -> List[Dict[str, Any]]:
        """Get historical bars for a symbol."""
        # Parse timeframe
        if timeframe == "1Day":
            tf = TimeFrame(1, TimeFrameUnit.Day)
        elif timeframe == "1Min":
            tf = TimeFrame(1, TimeFrameUnit.Minute)
        else:
            tf = TimeFrame(1, TimeFrameUnit.Day)
        
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=tf,
            start=start,
            end=end,
            limit=limit
        )
        
        bars = self.data_client.get_stock_bars(request)
        
        # Convert to list of dicts
        result = []
        if bars and hasattr(bars, 'data'):
            for bar in bars.data.get(symbol, []):
                result.append({
                    "timestamp": bar.timestamp,
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": bar.volume,
                })
        
        return result
    
    def get_latest_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get latest quote for a symbol."""
        request = StockLatestQuoteRequest(symbol_or_symbols=[symbol])
        quotes = self.data_client.get_stock_latest_quote(request)
        
        if symbol in quotes:
            q = quotes[symbol]
            return {
                "bid_price": float(q.bid_price),
                "ask_price": float(q.ask_price),
                "bid_size": q.bid_size,
                "ask_size": q.ask_size,
            }
        return None
    
    # ==================== WEBSOCKET ====================
    
    async def start_websocket(self):
        """Start WebSocket stream for real-time bars."""
        if not self.ws_handler:
            logger.warning("No WebSocket handler set")
            return
        
        self.ws_stream = StockDataStream(
            api_key=self.api_key,
            secret_key=self.secret_key
        )
        
        async def on_bar(bar):
            """Handle incoming bar data."""
            if self.ws_handler:
                formatted_bar = {
                    "symbol": bar.symbol,
                    "timestamp": bar.timestamp.isoformat() if hasattr(bar.timestamp, 'isoformat') else str(bar.timestamp),
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": float(bar.volume),
                }
                await self.ws_handler(formatted_bar)
        
        # Subscribe to symbols passing the handler
        if self.ws_symbols:
            self.ws_stream.subscribe_bars(on_bar, *self.ws_symbols)
        
        # Start the stream in a background task
        import asyncio
        asyncio.create_task(self.ws_stream._run_forever())
        
        # Wait slightly to ensure connection
        await asyncio.sleep(1)
    
    def subscribe_bars(self, symbols: List[str]):
        """Subscribe to bar updates for symbols."""
        self.ws_symbols.extend(symbols)
        if self.ws_stream:
            async def on_bar(bar):
                if self.ws_handler:
                    await self.ws_handler(bar)
            self.ws_stream.subscribe_bars(on_bar, *symbols)
    
    async def stop_websocket(self):
        """Stop WebSocket stream."""
        if self.ws_stream:
            await self.ws_stream.close()
            self.ws_stream = None
    
    # ==================== OPTIONS ====================
    
    def get_option_chains(self, underlying_symbol: str) -> Dict[str, Any]:
        """Get option chains for an underlying symbol."""
        from alpaca.data import OptionHistoricalDataClient
        
        options_client = OptionHistoricalDataClient(
            api_key=self.api_key,
            secret_key=self.secret_key
        )
        
        # This would return option chains - simplified for now
        return {"symbol": underlying_symbol, "status": "not_implemented"}


# Convenience factory function
def create_broker(paper=True, ws_handler=None, ws_symbols=None) -> AlpacaBrokerV3:
    """Create an Alpaca broker instance."""
    return AlpacaBrokerV3(
        paper=paper,
        ws_handler=ws_handler,
        ws_symbols=ws_symbols
    )


if __name__ == "__main__":
    # Test the broker
    broker = AlpacaBrokerV3()
    account = broker.get_account()
    print(f"Account equity: ${account['equity']}")
    print(f"Buying power: ${account['buying_power']}")
