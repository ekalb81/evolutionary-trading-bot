#!/bin/bash
# Usage: ./run_daemon.sh [env_file]
# Default: uses .trader.env (which symlinks to .env.paper100)
#
# Examples:
#   ./run_daemon.sh              # Use default ($100 paper)
#   ./run_daemon.sh .env.paper100k # Use $100k paper
#   ./run_daemon.sh .env.paper100  # Explicit $100 paper

cd /data/workspace
ENV_FILE=${1:-.trader.env}

# Load env vars
export TRADING_ENV_FILE=$ENV_FILE
set -a
source $ENV_FILE
set +a

# Activate venv
source venv/bin/activate

# Optional: override trading universe
export TRADING_UNIVERSE="${TRADING_UNIVERSE:-AMD,INTC,BAC,PFE,C,WFC,X}"

# Run daemon (paper mode by default, --live for real trading)
exec python -m trading_system.executor.daemon
