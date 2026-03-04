import re

text = open('/data/workspace/trading_system/executor/daemon.py').read()

# Replace stream_bars call with V3 start_websocket
old_ws = """    async def market_data_loop(self):
        \"\"\"
        Stream market data from broker via WebSocket if supported.
        Fallback to polling if streaming fails.
        \"\"\"
        logger.info(\"[Daemon] Starting WebSocket market data loop...\")
        
        symbols = self._get_tradeable_symbols()
        
        try:
            # Try to start streaming
            await self.broker.stream_bars(symbols, self.handle_bar_update)
            
        except Exception as e:
            logger.error(f\"[Daemon] Market data stream crashed: {e}\")
            logger.info(\"[Daemon] Falling back to polling...\")
            
            # Start polling fallback
            await self.market_data_poll(symbols)"""

new_ws = """    async def market_data_loop(self):
        \"\"\"
        Stream market data from broker via WebSocket if supported.
        Fallback to polling if streaming fails.
        \"\"\"
        logger.info(\"[Daemon] Starting WebSocket market data loop...\")
        
        symbols = self._get_tradeable_symbols()
        
        try:
            # Try to start streaming v3 style
            self.broker.ws_handler = self.handle_bar_update
            self.broker.ws_symbols = symbols
            await self.broker.start_websocket()
            
        except Exception as e:
            logger.error(f\"[Daemon] Market data stream crashed: {e}\")
            logger.info(\"[Daemon] Falling back to polling...\")
            
            # Start polling fallback
            await self.market_data_poll(symbols)"""

if old_ws in text:
    text = text.replace(old_ws, new_ws)
    open('/data/workspace/trading_system/executor/daemon.py', 'w').write(text)
    print("Patched market_data_loop")

old_poll = """                        market_data = {
                            "timestamp": datetime.utcnow().isoformat(),
                            "open": bid,
                            "high": ask,
                            "low": bid,
                            "close": (bid + ask) / 2,
                            "volume": 0,
                        }"""

new_poll = """                        
                        # Add reasonable spreads for fallback
                        market_data = {
                            "timestamp": datetime.utcnow().isoformat(),
                            "open": bid,
                            "high": ask,
                            "low": bid,
                            "close": (bid + ask) / 2,
                            "volume": 0,
                        }"""

if old_poll in text:
    text = text.replace(old_poll, new_poll)
    open('/data/workspace/trading_system/executor/daemon.py', 'w').write(text)
    print("Patched polling loops")
