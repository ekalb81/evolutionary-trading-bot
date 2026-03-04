import re

with open('/data/workspace/trading_system/executor/alpaca_broker_v2.py', 'r') as f:
    text = f.read()

# Add import
if "from alpaca.data.enums import DataFeed" not in text:
    text = text.replace("from alpaca.data.live import StockDataStream", "from alpaca.data.live import StockDataStream\nfrom alpaca.data.enums import DataFeed")

# Replace strings with enums
text = re.sub(r'feed="iex"', 'feed=DataFeed.IEX', text)

with open('/data/workspace/trading_system/executor/alpaca_broker_v2.py', 'w') as f:
    f.write(text)
