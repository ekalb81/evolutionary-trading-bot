#!/usr/bin/env python3
"""
CLI tool for the Orchestrator to monitor and control the trading daemon.

Usage:
  python orc.py status
  python orc.py alert wait
  python orc.py cmd hold <symbol>
  python orc.py cmd trail <symbol> <percent>
  python orc.py cmd close <symbol>
"""

import sys
import json
import time
from datetime import datetime
from pathlib import Path

# Add trading_system to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from trading_system.ipc.channel import IPCChannel, CommandType


def main():
    if len(sys.argv) < 2:
        print("Usage: orc.py [status|alert|cmd]")
        sys.exit(1)
        
    cmd = sys.argv[1].lower()
    ipc = IPCChannel()
    
    if cmd == "status":
        status = ipc.get_status()
        if not status:
            print("Daemon not running or status.json missing.")
            sys.exit(1)
            
        print(f"--- DAEMON STATUS ---")
        print(f"Timestamp:  {status.get('timestamp')}")
        print(f"State:      {status.get('state')}")
        print(f"Strategy:   {status.get('strategy')}")
        print(f"Positions:  {len(status.get('open_positions', []))}")
        
        pos_dict = status.get('positions', {})
        for sym, data in pos_dict.items():
            ext = "(EXTENDED)" if data.get('extended') else ""
            print(f"  - {sym}: {data.get('qty')} shares @ ${data.get('entry_price'):.2f}, held {data.get('bars_held')} bars {ext}")
            
    elif cmd == "alert":
        print("Waiting for alerts from daemon (Ctrl+C to stop)...")
        while True:
            try:
                alert = ipc.wait_for_alert(timeout_seconds=5)
                if alert:
                    print(f"\n[{datetime.utcnow().isoformat()}] ALERT RECEIVED:")
                    print(f"  Type:   {alert.alert_type}")
                    print(f"  Symbol: {alert.symbol}")
                    print(f"  Data:   {json.dumps(alert.data, indent=2)}")
            except KeyboardInterrupt:
                break
                
    elif cmd == "cmd":
        if len(sys.argv) < 4:
            print("Usage: orc.py cmd [hold|trail|close] <symbol> [params]")
            sys.exit(1)
            
        action = sys.argv[2].lower()
        symbol = sys.argv[3].upper()
        
        if action == "hold":
            fname = ipc.send_command(CommandType.HOLD, symbol)
            print(f"Sent HOLD command for {symbol} ({fname})")
            
        elif action == "trail":
            pct = 2.0
            if len(sys.argv) > 4:
                pct = float(sys.argv[4])
            fname = ipc.send_command(CommandType.REPLACE_SL_TRAIL, symbol, {"trail_percent": pct})
            print(f"Sent TRAIL command ({pct}%) for {symbol} ({fname})")
            
        elif action == "close":
            fname = ipc.send_command(CommandType.CLOSE, symbol)
            print(f"Sent CLOSE command for {symbol} ({fname})")
            
        else:
            print(f"Unknown command action: {action}")


if __name__ == "__main__":
    main()
