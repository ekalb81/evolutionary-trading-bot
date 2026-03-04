#!/usr/bin/env python3
"""
Evolution Runner - Main loop for backtesting and fitness evaluation.
"""
import json
import math
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from trading_system.data.yfinance_provider import YFinanceProvider
from trading_system.data.cache import DataCache
from trading_system.evolution.rule_engine import evaluate_rule


def load_universe(csv_path: str = "data/universe/us_equities_20.csv") -> list[str]:
    """Load stock symbols from universe CSV."""
    df = pd.read_csv(csv_path)
    return df['symbol'].tolist()


def load_population(path: str = "data/evolution/gen_000/population.json") -> list[dict]:
    """Load strategy population."""
    with open(path) as f:
        return json.load(f)


def compute_indicators(df: pd.DataFrame, indicators: list[dict]) -> pd.DataFrame:
    """Compute indicators for a dataframe."""
    df = df.copy()
    for ind in indicators:
        ind_id = ind['id']
        ind_type = ind['type']
        params = ind.get('params', {})
        
        if ind_type == 'SMA':
            period = params.get('period', 20)
            df[ind_id] = df['close'].rolling(window=period).mean()
        elif ind_type == 'EMA':
            period = params.get('period', 20)
            df[ind_id] = df['close'].ewm(span=period, adjust=False).mean()
        elif ind_type == 'RSI':
            period = params.get('period', 14)
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss
            df[ind_id] = 100 - (100 / (1 + rs))
        elif ind_type == 'BBANDS':
            period = params.get('period', 20)
            sma = df['close'].rolling(window=period).mean()
            std = df['close'].rolling(window=period).std()
            df[f"{ind_id}_upper"] = sma + (std * 2)
            df[f"{ind_id}_middle"] = sma
            df[f"{ind_id}_lower"] = sma - (std * 2)
        elif ind_type == 'MACD':
            fast = params.get('fast', 12)
            slow = params.get('slow', 26)
            signal = params.get('signal', 9)
            ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
            ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
            df[f"{ind_id}_macd"] = ema_fast - ema_slow
            df[f"{ind_id}_signal"] = df[f"{ind_id}_macd"].ewm(span=signal, adjust=False).mean()
        elif ind_type == 'ATR':
            period = params.get('period', 14)
            high_low = df['high'] - df['low']
            high_close = (df['high'] - df['close'].shift()).abs()
            low_close = (df['low'] - df['close'].shift()).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            df[ind_id] = tr.rolling(window=period).mean()
    
    return df


def evaluate_entry_rule(row: pd.Series, rule: dict, df: pd.DataFrame) -> bool:
    """Evaluate entry rule condition."""
    if not rule:
        return False
    
    rule_type = rule.get('type', 'condition')
    
    if rule_type == 'condition':
        left = rule.get('left')
        comparator = rule.get('comparator')
        right = rule.get('right')
        
        # Get left value
        if left in df.columns:
            left_val = row.get(left)
        elif left.startswith('px:'):
            col = left.replace('px:', '')
            left_val = row.get(col)
        else:
            left_val = None
        
        # Get right value
        if right in df.columns:
            right_val = row.get(right)
        elif isinstance(right, dict) and right.get('type') == 'constant':
            right_val = right.get('value')
        elif isinstance(right, (int, float)):
            right_val = right
        else:
            right_val = None
        
        if left_val is None or right_val is None:
            return False
        
        # Evaluate comparator
        if comparator == '>':
            return left_val > right_val
        elif comparator == '<':
            return left_val < right_val
        elif comparator == '>=':
            return left_val >= right_val
        elif comparator == '<=':
            return left_val <= right_val
        elif comparator == 'crosses_above':
            # Need previous row for crossover detection
            return False  # Simplified
        elif comparator == 'crosses_below':
            return False  # Simplified
    
    return False


def run_backtest(symbol: str, df: pd.DataFrame, genome: dict) -> list[dict]:
    """Run backtest using vectorized rule evaluation."""
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

