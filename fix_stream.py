import re

with open('/data/workspace/trading_system/executor/alpaca_broker_v2.py', 'r') as f:
    text = f.read()

# Fix streams
def fix_stream(match):
    return '        stream = StockDataStream(self.api_key, self.secret_key, feed="iex")'

text = re.sub(r'\s*url_override = .*?\n\s*stream = StockDataStream\(self.api_key, self.secret_key, url_override=url_override\)', 
              fix_stream, text)

with open('/data/workspace/trading_system/executor/alpaca_broker_v2.py', 'w') as f:
    f.write(text)
