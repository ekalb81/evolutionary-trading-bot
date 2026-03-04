import sys

filepath = "/data/workspace/trading_system/executor/alpaca_broker.py"
with open(filepath, 'r') as f:
    content = f.read()
    
# Add stream import
if "from alpaca_trade_api.stream import Stream" not in content:
    content = content.replace(
        "from alpaca_trade_api.rest import REST, APIError", 
        "from alpaca_trade_api.rest import REST, APIError\nfrom alpaca_trade_api.stream import Stream"
    )

with open(filepath, 'w') as f:
    f.write(content)
