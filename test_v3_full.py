import sys
import os

from trading_system.executor.alpaca_broker_v3 import AlpacaBrokerV3

# Load keys
apiKey = os.environ.get("ALPACA_API_KEY")
secKey = os.environ.get("ALPACA_SECRET_KEY")

b = AlpacaBrokerV3(apiKey, secKey, paper=True)

print("Test 1: TradingClient")
try:
    print(b.get_account()["cash"])
except Exception as e:
    print("Trading FAILED", e)

print("Test 2: DataClient")
try:
    print(len(b.get_bars("AAPL", limit=5)))
except Exception as e:
    print("Data FAILED", e)

import asyncio
print("Test 3: WebSocketStream")
async def handle(bar):
    pass
b.ws_handler = handle
b.ws_symbols = ["AAPL"]
try:
    asyncio.run(b.start_websocket())
except Exception as e:
    print("WS FAILED", e)
