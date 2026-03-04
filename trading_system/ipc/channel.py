"""
Inter-Process Communication (IPC) for orchestrator <-> daemon communication.

This provides a simple, platform-agnostic way for the OpenClaw orchestrator
to send commands to the trading daemon and receive status updates.

Two mechanisms:
1. Command Queue (file-based): Orchestrator writes commands, daemon reads
2. Status File: Daemon writes status, orchestrator reads

This works across process boundaries and survives restarts on either side.
"""

import os
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum


class CommandType(Enum):
    """Commands the orchestrator can send to the daemon"""
    HOLD = "hold"           # Extend position beyond soft limit
    CLOSE = "close"         # Close position immediately
    SCALE = "scale"         # Scale in/out of position
    CANCEL_ALL = "cancel_all"
    REPLACE_SL_TRAIL = "replace_sl_trailing"  # Replace static SL with trailing
    STATUS = "status"       # Request status update
    STOP_DAEMON = "stop"    # Gracefully stop the daemon


@dataclass
class DaemonCommand:
    """A command sent from orchestrator to daemon"""
    command: CommandType
    symbol: Optional[str] = None
    params: Optional[Dict[str, Any]] = None  # e.g., {"trail_percent": 2.0} for REPLACE_SL_TRAIL
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()


@dataclass
class OrchestratorAlert:
    """An alert sent from daemon to orchestrator"""
    alert_type: str  # EXTENSION_NEEDED, POSITION_CLOSED, ERROR, etc.
    symbol: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()


class IPCChannel:
    """
    File-based IPC channel.
    
    Directory structure:
        ipc/
            commands/     # Orchestrator writes commands here
            alerts/       # Daemon writes alerts here
            status.json   # Daemon writes current status here
            lock          # Optional lock file
    """
    
    def __init__(self, ipc_dir: str = "/data/workspace/trading_system/ipc"):
        self.ipc_dir = Path(ipc_dir)
        self.commands_dir = self.ipc_dir / "commands"
        self.alerts_dir = self.ipc_dir / "alerts"
        
        # Create directories
        self.commands_dir.mkdir(parents=True, exist_ok=True)
        self.alerts_dir.mkdir(parents=True, exist_ok=True)
    
    # ==================== ORCHESTRATOR METHODS ====================
    
    def send_command(self, command: CommandType, symbol: Optional[str] = None, 
                     params: Optional[Dict] = None) -> str:
        """
        Send a command to the daemon.
        
        Returns the command filename for tracking.
        """
        cmd = DaemonCommand(command=command, symbol=symbol, params=params)
        filename = f"{command.value}_{symbol or 'global'}_{int(time.time() * 1000)}.json"
        filepath = self.commands_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(asdict(cmd), f)
        
        return filename
    
    def wait_for_alert(self, timeout_seconds: float = 30, poll_interval: float = 1.0) -> Optional[OrchestratorAlert]:
        """
        Wait for the next alert from the daemon.
        
        Returns None on timeout.
        """
        start = time.time()
        seen_files = set(f.name for f in self.alerts_dir.glob("*.json"))
        
        while time.time() - start < timeout_seconds:
            current_files = set(f.name for f in self.alerts_dir.glob("*.json"))
            new_files = current_files - seen_files
            
            for fname in sorted(new_files):
                try:
                    with open(self.alerts_dir / fname) as f:
                        data = json.load(f)
                    # Don't delete - keep for history
                    return OrchestratorAlert(**data)
                except Exception:
                    pass
            
            seen_files = current_files
            time.sleep(poll_interval)
        
        return None
    
    # ==================== DAEMON METHODS ====================
    
    def read_pending_commands(self) -> List[DaemonCommand]:
        """Read all pending commands from the orchestrator"""
        commands = []
        
        for filepath in sorted(self.commands_dir.glob("*.json")):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                cmd = DaemonCommand(**data)
                commands.append(cmd)
                
                # Mark as processed (move to processed folder)
                processed_dir = self.commands_dir / "processed"
                processed_dir.mkdir(exist_ok=True)
                filepath.rename(processed_dir / filepath.name)
                
            except Exception as e:
                print(f"[IPC] Error reading command {filepath}: {e}")
        
        return commands
    
    def write_alert(self, alert_type: str, symbol: Optional[str] = None, 
                   data: Optional[Dict] = None):
        """Write an alert for the orchestrator"""
        alert = OrchestratorAlert(alert_type=alert_type, symbol=symbol, data=data)
        filename = f"{alert_type}_{symbol or 'global'}_{int(time.time() * 1000)}.json"
        filepath = self.alerts_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(asdict(alert), f)
        
        print(f"[IPC] Alert written: {alert_type} for {symbol}")
    
    def update_status(self, status: Dict[str, Any]):
        """Update the daemon status file"""
        status_path = self.ipc_dir / "status.json"
        
        full_status = {
            "timestamp": datetime.utcnow().isoformat(),
            **status
        }
        
        with open(status_path, 'w') as f:
            json.dump(full_status, f, indent=2)
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """Read current daemon status"""
        status_path = self.ipc_dir / "status.json"
        
        if not status_path.exists():
            return None
        
        try:
            with open(status_path) as f:
                return json.load(f)
        except Exception:
            return None


# Convenience functions for quick use
def send_command(command: CommandType, symbol: Optional[str] = None, 
                params: Optional[Dict] = None) -> str:
    """Quick command send"""
    channel = IPCChannel()
    return channel.send_command(command, symbol, params)


def alert(alert_type: str, symbol: Optional[str] = None, data: Optional[Dict] = None):
    """Quick alert send"""
    channel = IPCChannel()
    channel.write_alert(alert_type, symbol, data)
