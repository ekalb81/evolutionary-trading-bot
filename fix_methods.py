import re

with open('/data/workspace/trading_system/executor/alpaca_broker.py', 'r') as f:
    text = f.read()

text = re.sub(
    r'@conn\.on\(tradeapi\.stream\.WebSocketMessageType\.TRADE\)',
    '@conn.on_trade',
    text
)
text = re.sub(
    r'@conn\.on\(tradeapi\.stream\.WebSocketMessageType\.AMQP\)',
    '@conn.on_bar',
    text
)
text = re.sub(
    r'@conn\.on\(tradeapi\.stream\.WebSocketMessageType\.QUOTE\)',
    '@conn.on_quote',
    text
)
text = re.sub(
    r'await conn\.connect\(\)',
    'conn.run()  # This maps to the correct blocking asyncio task in alpaca-trade-api',
    text
)

with open('/data/workspace/trading_system/executor/alpaca_broker.py', 'w') as f:
    f.write(text)
