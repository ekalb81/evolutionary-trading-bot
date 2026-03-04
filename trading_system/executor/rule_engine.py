"""
Rule Engine for trading strategy evaluation.

Supports both batch backtesting (DataFrame) and real-time (dict) evaluation.
"""

import pandas as pd


def build_series_from_rule(rule, context):
    """
    Recursively build a result from rule AST.
    context: dict of { ref: value } - can be Series (backtest) or scalar/dict (realtime)
    """
    rtype = rule.get("type")
    
    if rtype == "condition":
        left_ref = rule["left"]
        comp = rule["comparator"]
        right_ref = rule["right"]
        
        # Get left value
        if left_ref in context:
            left_val = context[left_ref]
        else:
            print(f"Unknown reference: {left_ref}")
            return False
        
        # Get right value
        if isinstance(right_ref, dict) and right_ref.get("type") == "constant":
            right_val = right_ref["value"]
        elif right_ref in context:
            right_val = context[right_ref]
        else:
            print(f"Unknown reference: {right_ref}")
            return False
        
        # Handle comparison
        # For real-time: both might be scalars
        # For backtest: both might be Series
        
        if comp == ">":
            return left_val > right_val
        elif comp == "<":
            return left_val < right_val
        elif comp == ">=":
            return left_val >= right_val
        elif comp == "<=":
            return left_val <= right_val
        elif comp == "==":
            return left_val == right_val
        elif comp == "!=":
            return left_val != right_val
        elif comp == "crosses_above":
            # For real-time, we can't do crosses easily without history
            # Simplified: check if left > right
            return left_val > right_val
        elif comp == "crosses_below":
            return left_val < right_val
        else:
            return False
            
    elif rtype == "logical":
        left_result = build_series_from_rule(rule["left"], context)
        right_result = build_series_from_rule(rule["right"], context)
        
        if rule["operator"] == "AND":
            return left_result and right_result
        elif rule["operator"] == "OR":
            return left_result or right_result
            
    # Default fallback
    return False


def evaluate_rule(context, rule, indicators):
    """
    Evaluate a trading rule.
    
    For real-time (context is dict):
        Returns bool directly
    For backtest (context is DataFrame):
        Returns boolean Series
        
    Args:
        context: dict (realtime) or DataFrame (backtest)
        rule: Rule AST
        indicators: List of indicator definitions (from genome)
        
    Returns:
        Boolean (realtime) or Boolean Series (backtest)
    """
    # Check if we're in real-time (dict) or backtest (DataFrame) mode
    if isinstance(context, pd.DataFrame):
        # Backtest mode - build context from DataFrame
        ctx = {}
        
        # Add price columns
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in context.columns:
                ctx[col] = context[col]
        
        # Add indicator columns
        for ind in indicators:
            ind_id = ind['id']
            if ind_id in context.columns:
                ctx[ind_id] = context[ind_id]
            
            # Handle complex indicators (BBANDS, MACD)
            if ind.get('type') == 'BBANDS':
                for suffix in ['_upper', '_middle', '_lower']:
                    col = ind_id + suffix
                    if col in context.columns:
                        ctx[col] = context[col]
            elif ind.get('type') == 'MACD':
                for suffix in ['_macd', '_signal', '_hist']:
                    col = ind_id + suffix
                    if col in context.columns:
                        ctx[col] = context[col]
        
        # For backtest, we need to evaluate the last row
        last_row = ctx
        result = build_series_from_rule(rule, ctx)
        
        # If result is a Series, get the last value
        if isinstance(result, pd.Series):
            return result.iloc[-1] if len(result) > 0 else False
        return result
        
    else:
        # Real-time mode - context is already a dict
        # Add indicators (would need real-time calculation in production)
        ctx = dict(context)
        
        # For now, use basic price data
        # In production, we'd compute indicators from recent bars
        
        return build_series_from_rule(rule, ctx)
