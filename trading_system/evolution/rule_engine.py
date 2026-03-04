import pandas as pd

def build_series_from_rule(rule, context):
    """
    Recursively build a pandas Series from rule AST.
    context: dict of { ref: pd.Series }
    """
    rtype = rule.get("type")
    
    if rtype == "condition":
        left_ref = rule["left"]
        comp = rule["comparator"]
        right_ref = rule["right"]
        
        left = context[left_ref]
        
        # Handle right reference
        if isinstance(right_ref, dict) and right_ref.get("type") == "constant":
            right_val = right_ref["value"]
            right = pd.Series(right_val, index=left.index)
        elif right_ref in context:
            right = context[right_ref]
        else:
            # Fallback for unknown reference - shouldn't happen
            print(f"Unknown reference: {right_ref}")
            return pd.Series(False, index=left.index)
            
        if comp == ">":
            return left > right
        elif comp == "<":
            return left < right
        elif comp == ">=":
            return left >= right
        elif comp == "<=":
            return left <= right
        elif comp == "==":
            return left == right
        elif comp == "!=":
            return left != right
        elif comp == "crosses_above":
            # crosses_above: Current Left > Right AND Previous Left <= Previous Right
            shift_left = left.shift(1).fillna(0)
            shift_right = right.shift(1).fillna(0)
            return (left > right) & (shift_left <= shift_right)
        elif comp == "crosses_below":
            shift_left = left.shift(1).fillna(0)
            shift_right = right.shift(1).fillna(0)
            return (left < right) & (shift_left >= shift_right)
        else:
            return pd.Series(False, index=left.index)
            
    elif rtype == "logical":
        left_series = build_series_from_rule(rule["left"], context)
        right_series = build_series_from_rule(rule["right"], context)
        
        if rule["operator"] == "AND":
            return left_series & right_series
        elif rule["operator"] == "OR":
            return left_series | right_series
            
    # Default fallback
    return pd.Series(False, index=context[list(context.keys())[0]].index)

def evaluate_rule(df, rule, indicators):
    """
    Evaluate a trading rule on a dataframe.
    
    Args:
        df: DataFrame with price data
        rule: Rule AST
        indicators: List of indicator definitions (from genome)
        
    Returns:
        Boolean Series indicating where rule is True
    """
    # Build context: merge price columns and indicator columns
    context = {}
    
    # Add price columns
    for col in ['open', 'high', 'low', 'close', 'volume']:
        if col in df.columns:
            context[col] = df[col]
    
    # Add indicator columns
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
                context[ind_id + "_lower"] = df[ind_id + "_lower"]
                
    return build_series_from_rule(rule, context)
