#!/usr/bin/env python3
"""
Live Trading Dashboard - View daemon status, positions, and activity log.

Usage:
    python trading_status.py           # Single snapshot
    python trading_status.py --watch   # Live tail mode
"""

import os
import sys
import json
import argparse
import time
from pathlib import Path
from datetime import datetime

IPC_DIR = Path("/data/workspace/trading_system/ipc")
LOG_DIR = Path("/data/workspace/logs")

def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return None

def format_pnl(pnl):
    if pnl is None:
        return "N/A"
    return f"${pnl:,.2f}" if pnl >= 0 else f"-${abs(pnl):,.2f}"

def show_status():
    os.system('clear')
    
    print("=" * 60)
    print("🐉 ALPACA PAPER TRADING - LIVE DASHBOARD")
    print("=" * 60)
    print(f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # === System Health ===
    status_file = IPC_DIR / "status.json"
    status = load_json(status_file)
    
    if status:
        print("📊 SYSTEM STATUS")
        print("-" * 40)
        print(f"  State:       {status.get('state', 'unknown')}")
        print(f"  Strategy:    {status.get('strategy', 'N/A')}")
        
        config = status.get('config', {})
        print(f"  Soft Limit:  {config.get('max_hold_soft', 'N/A')} days")
        print(f"  Hard Limit:  {config.get('max_hold_hard', 'N/A')} days")
        print(f"  Stop Loss:   {config.get('stop_loss_pct', 0)*100:.1f}%")
        print(f"  Take Profit: {config.get('take_profit_pct', 0)*100:.1f}%")
        print()
        
        # === Positions ===
        positions = status.get('positions', {})
        if positions:
            print("📈 OPEN POSITIONS")
            print("-" * 40)
            print(f"{'Symbol':<10} {'Qty':<6} {'Entry':<10} {'Bars':<6} {'Extended':<10}")
            print("-" * 40)
            
            total_market_value = 0
            for sym, pos in positions.items():
                qty = pos.get('qty', 0)
                entry = pos.get('entry_price', 0)
                bars = pos.get('bars_held', 0)
                extended = pos.get('extended', False)
                market_val = qty * entry
                total_market_value += market_val
                
                print(f"{sym:<10} {qty:<6} ${entry:<9.2f} {bars:<6} {'✓' if extended else '✗':<10}")
            
            print("-" * 40)
            print(f"Total Exposure: ${total_market_value:,.2f}")
        else:
            print("📈 POSITIONS: None open")
        print()
    else:
        print("❌ No status available - daemon may not be running")
        print()
    
    # === Recent Activity Log ===
    print("📜 RECENT ACTIVITY (last 15 lines)")
    print("-" * 40)
    
    daemon_log = LOG_DIR / "daemon.log"
    if daemon_log.exists():
        lines = daemon_log.read_text().strip().split('\n')
        for line in lines[-15:]:
            # Colorize by level
            if 'ERROR' in line:
                print(f"  🔴 {line}")
            elif 'WARN' in line:
                print(f"  🟡 {line}")
            elif 'Opened' in line or 'Closed' in line:
                print(f"  🟢 {line}")
            else:
                print(f"  {line}")
    else:
        print("  No daemon log found")
    
    print()
    print("=" * 60)
    print("Press Ctrl+C to exit")

def main():
    parser = argparse.ArgumentParser(description='Trading Bot Dashboard')
    parser.add_argument('--watch', '-w', action='store_true', help='Watch mode (live updates)')
    parser.add_argument('--interval', '-i', type=int, default=5, help='Refresh interval in seconds')
    args = parser.parse_args()
    
    if args.watch:
        try:
            while True:
                show_status()
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n👋 Dashboard stopped")
    else:
        show_status()

if __name__ == "__main__":
    main()
