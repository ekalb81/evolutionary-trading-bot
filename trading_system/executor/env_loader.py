#!/usr/bin/env python3
"""
Environment loader for trading system.
Handles consistency across different .env file formats.
"""

import os
from pathlib import Path


def load_env(env_file: str = None) -> dict:
    """
    Load environment variables from a .env file.
    
    Supports:
    - ALPACA_API_KEY / ALPACA_SECRET_KEY (preferred)
    - API_KEY / API_SECRET (fallback)
    - ALPACA_BASE_URL / APCA_API_BASE_URL (URL override)
    
    Returns dict of loaded values for debugging.
    """
    if env_file is None:
        env_file = os.getenv("TRADING_ENV_FILE", ".trader.env")
    
    env_path = Path(env_file)
    if not env_path.exists():
        # Try current directory
        env_path = Path(".") / env_file
        if not env_path.exists():
            return {}
    
    loaded = {}
    
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                
                # Store in loaded dict
                loaded[key] = value
                
                # Set in os.environ if not already set (preserve existing)
                if key not in os.environ:
                    os.environ[key] = value
    
    # Normalize key names for Alpaca SDK compatibility
    # The alpaca-py SDK looks for these specific env vars:
    
    # Map API_KEY -> ALPACA_API_KEY if needed
    if "API_KEY" in loaded and "ALPACA_API_KEY" not in os.environ:
        os.environ["ALPACA_API_KEY"] = loaded["API_KEY"]
    
    # Map API_SECRET -> ALPACA_SECRET_KEY if needed  
    if "API_SECRET" in loaded and "ALPACA_SECRET_KEY" not in os.environ:
        os.environ["ALPACA_SECRET_KEY"] = loaded["API_SECRET"]
    
    # Map ALPACA_BASE_URL -> APCA_API_BASE_URL if needed (alpaca-py looks for this)
    if "ALPACA_BASE_URL" in loaded and "APCA_API_BASE_URL" not in os.environ:
        os.environ["APCA_API_BASE_URL"] = loaded["ALPACA_BASE_URL"]
    
    return loaded


def get_alpaca_credentials() -> tuple:
    """Return (api_key, secret_key) with fallbacks."""
    api_key = os.environ.get("ALPACA_API_KEY") or os.environ.get("API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY") or os.environ.get("API_SECRET")
    return api_key, secret_key


if __name__ == "__main__":
    loaded = load_env()
    print("Loaded env:", loaded)
    print("API_KEY:", os.environ.get("ALPACA_API_KEY"))
    print("SECRET:", os.environ.get("ALPACA_SECRET_KEY")[:10] + "..." if os.environ.get("ALPACA_SECRET_KEY") else None)
