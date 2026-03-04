"""
Orchestrator - I am the trading bot's orchestrator.

I monitor the daemon via IPC and respond to alerts autonomously.
This runs as a background task in my session.
"""

import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from trading_system.ipc.channel import IPCChannel, CommandType, OrchestratorAlert


class Orchestrator:
    """
    I am the orchestrator. I:
    1. Poll IPC for alerts from the daemon
    2. Analyze the situation
    3. Decide and act (HOLD, CLOSE, TRAIL)
    4. Log everything to memory
    """
    
    def __init__(self, ipc_dir: str = "/data/workspace/trading_system/ipc"):
        self.ipc = IPCChannel(ipc_dir)
        self.last_checked_alert = None
        
    def analyze_extension_alert(self, alert: OrchestratorAlert) -> str:
        """
        Analyze an EXTENSION_NEEDED alert and decide what to do.
        
        Decision logic:
        - If profit > 8% and strong momentum: TRAIL (let it run)
        - If profit 3-8%: HOLD (wait one more day)
        - If profit < 3% or losing: CLOSE (take what we have)
        """
        data = alert.data or {}
        pnl_pct = data.get("pnl_pct", 0)
        bars_held = data.get("bars_held", 0)
        entry_price = data.get("entry_price", 0)
        current_price = data.get("current_price", 0)
        
        symbol = alert.symbol
        
        # Decision tree
        if pnl_pct > 0.08:
            # >8% profit - convert to trailing stop to lock in gains
            decision = "TRAIL"
            reason = f"Strong profit ({pnl_pct:.1%}) - lock in with trailing stop"
            trail_pct = 3.0  # 3% trailing
            
        elif pnl_pct > 0.03:
            # 3-8% profit - hold but don't trail yet
            decision = "HOLD"
            reason = f"Moderate profit ({pnl_pct:.1%}) - hold for more upside"
            trail_pct = None
            
        else:
            # <3% or losing - close and take what we have
            decision = "CLOSE"
            reason = f"Low profit ({pnl_pct:.1%}) or losing - secure capital"
            trail_pct = None
        
        return decision, reason, trail_pct
    
    def act_on_decision(self, symbol: str, decision: str, reason: str, trail_pct: Optional[float] = None):
        """Execute the decision via IPC"""
        
        if decision == "TRAIL":
            self.ipc.send_command(CommandType.REPLACE_SL_TRAIL, symbol, {"trail_percent": trail_pct})
            print(f"[Orchestrator] ✅ TRAIL {symbol} @ {trail_pct}% trailing - {reason}")
            
        elif decision == "HOLD":
            self.ipc.send_command(CommandType.HOLD, symbol)
            print(f"[Orchestrator] ✅ HOLD {symbol} - {reason}")
            
        elif decision == "CLOSE":
            self.ipc.send_command(CommandType.CLOSE, symbol)
            print(f"[Orchestrator] ✅ CLOSE {symbol} - {reason}")
        
        # Log to memory
        self._log_decision(symbol, decision, reason)
    
    def _log_decision(self, symbol: str, decision: str, reason: str):
        """Log decision to memory"""
        log_path = Path("/data/workspace/trading_system/ipc/orchestrator_log.json")
        
        existing = []
        if log_path.exists():
            with open(log_path) as f:
                existing = json.load(f)
        
        existing.append({
            "timestamp": datetime.utcnow().isoformat(),
            "symbol": symbol,
            "decision": decision,
            "reason": reason,
        })
        
        with open(log_path, 'w') as f:
            json.dump(existing, f, indent=2)
    
    async def check_for_alerts(self) -> Optional[OrchestratorAlert]:
        """Check for new alerts (non-blocking)"""
        # Read any new alert files
        alerts_dir = self.ipc.alerts_dir
        
        # Get most recent alert file
        alert_files = sorted(alerts_dir.glob("*.json"))
        
        if not alert_files:
            return None
        
        latest = alert_files[-1]
        
        # Skip if we already processed this
        if self.last_checked_alert and latest.name == self.last_checked_alert:
            return None
        
        try:
            with open(latest) as f:
                data = json.load(f)
            
            self.last_checked_alert = latest.name
            return OrchestratorAlert(**data)
            
        except Exception as e:
            print(f"[Orchestrator] Error reading alert: {e}")
            return None
    
    async def run_loop(self, interval_seconds: int = 30):
        """
        Main orchestrator loop.
        
        Runs continuously, checking for alerts and responding.
        """
        print("[Orchestrator] Starting orchestrator loop...")
        
        while True:
            try:
                # Check for alerts
                alert = await self.check_for_alerts()
                
                if alert:
                    print(f"[Orchestrator] Received alert: {alert.alert_type} for {alert.symbol}")
                    
                    if alert.alert_type == "EXTENSION_NEEDED":
                        # Analyze and decide
                        decision, reason, trail_pct = self.analyze_extension_alert(alert)
                        
                        # Execute
                        self.act_on_decision(alert.symbol, decision, reason, trail_pct)
                        
                    elif alert.alert_type == "POSITION_CLOSED":
                        print(f"[Orchestrator] Position closed: {alert.symbol} - {alert.data.get('reason')}")
                        
                    elif alert.alert_type == "ORDER_FILLED":
                        print(f"[Orchestrator] Order filled: {alert.symbol}")
                
                # Update status
                status = self.ipc.get_status()
                if status:
                    positions = status.get("open_positions", [])
                    if positions:
                        print(f"[Orchestrator] Monitoring {len(positions)} position(s): {', '.join(positions)}")
                
                await asyncio.sleep(interval_seconds)
                
            except asyncio.CancelledError:
                print("[Orchestrator] Stopping...")
                break
            except Exception as e:
                print(f"[Orchestrator] Error: {e}")
                await asyncio.sleep(5)


async def main():
    orch = Orchestrator()
    await orch.run_loop(interval_seconds=30)


if __name__ == "__main__":
    asyncio.run(main())
