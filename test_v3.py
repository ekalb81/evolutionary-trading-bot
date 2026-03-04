import sys
import os

from trading_system.executor.alpaca_broker_v3 import AlpacaBrokerV3

# Load keys
apiKey = os.environ.get("ALPACA_API_KEY")
secKey = os.environ.get("ALPACA_SECRET_KEY")

print(f"API_KEY: {apiKey[:5]}...{apiKey[-5:] if apiKey else 'None'}")

# Test 1 - directly pass
print("Test 1: Direct pass")
try:
    b1 = AlpacaBrokerV3(apiKey, secKey, paper=True)
    res = b1.get_account()
    print("SUCCESS:", res["cash"])
except Exception as e:
    import traceback
    traceback.print_exc()

