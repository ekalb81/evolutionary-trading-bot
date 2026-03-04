import re

with open('/data/workspace/trading_system/executor/alpaca_broker.py', 'r') as f:
    text = f.read()

# Fix mangled stream initialization in stream_trades
text = re.sub(
    r'feed = "iex" if self\.paper else "sip"\n\s+conn = Stream\(\n\s+self\.api_key,\n\s+self\.secret_key,\n\s+base_url=self\.base_url,\n\s+data_feed=feed if self\.paper else "sip"\n\s+conn = Stream\(\n\s+self\.api_key,\n\s+self\.secret_key,\n\s+base_url=self\.base_url,\n\s+data_feed=feed\n\s+\)',
    'conn = Stream(key_id=self.api_key, secret_key=self.secret_key, base_url=self.base_url, data_feed="iex" if self.paper else "sip")',
    text
)

with open('/data/workspace/trading_system/executor/alpaca_broker.py', 'w') as f:
    f.write(text)
