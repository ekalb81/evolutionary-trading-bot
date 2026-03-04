#!/bin/bash
cd /data/workspace
export $(cat .trader.env | xargs)
source venv/bin/activate
mkdir -p logs

echo "Starting Alpaca Trading Daemon..."
nohup python -m trading_system.executor.daemon --live > logs/daemon.log 2>&1 &
echo $! > trading_system/executor/daemon.pid

echo "Starting Orchestrator V2 (LLM-powered)..."
nohup python -m trading_system.ipc.orchestrator_v2 > logs/orchestrator.log 2>&1 &
echo $! > trading_system/ipc/orchestrator.pid

echo ""
echo "System is LIVE with LLM Orchestrator!"
tail -f logs/orchestrator.log
