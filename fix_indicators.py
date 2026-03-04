import re

with open("trading_system/evolution/rule_engine.py", "r") as f:
    code = f.read()

# Fix how indicators with sub-columns (like BB and STOCH) resolve their variables in evaluate_rule
new_logic = """    # Add indicator columns
    for ind in indicators:
        ind_id = ind['id']
        # Main output
        if ind_id in df.columns:
            context[ind_id] = df[ind_id]
        
        # Handle complex indicators that generate multiple columns
        if ind['type'] == 'MACD':
            if ind_id + "_macd" in df.columns:
                context[ind_id] = df[ind_id + "_macd"]  # Map main ID to macd line
            if ind_id + "_signal" in df.columns:
                context[ind_id + "_signal"] = df[ind_id + "_signal"]
                
        elif ind['type'] == 'BBANDS':
            # Map ind_id to the middle band by default if explicitly referenced
            if ind_id + "_middle" in df.columns:
                context[ind_id] = df[ind_id + "_middle"]
                context[ind_id + "_middle"] = df[ind_id + "_middle"]
            if ind_id + "_upper" in df.columns:
                context[ind_id + "_upper"] = df[ind_id + "_upper"]
            if ind_id + "_lower" in df.columns:
                context[ind_id + "_lower"] = df[ind_id + "_lower"]"""

code = re.sub(r"    # Add indicator columns\n.*?(?=    return)", new_logic, code, flags=re.DOTALL)

with open("trading_system/evolution/rule_engine.py", "w") as f:
    f.write(code)
print("Fixed indicator reference mapping!")
