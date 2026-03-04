"""
Alpaca broker implementation using alpaca-trade-api (v2 REST API).

This is the older but more widely compatible Alpaca library.
"""

import logging
logger = logging.getLogger(__name__)

import os
import json
from typing import Dict, List, Optional, Any, Callable, Awaitable

import alpaca_trade_api as tradeapi
from alpaca_trade_api.rest import REST, APIError
from alpaca_trade_api.stream import Stream
from alpaca_trade_api.stream import Stream

from .interfaces import (
    BrokerInterface,
    OrderSide,
    TimeInForce,
    BracketOrderRequest,
    TrailingStopOrderRequest,
    Position,
    Order,
)


class AlpacaBroker(BrokerInterface):
    """
    Alpaca implementation using alpaca-trade-api.
    
    Supports both paper and live trading. Configure via environment:
    - ALPACA_API_KEY
    - ALPACA_SECRET_KEY
    - ALPACA_BASE_URL (optional, defaults to paper)
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        base_url: Optional[str] = None,
        paper: bool = True,
    ):
        self.api_key = api_key or os.getenv("ALPACA_API_KEY")
        self.secret_key = secret_key
        self.paper = paper or os.getenv("ALPACA_SECRET_KEY")
        
        if not self.api_key or not self.secret_key:
            raise ValueError("AlpACA_API_KEY and ALPACA_SECRET_KEY must be set")
            
        self.paper = paper
        
        # Set base URL
        if base_url:
            self.base_url = base_url.replace('/v2', '')
        elif paper:
            # Drop the trailing /v2 if it is manually specified in env so the REST class doesn't double it
            self.base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").replace('/v2', '')
        else:
            self.base_url = os.getenv("ALPACA_BASE_URL", "https://api.alpaca.markets").replace('/v2', '')
        
        # Initialize REST client
        self.client = REST(
            self.api_key,
            self.secret_key,
            base_url="https://paper-api.alpaca.markets",
            api_version='v2'
        )
        
        # For market data
        # Note: Using REST client for quotes instead of Polygon
        self._data_client = REST(
            self.api_key,
            self.secret_key,
            base_url="https://paper-api.alpaca.markets",
            api_version='v2'
        )
        
        # Track orders
        self._order_map: Dict[str, Dict] = {}
        
        print(f"[Alpaca] Connected to {'PAPER' if 'paper' in self.base_url else 'LIVE'} trading")
    
    def get_account(self) -> Dict[str, Any]:
        account = self.client.get_account()
        return {
            "equity": float(account.equity),
            "cash": float(account.cash),
            "buying_power": float(account.buying_power),
            "portfolio_value": float(account.portfolio_value),
            "pattern_day_trader": account.pattern_day_trader,
            "trading_blocked": account.trading_blocked,
            "transfers_blocked": account.transfers_blocked,
        }
    
    def get_positions(self) -> List[Position]:
        positions = self.client.list_positions()
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
        except APIError:
            return None
    
    def submit_bracket_order(self, order: BracketOrderRequest) -> Order:
        """
        Submit a bracket order using Alpaca's v2 bracket order syntax.
        
        Creates: Primary order + take_profit + stop_loss
        """
        # Build order legs
        side_str = "buy" if order.side == OrderSide.BUY else "sell"
        tif_str = order.time_in_force.value if order.time_in_force else "day"
        
        # Build the order submission
        submit_params = {
            "symbol": order.symbol,
            "qty": str(order.qty),
            "side": side_str,
            "type": order.order_type,
            "time_in_force": tif_str,
            "order_class": "bracket",
        }
        
        if order.limit_price:
            submit_params["limit_price"] = str(round(order.limit_price, 2))
        
        # Take profit and stop loss
        if order.take_profit_limit_price:
            submit_params["take_profit"] = {"limit_price": str(round(order.take_profit_limit_price, 2))}
        
        if order.stop_loss_stop_price:
            submit_params["stop_loss"] = {
                "stop_price": str(round(order.stop_loss_stop_price, 2)),
            }
            if order.stop_loss_limit_price:
                submit_params["stop_loss"]["limit_price"] = str(round(order.stop_loss_limit_price, 2))
        
        # Submit
        # Ensure we pass unpacked params properly to alpaca_trade_api
        response = self.client.submit_order(**submit_params)
        
        # Track
        self._order_map[response.id] = {
            "symbol": order.symbol,
            "qty": order.qty,
            "side": order.side,
        }
        
        return Order(
            id=response.id,
            symbol=response.symbol,
            side=order.side,
            qty=order.qty,
            status=response.status,
            filled_qty=0,
            filled_avg_price=None,
            order_type=f"bracket_{order.order_type}",
        )
    
    def replace_with_trailing_stop(self, symbol: str, trail_percent: float) -> Order:
        """
        Replace a position's stop-loss with a trailing stop.
        
        Process:
        1. Get current position
        2. Cancel existing stop orders
        3. Submit trailing stop order
        """
        position = self.get_position(symbol)
        if not position:
            raise ValueError(f"No position found for {symbol}")
        
        # Cancel existing stop orders
        self._cancel_stops_for_symbol(symbol)
        
        # Submit trailing stop
        # In Alpaca v2, we submit a stop order with a trail percent
        response = self.client.submit_order({
            "symbol": symbol,
            "qty": str(position.qty),
            "side": "sell",
            "type": "trailing_stop",
            "trail_percent": str(trail_percent),
            "time_in_force": "gtc",
        })
        
        self._order_map[response.id] = {
            "symbol": symbol,
            "qty": position.qty,
            "side": OrderSide.SELL,
            "type": "trailing_stop",
        }
        
        return Order(
            id=response.id,
            symbol=symbol,
            side=OrderSide.SELL,
            qty=position.qty,
            status=response.status,
            filled_qty=0,
            filled_avg_price=None,
            order_type="trailing_stop",
        )
    
    def _cancel_stops_for_symbol(self, symbol: str):
        """Cancel all pending stop/tp orders for a symbol"""
        try:
            orders = self.client.list_orders(status="open")
            for o in orders:
                if o.symbol == symbol and o.side == "sell":
                    try:
                        self.client.cancel_order(o.id)
                        print(f"[Alpaca] Cancelled order {o.id} for {symbol}")
                    except Exception:
                        pass  # May already be filled/cancelled
        except Exception:
            pass
    
    def cancel_order(self, order_id: str) -> bool:
        try:
            self.client.cancel_order(order_id)
            return True
        except Exception:
            return False
    
    def close_position(self, symbol: str, qty: Optional[int] = None) -> Order:
        """Close all or part of a position"""
        try:
            # Use close_position which handles the logic
            response = self.client.close_position(symbol, qty=qty)
            
            return Order(
                id=response.id,
                symbol=response.symbol,
                side=OrderSide.SELL,
                qty=int(response.qty),
                status=response.status,
                filled_qty=0,
                filled_avg_price=None,
                order_type="close",
            )
        except APIError as e:
            raise ValueError(f"Failed to close position for {symbol}: {e}")
    
    def get_latest_quote(self, symbol: str) -> Dict[str, float]:
        """Get latest bid/ask for a symbol"""
        # Use the latest quote endpoint
        try:
            quote = self._data_client.get_latest_quote(symbol)
            return {
                "bid": float(quote.bid_price),
                "ask": float(quote.ask_price),
                "bid_size": quote.bid_size,
                "ask_size": quote.ask_size,
            }
        except Exception as e:
            # Fallback - try bar endpoint
            try:
                bars = self._data_client.get_barset(symbol, "minute", 1)
                bar = bars[symbol][0]
                return {
                    "bid": bar.c,
                    "ask": bar.c,
                    "bid_size": 0,
                    "ask_size": 0,
                }
            except Exception as e2:
                raise ValueError(f"Failed to get quote for {symbol}: {e}, {e2}")
    
    async def stream_trades(self, callback: Callable[[Dict], Awaitable]):
        """Stream trade updates via WebSocket"""
        # This requires the websocket connection - simplified for now
        print("[Alpaca] Trade streaming not implemented in this version")
        pass
    
    async def stream_quotes(self, callback: Callable[[Dict], Awaitable]):
        """Stream quote updates via WebSocket"""
        print("[Alpaca] Quote streaming not implemented in this version")
        pass
    
    def get_open_orders(self) -> List[Order]:
        """Get all open orders"""
        orders = self.client.list_orders(status="open")
        return [
            Order(
                id=o.id,
                symbol=o.symbol,
                side=OrderSide.BUY if o.side == "buy" else OrderSide.SELL,
                qty=o.qty,
                status=o.status,
                filled_qty=o.filled_qty,
                filled_avg_price=float(o.filled_avg_price) if o.filled_avg_price else None,
                order_type=o.order_type,
            )
            for o in orders
        ]

    def get_bars(self, symbol: str, limit: int = 100, timeframe: str = "1Day") -> List[Dict]:
        """Fetch historical bars for indicator seeding."""
        try:
            bars = self.client.get_bars(symbol, "1Day", limit=limit).df
            if bars.empty:
                return []
            result = []
            for idx, row in bars.iterrows():
                result.append({
                    "timestamp": idx.isoformat() if hasattr(idx, 'isoformat') else str(idx),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": int(row["volume"])
                })
            return result
        except Exception as e:
            logger.error(f"Failed to fetch historical bars for {symbol}: {e}")
            return []

    async def stream_trades(self, callback: Callable[[Dict], Awaitable], symbols: List[str]):
        """Stream real-time trade updates via WebSocket"""
        try:
            conn = Stream(key_id=self.api_key, secret_key=self.secret_key, base_url="https://paper-api.alpaca.markets", data_feed="iex" if self.paper else "sip")
            
            def _handle_trade(trade):
                if trade.symbol in symbols:
                    asyncio.get_event_loop().call_soon_threadsafe(
                        asyncio.ensure_future,
                        callback({
                            "symbol": trade.symbol,
                            "price": float(trade.price),
                            "size": int(trade.size),
                            "timestamp": str(trade.timestamp),
                        })
                    )
            
            conn.subscribe_trades(_handle_trade, *symbols)
            
            import threading
            def _run_ws():
                conn.run()
            
            ws_thread = threading.Thread(target=_run_ws, daemon=True)
            ws_thread.start()
            
            logger.info(f"[Alpaca] Trade stream connected for {symbols}")
            
        except Exception as e:
            logger.error(f"[Alpaca] Trade stream error: {e}")

    async def stream_bars(self, callback: Callable[[Dict], Awaitable], symbols: List[str]):
        """Stream real-time minute bars via WebSocket"""
        try:
            # Free tier defaults to IEX for both paper and live
            conn = Stream(key_id=self.api_key, secret_key=self.secret_key, base_url="https://paper-api.alpaca.markets", data_feed="iex")
            
            async def _handle_bar(bar):
                if bar.symbol in symbols:
                    await callback({
                        "symbol": bar.symbol,
                        "open": float(bar.open),
                        "high": float(bar.high),
                        "low": float(bar.low),
                        "close": float(bar.close),
                        "volume": int(bar.volume),
                        "timestamp": str(bar.timestamp),
                    })
            
            conn.subscribe_bars(_handle_bar, *symbols)
            
            # Run in a separate thread to not block
            import threading
            def _run_ws():
                conn.run()
            
            ws_thread = threading.Thread(target=_run_ws, daemon=True)
            ws_thread.start()
            
            logger.info(f"[Alpaca] Bar stream connected for {symbols}")
            
        except Exception as e:
            logger.error(f"[Alpaca] Bar stream error: {e}")

    async def stream_quotes(self, callback: Callable[[Dict], Awaitable], symbols: List[str]):
        """Stream real-time quote updates via WebSocket"""
        try:
            conn = Stream(key_id=self.api_key, secret_key=self.secret_key, base_url="https://paper-api.alpaca.markets", data_feed="iex" if self.paper else "sip")
            
            def _handle_quote(quote):
                if quote.symbol in symbols:
                    asyncio.get_event_loop().call_soon_threadsafe(
                        asyncio.ensure_future,
                        callback({
                            "symbol": quote.symbol,
                            "bid": float(quote.bid_price),
                            "ask": float(quote.ask_price),
                            "bid_size": int(quote.bid_size),
                            "ask_size": int(quote.ask_size),
                            "timestamp": str(quote.timestamp),
                        })
                    )
            
            conn.subscribe_quotes(_handle_quote, *symbols)
            
            import threading
            def _run_ws():
                conn.run()
            
            ws_thread = threading.Thread(target=_run_ws, daemon=True)
            ws_thread.start()
            
            logger.info(f"[Alpaca] Quote stream connected for {symbols}")
            
        except Exception as e:
            logger.error(f"[Alpaca] Quote stream error: {e}")
