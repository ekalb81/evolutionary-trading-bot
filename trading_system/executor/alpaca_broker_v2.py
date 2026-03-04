"""
Alpaca Broker Implementation using alpaca-py SDK.

Migrated from alpaca-trade-api to alpaca-py for:
- Unified WebSocket handling
- Native Options support
- Better maintained codebase
"""

import os
import logging
from typing import Dict, List, Optional, Any, Callable, Awaitable
from datetime import datetime

from alpaca.trading import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, StopOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass
from alpaca.data import StockHistoricalDataClient
from alpaca.data.live import StockDataStream
from alpaca.data.enums import DataFeed
from alpaca.data.requests import OptionChainRequest

from .interfaces import BrokerInterface, OrderSide as InterfaceOrderSide, TimeInForce as InterfaceTimeInForce
from .interfaces import BracketOrderRequest, TrailingStopOrderRequest, Position, Order

logger = logging.getLogger(__name__)


class AlpacaBrokerV2(BrokerInterface):
    """
    Alpaca broker using the modern alpaca-py SDK.
    
    Supports:
    - Stock & ETF trading (long/short)
    - Fractional trading
    - Bracket orders (OTO, OCO)
    - Options chains
    - Real-time WebSocket streams
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        paper: bool = True,
    ):
        self.api_key = api_key or os.getenv("ALPACA_API_KEY")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY")
        self.paper = paper
        
        if not self.api_key or not self.secret_key:
            raise ValueError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set")
        
        # Trading client (for orders, positions, account)
        self.client = TradingClient(
            self.api_key,
            self.secret_key,
            paper=paper,
            url_override="https://paper-api.alpaca.markets" if paper else None
        )
        
        # Historical data client (for bars, quotes)
        self.data_client = StockHistoricalDataClient(
            self.api_key,
            self.secret_key
        )
        
        # WebSocket stream (initialized lazily)
        self._stream = None
        
        print(f"[AlpacaV2] Connected to {'PAPER' if paper else 'LIVE'} trading")
    
    def get_account(self) -> Dict[str, Any]:
        """Get account information"""
        account = self.client.get_account()
        return {
            "id": account.id,
            "cash": float(account.cash),
            "portfolio_value": float(account.portfolio_value),
            "buying_power": float(account.buying_power),
            "equity": float(account.equity),
            "status": account.status,
        }
    
    def get_positions(self) -> List[Position]:
        """Get all open positions"""
        positions = self.client.get_all_positions()
        return [
            Position(
                symbol=p.symbol,
                qty=int(p.qty),
                entry_price=float(p.avg_entry_price),
                current_price=float(p.current_price),
                unrealized_pl=float(p.unrealized_pl),
                unrealized_plpc=float(p.unrealized_plpc),
                avg_entry_price=float(p.avg_entry_price),
            )
            for p in positions
        ]
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol"""
        try:
            p = self.client.get_position(symbol)
            return Position(
                symbol=p.symbol,
                qty=int(p.qty),
                entry_price=float(p.avg_entry_price),
                current_price=float(p.current_price),
                unrealized_pl=float(p.unrealized_pl),
                unrealized_plpc=float(p.unrealized_plpc),
                avg_entry_price=float(p.avg_entry_price),
            )
        except Exception:
            return None
    
    def submit_bracket_order(self, order: BracketOrderRequest) -> Order:
        """
        Submit a bracket order using alpaca-py.
        
        Creates: Primary order + take_profit + stop_loss
        """
        side = OrderSide.BUY if order.side == InterfaceOrderSide.BUY else OrderSide.SELL
        tif = TimeInForce.DAY if order.time_in_force == InterfaceTimeInForce.DAY else TimeInForce.GTC
        
        # Build the order request
        order_req = MarketOrderRequest(
            symbol=order.symbol,
            qty=order.qty,
            side=side,
            time_in_force=tif,
            order_class=OrderClass.BRACKET,
            take_profit=dict(limit_price=str(order.take_profit_limit_price)) if order.take_profit_limit_price else None,
            stop_loss=dict(stop_price=str(order.stop_loss_stop_price)) if order.stop_loss_stop_price else None,
        )
        
        response = self.client.submit_order(order_req)
        
        return Order(
            id=response.id,
            symbol=response.symbol,
            side=InterfaceOrderSide.BUY if response.side == OrderSide.BUY else InterfaceOrderSide.SELL,
            qty=int(response.qty),
            status=str(response.status),
            filled_qty=int(response.filled_qty),
            filled_avg_price=float(response.filled_avg_price) if response.filled_avg_price else None,
            order_type=str(response.order_type),
        )
    
    def submit_market_order(
        self,
        symbol: str,
        qty: float,
        side: InterfaceOrderSide,
        time_in_force: InterfaceTimeInForce = InterfaceTimeInForce.DAY,
    ) -> Order:
        """Submit a simple market order (supports fractional qty)"""
        order_side = OrderSide.BUY if side == InterfaceOrderSide.BUY else OrderSide.SELL
        tif = TimeInForce.DAY if time_in_force == InterfaceTimeInForce.DAY else TimeInForce.GTC
        
        req = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=order_side,
            time_in_force=tif,
        )
        
        response = self.client.submit_order(req)
        
        return Order(
            id=response.id,
            symbol=response.symbol,
            side=side,
            qty=int(response.qty),
            status=str(response.status),
            filled_qty=int(response.filled_qty),
            filled_avg_price=float(response.filled_avg_price) if response.filled_avg_price else None,
            order_type=str(response.order_type),
        )
    
    def replace_with_trailing_stop(self, symbol: str, trail_percent: float) -> Order:
        """Replace a position's stop-loss with a trailing stop"""
        # First cancel existing stop orders
        self._cancel_stops_for_symbol(symbol)
        
        # Submit new trailing stop
        req = StopOrderRequest(
            symbol=symbol,
            qty=1,  # Will be filled by broker
            side=OrderSide.SELL,
            trailing_percent=trail_percent,
            time_in_force=TimeInForce.GTC,
        )
        
        response = self.client.submit_order(req)
        
        return Order(
            id=response.id,
            symbol=response.symbol,
            side=InterfaceOrderSide.SELL,
            qty=1,
            status=str(response.status),
            filled_qty=0,
            filled_avg_price=None,
            order_type="trailing_stop",
        )
    
    def _cancel_stops_for_symbol(self, symbol: str):
        """Cancel all stop orders for a symbol"""
        try:
            orders = self.client.get_orders(status="open")
            for o in orders:
                if o.symbol == symbol and o.order_type in ["stop_loss", "trailing_stop"]:
                    self.client.cancel_order(o.id)
        except Exception as e:
            logger.warning(f"Could not cancel stops: {e}")
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order"""
        try:
            self.client.cancel_order(order_id)
            return True
        except Exception:
            return False
    
    def close_position(self, symbol: str, qty: Optional[int] = None) -> Order:
        """Close all or part of a position"""
        close_req = {"qty": str(qty)} if qty else {}
        
        # Use the close_position endpoint
        response = self.client.close_position(symbol, **close_req)
        
        return Order(
            id=response.id,
            symbol=response.symbol,
            side=InterfaceOrderSide.SELL,
            qty=int(response.qty),
            status=str(response.status),
            filled_qty=int(response.filled_qty),
            filled_avg_price=float(response.filled_avg_price) if response.filled_avg_price else None,
            order_type=str(response.order_type),
        )
    
    def get_latest_quote(self, symbol: str) -> Dict[str, float]:
        """Get latest bid/ask for a symbol"""
        try:
            from alpaca.data import LatestQuoteRequest
            req = LatestQuoteRequest(symbols=[symbol])
            quote = self.data_client.get_latest_quote(req)
            
            if symbol in quote:
                q = quote[symbol]
                return {
                    "bid": float(q.bid_price),
                    "ask": float(q.ask_price),
                    "bid_size": int(q.bid_size),
                    "ask_size": int(q.ask_size),
                }
        except Exception as e:
            logger.error(f"Quote error for {symbol}: {e}")
        
        return {"bid": 0, "ask": 0}
    
    def get_bars(self, symbol: str, limit: int = 100, timeframe: str = "1Day") -> List[Dict]:
        """Fetch historical bars for indicator seeding"""
        try:
            from alpaca.data import StockBarsRequest, TimeFrame
            from alpaca.data.timeframe import TimeFrameUnit
            
            # Map timeframe string to TimeFrame
            tf_map = {
                "1Min": TimeFrame(1, TimeFrameUnit.Minute),
                "5Min": TimeFrame(5, TimeFrameUnit.Minute),
                "15Min": TimeFrame(15, TimeFrameUnit.Minute),
                "1Hour": TimeFrame(1, TimeFrameUnit.Hour),
                "1Day": TimeFrame(1, TimeFrameUnit.Day),
            }
            
            req = StockBarsRequest(
                symbol_or_symbols=[symbol],
                timeframe=tf_map.get(timeframe, TimeFrame(1, TimeFrameUnit.Day)),
                limit=limit,
            )
            
            bars = self.data_client.get_stock_bars(req)
            
            if symbol in bars:
                return [
                    {
                        "timestamp": b.timestamp.isoformat(),
                        "open": float(b.open),
                        "high": float(b.high),
                        "low": float(b.low),
                        "close": float(b.close),
                        "volume": int(b.volume),
                    }
                    for b in bars[symbol]
                ]
        except Exception as e:
            logger.error(f"Bars error for {symbol}: {e}")
        
        return []
    
    def get_options_chain(self, underlying_symbol: str, limit: int = 200) -> List[Dict]:
        """Fetch options chain for underlying symbol"""
        try:
            from alpaca.data import OptionHistoricalDataClient
            from alpaca.data.requests import OptionChainRequest
            
            # Options require a separate client
            opt_client = OptionHistoricalDataClient(self.api_key, self.secret_key)
            
            req = OptionChainRequest(underlying_symbol=underlying_symbol, limit=limit)
            chain = opt_client.get_option_chain(req)
            
            results = []
            # Chain is a dict: {symbol: OptionsSnapshot}
            # Symbol format: AAPL260313P00252500 -> Underlying(6date)(Put/Call)(strike*1000)
            for sym, snap in chain.items():
                # Parse symbol for strike/expiration
                if len(sym) > 12:
                    exp_str = sym[len(underlying_symbol):len(underlying_symbol)+6]
                    right = sym[len(underlying_symbol)+6]
                    strike = float(sym[len(underlying_symbol)+7:]) / 1000
                else:
                    exp_str = "Unknown"
                    right = "call"
                    strike = 0
                    
                results.append({
                    "symbol": sym,
                    "underlying": underlying_symbol,
                    "expiration": f"20{exp_str[:2]}-{exp_str[2:4]}-{exp_str[4:6]}",
                    "strike": strike,
                    "right": "put" if right == "P" else "call",
                    "bid": float(snap.latest_quote.bid_price) if snap.latest_quote else None,
                    "ask": float(snap.latest_quote.ask_price) if snap.latest_quote else None,
                    "last": float(snap.latest_trade.price) if snap.latest_trade else None,
                })
            return results
        except Exception as e:
            logger.error(f"Options chain error for {underlying_symbol}: {e}")
            return []
    
    # ========== WebSocket Methods ==========
    
    async def stream_bars(self, callback: Callable[[Dict], Awaitable], symbols: List[str]):
        """Stream real-time 1-minute bars via WebSocket"""
        stream = StockDataStream(self.api_key, self.secret_key, feed=DataFeed.IEX)
        
        async def on_bar(bar):
            await callback({
                "symbol": bar.symbol,
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": int(bar.volume),
                "timestamp": bar.timestamp.isoformat(),
            })
        
        stream.subscribe_bars(on_bar, *symbols)
        
        # Run forever
        await stream._run_forever()
    
    async def stream_quotes(self, callback: Callable[[Dict], Awaitable], symbols: List[str]):
        """Stream real-time quotes via WebSocket"""
        stream = StockDataStream(self.api_key, self.secret_key, feed=DataFeed.IEX)
        
        async def on_quote(quote):
            await callback({
                "symbol": quote.symbol,
                "bid": float(quote.bid_price),
                "ask": float(quote.ask_price),
                "bid_size": int(quote.bid_size),
                "ask_size": int(quote.ask_size),
                "timestamp": quote.timestamp.isoformat(),
            })
        
        stream.subscribe_quotes(on_quote, *symbols)
        await stream._run_forever()
    
    async def stream_trades(self, callback: Callable[[Dict], Awaitable], symbols: List[str]):
        """Stream real-time trades via WebSocket"""
        stream = StockDataStream(self.api_key, self.secret_key, feed=DataFeed.IEX)
        
        async def on_trade(trade):
            await callback({
                "symbol": trade.symbol,
                "price": float(trade.price),
                "size": int(trade.size),
                "timestamp": trade.timestamp.isoformat(),
            })
        
        stream.subscribe_trades(on_trade, *symbols)
        await stream._run_forever()
