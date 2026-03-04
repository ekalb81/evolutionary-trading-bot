import re

with open("trading_system/evolution/evolve.py", "r") as f:
    code = f.read()

# Add import for the rule engine at the top
if "from trading_system.evolution.rule_engine import evaluate_rule" not in code:
    code = code.replace("from trading_system.data.cache import DataCache", 
                        "from trading_system.data.cache import DataCache\nfrom trading_system.evolution.rule_engine import evaluate_rule")

# Fix run_backtest to use fast vectorized evaluation
new_backtest = """def run_backtest(symbol: str, df: pd.DataFrame, genome: dict) -> list[dict]:
    \"\"\"Run backtest using vectorized rule evaluation.\"\"\"
    trades = []
    
    indicators = genome.get('indicators', [])
    df = compute_indicators(df, indicators)
    df = df.dropna().reset_index(drop=True)
    
    if len(df) < 20:
        return trades
        
    entry_rule = genome.get('entry_rule')
    exit_rule = genome.get('exit_rule')
    risk = genome.get('risk_management', {})
    
    sl_pct = risk.get('stop_loss_pct', 0.05)
    tp_pct = risk.get('take_profit_pct', 0.10)
    max_bars = risk.get('max_hold_bars', 100)
    
    # 1. Evaluate the entire rule AST in one vectorized pass!
    # Much faster than iterating row-by-row
    try:
        entries = evaluate_rule(df, entry_rule, indicators)
    except Exception as e:
        # If AST is completely broken, fail gracefully
        return []
        
    # Optional soft exits
    soft_exits = np.zeros(len(df), dtype=bool)
    if exit_rule:
        try:
            soft_exits = evaluate_rule(df, exit_rule, indicators)
        except Exception:
            pass
            
    position = None
    entry_price = 0
    entry_bar = 0
    
    closes = df['close'].values
    
    # Still need to iterate for stateful position management (stops/targets)
    for i in range(1, len(df)):
        if position is None:
            if entries.iloc[i]:  # Buy signal
                position = 'long'
                entry_price = closes[i]
                entry_bar = i
        
        elif position == 'long':
            current_price = closes[i]
            pnl_pct = (current_price - entry_price) / entry_price
            
            bars_held = i - entry_bar
            
            # Check exits in priority order
            if pnl_pct <= -sl_pct:
                trades.append({'symbol': symbol, 'entry_price': entry_price, 'exit_price': current_price, 'pnl_pct': pnl_pct, 'bars_held': bars_held, 'type': 'stop_loss'})
                position = None
            elif pnl_pct >= tp_pct:
                trades.append({'symbol': symbol, 'entry_price': entry_price, 'exit_price': current_price, 'pnl_pct': pnl_pct, 'bars_held': bars_held, 'type': 'take_profit'})
                position = None
            elif bars_held >= max_bars:
                trades.append({'symbol': symbol, 'entry_price': entry_price, 'exit_price': current_price, 'pnl_pct': pnl_pct, 'bars_held': bars_held, 'type': 'time_exit'})
                position = None
            elif soft_exits[i]:
                trades.append({'symbol': symbol, 'entry_price': entry_price, 'exit_price': current_price, 'pnl_pct': pnl_pct, 'bars_held': bars_held, 'type': 'soft_exit'})
                position = None
                
    # Close EOD open positions
    if position == 'long':
        pnl_pct = (closes[-1] - entry_price) / entry_price
        trades.append({'symbol': symbol, 'entry_price': entry_price, 'exit_price': closes[-1], 'pnl_pct': pnl_pct, 'bars_held': len(df) - entry_bar, 'type': 'eod'})
        
    return trades
"""

# Replace the run_backtest function
code = re.sub(r"def run_backtest\(.*?\n(.*?)(?=\ndef calculate_fitness)", new_backtest, code, flags=re.DOTALL)

with open("trading_system/evolution/evolve.py", "w") as f:
    f.write(code)

print("Fixed evolve.py backtest logic!")
