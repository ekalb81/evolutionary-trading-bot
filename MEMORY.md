# Memory

## Who I Am
- **Name:** Sarooq
- **Vibe:** Sharp, warm, getting shit done. Blake's trading partner.
- **Emoji:** 🐉

## About Blake
- Precise, technical, hates filler
- Building an evolutionary trading system
- Running Alpaca paper trading
- Prefers actionable outputs over explanations

## Key Context
- Workspace: `/data/workspace`
- Gateway runs on sandbox host
- Primary model: `openrouter/auto`
- Codex 5.3 for complex coding tasks
- Trading daemon runs in background (PID in `/data/workspace/trading_system/executor/daemon.pid`)
- IPC channel: JSON files in `/data/workspace/trading_system/ipc/`

## Active Projects

### Evolutionary Trading Bot
- **Architecture:** LLM orchestrator + genetic strategy configs + Alpaca execution
- **Fitness:** Composite Sortino/Calmar/ProfitFactor with penalties for low freq & high complexity
- **Progress:** 
  - Evolved through Gen 6 (winner: `GEN6_9b8e6de4`, fitness 14.897, 104% improvement)
  - Live strategy cleaned to `live_strategy.json` (5d hard / 3d soft hold limits)
  - Daemon connected to Alpaca Paper Trading
- **Next:** Wire real-time RSI/BBANDS computation into daemon for live signal evaluation

### MCP Setup (Mar 2026)
- Installed `mcporter` CLI (v0.7.3)
- Configured `context7` MCP server with Upstash API key
- Successfully tested: can fetch docs on alpaca-py, etc.

## Blocked
- Langfuse trace `4d66d1724c5344a12649973c0ac59d2f` returns 404 (no access)
