import re

with open('/data/workspace/trading_system/executor/alpaca_broker.py', 'r') as f:
    text = f.read()

# Make sure self.paper exists
if "self.paper = paper" not in text:
    text = text.replace("self.secret_key = secret_key", "self.secret_key = secret_key\n        self.paper = paper")

with open('/data/workspace/trading_system/executor/alpaca_broker.py', 'w') as f:
    f.write(text)
