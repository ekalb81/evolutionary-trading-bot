"""
Trading Daemon - runs the trading engine in the background.

This is the entry point for the live trading system. It:
1. Loads the strategy genome
2. Connects to the broker (Alpaca)
3. Sets up WebSocket streams for real-time data
4. Runs the trading engine loop
5. Handles IPC communication with the orchestrator

Usage:
    python -m trading_system.executor.daemon [--live]
"""

import os
import sys
import json
import asyncio
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

# Add trading_system to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from trading_system.executor.alpaca_broker import AlpacaBroker
from trading_system.executor.engine import TradingEngine
from trading_system.ipc.channel import IPCChannel


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class TradingDaemon:
    """
    Main daemon that runs the trading system.
    
    Manages:
    - Broker connection
    - Trading engine
    - WebSocket streams (market data + trade updates)
    - IPC channel (orchestrator communication)
    - Scheduled tasks (EOD checks, etc.)
    """
    
    def __init__(
        self,
        strategy_path: str,
        paper: bool = True,
        ipc_dir: Optional[str] = None,
    ):
        self.paper = paper
        
        # Load strategy
        with open(strategy_path) as f:
            self.strategy = json.load(f)
        
        logger.info(f"[Daemon] Loaded strategy: {self.strategy.get('name')}")
        
        # Initialize broker
        api_key = os.getenv("ALPACA_API_KEY")
        secret_key = os.getenv("ALPACA_SECRET_KEY")
        
        if not api_key or not secret_key:
            raise ValueError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set")
        
        self.broker = AlpacaBroker(
            api_key=api_key,
            secret_key=secret_key,
            paper=paper,
        )
        
        # Initialize IPC
        self.ipc = IPCChannel(ipc_dir or "/data/workspace/trading_system/ipc")
        
        # Initialize engine
        self.engine = TradingEngine(
            broker=self.broker,
            strategy_genome=self.strategy,
            ipc_channel=self.ipc,
            config={
                "symbols": self._get_tradeable_symbols(),
            },
        )
        
        # State
        self.running = False
        self.market_data_cache: Dict[str, Dict] = {}
        
    def _get_tradeable_symbols(self) -> list:
        """Get list of symbols to trade from strategy or universe"""
        # Top 25 most liquid US large-cap equities (staying under Alpaca's ~30 stream limit)
        # Covers tech, finance, healthcare, consumer, energy - diverse enough for the strategy
        return [
            "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",  # Tech top 5
            "META", "TSLA", "NFLX", "AMD", "INTC",   # Tech continued
            "JPM", "BAC", "WFC", "GS", "C",          # Finance
            "UNH", "JNJ", "PFE", "MRK", "ABBV",      # Healthcare
            "XOM", "CVX", "SHEL", "COP",             # Energy
            "SPY", "QQQ", "IWM", "DIA",              # ETFs
        ]
    
    async def handle_trade_update(self, update: Dict):
        """Handle incoming trade update from WebSocket"""
        event = update.get("event")
        symbol = update.get("symbol")
        
        logger.info(f"[Daemon] Trade update: {event} for {symbol}")
        
        if event == "fill":
            # Position opened or closed
            self.ipc.write_alert(
                alert_type="ORDER_FILLED",
                symbol=symbol,
                data=update,
            )
            
        elif event == "cancel":
            self.ipc.write_alert(
                alert_type="ORDER_CANCELLED",
                symbol=symbol,
                data=update,
            )
    
    async def handle_quote_update(self, update: Dict):
        """Handle incoming quote update from WebSocket"""
        symbol = update.get("symbol")
        
        # Update cache with latest quote
        self.market_data_cache[symbol] = {
            "timestamp": update.get("timestamp"),
            "bid": update.get("bid_price"),
            "ask": update.get("ask_price"),
            "close": (update.get("bid_price", 0) + update.get("ask_price", 0)) / 2,
            "volume": 0,  # Quotes don't have volume
        }
    
    async def handle_bar_update(self, bar: Dict):
        """Handle incoming 1-minute bar update from WebSocket"""
        symbol = bar.get("symbol")
        if not symbol:
            return
            
        market_data = {
            "timestamp": bar.get("timestamp"),
            "open": float(bar.get("open", 0)),
            "high": float(bar.get("high", 0)),
            "low": float(bar.get("low", 0)),
            "close": float(bar.get("close", 0)),
            "volume": int(bar.get("volume", 0)),
        }
        
        # Process through engine immediately on bar close
        self.engine.process_market_data(symbol, market_data)

    async def market_data_loop(self):
        """
        Main market data processing loop.
        Connects directly to Alpaca WebSocket stream for real-time 1Min bars.
        """
        logger.info("[Daemon] Starting WebSocket market data loop...")
        
        symbols = self.engine.config.get("symbols", [])
        if not symbols:
            logger.warning("[Daemon] No symbols configured to monitor")
            return
            
        # Instead of while-loop polling, we hook the streaming API
        try:
            # `self.broker.stream_bars` runs internally using `conn.run()` blocking the async
            # So we await it. It will reconnect automatically on drops.
            await self.broker.stream_bars(self.handle_bar_update, symbols)
        except Exception as e:
            logger.error(f"[Daemon] Market data stream crashed: {e}")
            logger.info("[Daemon] Falling back to polling...")
            await self.market_data_fallback_poll()
            
    async def market_data_fallback_poll(self):
        """Original polling fallback if WebSockets fail"""
        while self.running:
            try:
                for symbol in self.engine.config.get("symbols", []):
                    try:
                        quote = self.broker.get_latest_quote(symbol)
                        market_data = {
                            "timestamp": datetime.utcnow().isoformat(),
                            "open": quote["bid"],  # Simplified
                            "high": quote["ask"],
                            "low": quote["bid"],
                            "close": (quote["bid"] + quote["ask"]) / 2,
                            "volume": 0,
                        }
                        
                        # Process through engine
                        self.engine.process_market_data(symbol, market_data)
                        
                    except Exception as e:
                        logger.error(f"[Daemon] Error processing {symbol}: {e}")
                
                # Sleep between iterations
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"[Daemon] Market data loop error: {e}")
                await asyncio.sleep(5)
    
    async def command_loop(self):
        """
        Process commands from orchestrator.
        
        This runs alongside the market data loop.
        """
        logger.info("[Daemon] Starting command loop...")
        
        while self.running:
            try:
                # Process any pending commands
                self.engine.process_commands()
                
                # Update status
                status = self.engine.get_status()
                self.ipc.update_status(status)
                
                await asyncio.sleep(2)  # Check every 2 seconds
                
            except Exception as e:
                logger.error(f"[Daemon] Command loop error: {e}")
                await asyncio.sleep(1)
    
    async def run_websocket_streams(self):
        """Run WebSocket streams for real-time updates"""
        logger.info("[Daemon] Starting WebSocket streams...")
        
        # These run in the background
        try:
            await self.broker.stream_trades(self.handle_trade_update)
        except Exception as e:
            logger.warning(f"[Daemon] Trade stream error (falling back to polling): {e}")
    
    async def run_async(self):
        """Run the daemon asynchronously"""
        self.running = True
        
        logger.info(f"[Daemon] Starting {'PAPER' if self.paper else 'LIVE'} trading daemon...")
        
        # Check account
        account = self.broker.get_account()
        logger.info(f"[Daemon] Account equity: ${account['equity']:,.2f}")
        
        # Write initial status
        self.ipc.update_status({
            "state": "starting",
            "strategy": self.strategy.get("name"),
            "paper": self.paper,
            "account_equity": account["equity"],
        })
        
        # Start background tasks
        try:
            # Run market data loop and command loop concurrently
            await asyncio.gather(
                self.market_data_loop(),
                self.command_loop(),
                # WebSocket streams when working:
                # self.run_websocket_streams(),
            )
        except asyncio.CancelledError:
            logger.info("[Daemon] Daemon cancelled")
        finally:
            self.running = False
            self.engine.stop()
    
    def run(self):
        """Run the daemon (sync wrapper)"""
        try:
            asyncio.run(self.run_async())
        except KeyboardInterrupt:
            logger.info("[Daemon] Interrupted by user")
            self.running = False


def main():
    parser = argparse.ArgumentParser(description="Trading Daemon")
    parser.add_argument(
        "--strategy",
        default="/data/workspace/trading_system/strategies/live_strategy.json",
        help="Path to strategy JSON file",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use live trading (default is paper)",
    )
    parser.add_argument(
        "--ipc-dir",
        default="/data/workspace/trading_system/ipc",
        help="IPC directory",
    )
    
    args = parser.parse_args()
    
    daemon = TradingDaemon(
        strategy_path=args.strategy,
        paper=not args.live,
        ipc_dir=args.ipc_dir,
    )
    
    daemon.run()


if __name__ == "__main__":
    main()