def calculate_fitness(trades: list[dict]) -> dict:
    """Calculate fitness metrics for a strategy."""
    if not trades:
        return {
            'fitness': 0,
            'sortino': 0,
            'calmar': 0,
            'profit_factor': 0,
            'total_trades': 0,
            'max_drawdown': 1,
            'win_rate': 0,
            'complexity': 0
        }
    
    pnls = [t['pnl_pct'] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    
    total_trades = len(trades)
    win_rate = len(wins) / total_trades if total_trades > 0 else 0
    
    # Profit factor
    gross_profit = sum(wins) if wins else 0.001
    gross_loss = abs(sum(losses)) if losses else 0.001
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
    
    # Sortino (simplified - use downside deviation)
    returns = np.array(pnls)
    downside_returns = returns[returns < 0]
    downside_dev = np.std(downside_returns) if len(downside_returns) > 0 else 0.001
    mean_return = np.mean(returns)
    sortino = mean_return / downside_dev if downside_dev > 0 else 0
    
    # Calmar (simplified - use max drawdown)
    cumulative = np.cumprod(1 + returns)
    running_max = np.maximum.accumulate(cumulative)
    drawdowns = (running_max - cumulative) / running_max
    max_drawdown = np.max(drawdowns) if len(drawdowns) > 0 else 1
    
    annualized_return = mean_return * 252  # Assume daily
    calmar = annualized_return / max_drawdown if max_drawdown > 0 else 0
    
    return {
        'fitness': 0,  # Will be computed after complexity
        'sortino': sortino,
        'calmar': calmar,
        'profit_factor': profit_factor,
        'total_trades': total_trades,
        'max_drawdown': max_drawdown,
        'win_rate': win_rate,
        'complexity': 0
    }


def compute_composite_fitness(metrics: dict, indicator_count: int) -> float:
    """Compute composite fitness score."""
    w1, w2, w3 = 0.40, 0.40, 0.20
    
    sortino = max(0, metrics['sortino'])
    calmar = max(0, metrics['calmar'])
    pf = metrics['profit_factor']
    
    base = w1 * sortino + w2 * calmar + w3 * pf
    
    # Trade frequency penalty
    trades = metrics['total_trades']
    n_target = 50
    freq_penalty = min(1.0, (trades / n_target) ** 2)
    
    # Complexity penalty
    complexity = max(0, indicator_count - 3)
    lambda_decay = 0.05
    comp_penalty = math.exp(-lambda_decay * complexity)
    
    fitness = base * freq_penalty * comp_penalty
    
    return fitness


def run_evolution():
    """Main evolution loop."""
    print("=" * 60)
    print("EVOLUTION RUNNER - Generation 0")
    print("=" * 60)
    
    # Load universe
    universe = load_universe()
    print(f"Universe: {len(universe)} symbols")
    
    # Load population
    population = load_population()
    print(f"Population: {len(population)} strategies")
    
    # Initialize data provider
    cache = DataCache()
    provider = YFinanceProvider(cache)
    
    # Date range (2 years)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=730)
    
    # Fetch all data first
    print(f"\nFetching historical data ({start_date.date()} to {end_date.date()})...")
    data_cache = {}
    for symbol in universe:
        print(f"  Fetching {symbol}...", end=" ", flush=True)
        df = provider.get_bars(symbol, "1d", start_date, end_date)
        if df is not None and not df.empty:
            data_cache[symbol] = df
            print(f"OK ({len(df)} bars)")
        else:
            print("FAILED")
    
    print(f"\nData cached: {len(data_cache)} symbols")
    
    # Run backtests
    results = []
    total = len(population)
    
    print(f"\nRunning backtests...")
    for idx, genome in enumerate(population):
        if (idx + 1) % 20 == 0 or idx == 0:
            print(f"  Progress: {idx + 1}/{total} strategies...")
        
        all_trades = []
        
        # Run on each symbol
        for symbol, df in data_cache.items():
            trades = run_backtest(symbol, df, genome)
            all_trades.extend(trades)
        
        # Calculate metrics
        metrics = calculate_fitness(all_trades)
        metrics['strategy_id'] = genome['id']
        metrics['strategy_name'] = genome.get('name', 'unknown')
        
        # Add complexity from indicator count
        indicator_count = len(genome.get('indicators', []))
        metrics['complexity'] = indicator_count
        
        # Compute composite fitness
        metrics['fitness'] = compute_composite_fitness(metrics, indicator_count)
        
        results.append(metrics)
    
    # Sort by fitness
    results.sort(key=lambda x: x['fitness'], reverse=True)
    
    # Get top 10
    top_10 = [r['strategy_id'] for r in results[:10]]
    
    # Save results
    output = {
        'generation': 0,
        'total_strategies': total,
        'results': results,
        'top_10': top_10,
        'timestamp': datetime.now().isoformat()
    }
    
    output_path = "data/evolution/gen_000/results.json"
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Total strategies evaluated: {total}")
    print(f"Results saved to: {output_path}")
    print(f"\nTop 10 Strategies:")
    for i, r in enumerate(results[:10], 1):
        print(f"  {i}. {r['strategy_name']}")
        print(f"     Fitness: {r['fitness']:.3f} | Trades: {r['total_trades']} | Win: {r['win_rate']*100:.1f}% | DD: {r['max_drawdown']*100:.1f}%")
    
    return output


if __name__ == "__main__":
    run_evolution()
