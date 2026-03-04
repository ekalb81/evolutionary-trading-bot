"""
Orchestrator V2 - LLM-powered trading bot coordinator.

Features:
1. LLM Decision Engine (replaces hardcoded rules)
2. News Filter with cheap LLM triage
3. Periodic Health Audit

Runs as background asyncio loop.
"""

import os
import sys
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

# Add to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from trading_system.ipc.channel import IPCChannel, CommandType, OrchestratorAlert
import alpaca_trade_api as tradeapi

# =============================================================================
# Configuration
# =============================================================================
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "PKW4ZBECKAWJ5PSLKUEYGNR4EM")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")  # Fallback
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# =============================================================================
# Logging
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# =============================================================================
# LLM Client
# =============================================================================
class LLMClient:
    """Lightweight OpenRouter client with cost controls"""
    
    def __init__(self, api_key: str = None, base_url: str = OPENROUTER_BASE_URL):
        self.api_key = api_key or OPENROUTER_API_KEY
        self.base_url = base_url
        self.default_model = "anthropic/claude-3-haiku"  # Fast & cheap ($0.25/1M)
        self.reasoning_model = "openai/gpt-4o-mini"  # For complex reasoning if needed
        
    async def chat(self, messages: List[Dict], model: str = None, 
                   max_tokens: int = 500, temperature: float = 0.3) -> str:
        """Send chat completion request"""
        import aiohttp
        
        model = model or self.default_model
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://openclaw.local",
            "X-Title": "TradingOrchestrator"
        }
        
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        error = await resp.text()
                        logger.error(f"LLM API error: {resp.status} - {error}")
                        return None
                    
                    result = await resp.json()
                    return result["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"LLM request failed: {e}")
            return None
    
    async def decide_action(self, position_data: Dict, market_context: Dict) -> Dict:
        """
        Use LLM to decide: TRAIL, HOLD, or CLOSE
        """
        prompt = f"""You are a trading bot coordinator. Analyze this position and decide the best action.

Position:
- Symbol: {position_data.get('symbol')}
- Entry Price: ${position_data.get('entry_price', 0):.2f}
- Current Price: ${position_data.get('current_price', 0):.2f}
- PnL: {position_data.get('pnl_pct', 0):.2%}
- Bars Held: {position_data.get('bars_held', 0)}
- Extended: {position_data.get('extended', False)}

Market Context:
- News Impact: {market_context.get('news_impact', 'None')}
- Market Sentiment: {market_context.get('sentiment', 'Neutral')}

Decision Options:
- TRAIL: Convert stop-loss to trailing stop (for winners >5%)
- HOLD: Keep position (for moderate gains, no concerns)
- CLOSE: Close position immediately (for losses or high risk)

Output ONLY a JSON object:
{{"decision": "TRAIL|HOLD|CLOSE", "reason": "one sentence reasoning", "trail_percent": 3.0 (if TRAIL)}}
"""
        
        result = await self.chat([
            {"role": "system", "content": "You are a precise trading assistant. Output only valid JSON."},
            {"role": "user", "content": prompt}
        ])
        
        if result:
            try:
                return json.loads(result)
            except:
                return {"decision": "HOLD", "reason": "LLM parse error, default hold"}
        return {"decision": "HOLD", "reason": "LLM unavailable"}
    
    async def should_act_on_news(self, headlines: List[str], symbols: List[str]) -> Dict:
        """
        Cheap triage: Given news headlines, should we adjust positions?
        Returns: {should_act: bool, affected_symbols: [], summary: ""}
        """
        if not headlines:
            return {"should_act": False, "affected_symbols": [], "summary": "No news"}
        
        headlines_text = "\n".join([f"- {h}" for h in headlines[:10]])
        
        prompt = f"""You are a market news filter. Determine if these headlines require action.

Symbols in portfolio: {', '.join(symbols)}

Headlines:
{headlines_text}

Output ONLY a JSON object:
{{"should_act": true/false, "affected_symbols": ["AAPL"], "summary": "brief reason"}}
"""
        
        result = await self.chat([
            {"role": "system", "content": "You are a concise news analyst. Output only valid JSON."},
            {"role": "user", "content": prompt}
        ], model="anthropic/claude-3-haiku")  # Cheapest model for triage
        
        if result:
            try:
                return json.loads(result)
            except:
                return {"should_act": False, "affected_symbols": [], "summary": "parse error"}
        return {"should_act": False, "affected_symbols": [], "summary": "LLM error"}
    
    async def health_check(self, status: Dict, recent_pnl: float) -> str:
        """
        LLM audits system health and returns summary
        """
        positions = status.get("positions", {})
        config = status.get("config", {})
        
        prompt = f"""You are a trading bot system auditor. Review this snapshot.

System Status:
- State: {status.get('state')}
- Strategy: {status.get('strategy')}
- Recent PnL: ${recent_pnl:.2f}

Open Positions ({len(positions)}):
{json.dumps(positions, indent=2)}

Config:
- Max Hold (soft/hard): {config.get('max_hold_soft')}/{config.get('max_hold_hard')}
- Stop Loss: {config.get('stop_loss_pct', 0):.1%}
- Take Profit: {config.get('take_profit_pct', 0):.1%}

Output ONLY a one-line status: "OK", "WARNING: <issue>", or "CRITICAL: <issue>"
"""
        
        result = await self.chat([
            {"role": "system", "content": "You are a system auditor. Be brief and practical."},
            {"role": "user", "content": prompt}
        ], model="anthropic/claude-3-haiku")
        
        return result or "OK (LLM unavailable)"

# =============================================================================
# News Fetcher
# =============================================================================
class NewsFetcher:
    """Fetch and filter market news from Alpaca"""
    
    def __init__(self):
        self.api = tradeapi.REST(ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL)
        self.last_check = None
        
    def get_relevant_news(self, symbols: List[str], hours_back: int = 4) -> List[Dict]:
        """Get news for symbols, filtered by recency"""
        try:
            news = self.api.get_news(symbols=symbols, limit=50)
            results = []
            cutoff = datetime.utcnow().timestamp() - (hours_back * 3600)
            
            for n in news:
                # Parse timestamp
                ts = n.started_at.timestamp() if hasattr(n.started_at, 'timestamp') else 0
                if ts < cutoff:
                    continue
                    
                results.append({
                    "headline": n.headline,
                    "summary": n.summary[:200] if n.summary else "",
                    "symbols": n.symbols,
                    "url": n.url,
                    "ts": str(n.started_at)
                })
            
            return results
        except Exception as e:
            logger.warning(f"News fetch failed: {e}")
            return []

# =============================================================================
# Health Monitor
# =============================================================================
class HealthMonitor:
    """Periodic system health checks"""
    
    def __init__(self, log_dir: str = "/data/workspace/logs"):
        self.log_dir = Path(log_dir)
        self.audit_log = self.log_dir / "audit.md"
        self.loop_count = 0
        
    async def maybe_audit(self, ipc: IPCChannel, llm: LLMClient) -> bool:
        """
        Run audit every N loops. Returns True if audit was run.
        """
        self.loop_count += 1
        
        # Audit every 20 loops (~10 minutes at 30s intervals)
        if self.loop_count % 20 != 0:
            return False
        
        logger.info("[Health] Running periodic audit...")
        
        status = ipc.get_status()
        if not status:
            return False
        
        # Get recent PnL from account
        try:
            account = tradeapi.REST(ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL).get_account()
            recent_pnl = float(account.portfolio_value) - 100000  # Rough PnL
        except:
            recent_pnl = 0
        
        # LLM audit
        summary = await llm.health_check(status, recent_pnl)
        
        # Log to audit file
        timestamp = datetime.utcnow().isoformat()
        entry = f"\n## {timestamp}\n{summary}\n"
        
        with open(self.audit_log, "a") as f:
            f.write(entry)
        
        logger.info(f"[Health] Audit: {summary}")
        
        # Alert if critical
        if "CRITICAL" in summary:
            logger.critical(f"[Health] CRITICAL ISSUE DETECTED: {summary}")
            
        return True

# =============================================================================
# Main Orchestrator
# =============================================================================
class OrchestratorV2:
    """
    Enhanced Orchestrator with LLM decision making
    """
    
    def __init__(self, ipc_dir: str = "/data/workspace/trading_system/ipc"):
        self.ipc = IPCChannel(ipc_dir)
        self.llm = LLMClient()
        self.news = NewsFetcher()
        self.health = HealthMonitor()
        self.last_checked_alert = None
        self.last_news_check = None
        
        # Track monitored symbols
        self.symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "NFLX", "AMD", "INTC", "JPM", "BAC", "WFC", "GS", "C", "UNH", "JNJ", "PFE", "MRK", "ABBV", "XOM", "CVX", "SHEL", "COP", "SPY", "QQQ", "IWM", "DIA"]
        
    async def check_for_alerts(self) -> Optional[OrchestratorAlert]:
        """Check for daemon alerts"""
        alerts_dir = self.ipc.alerts_dir
        alert_files = sorted(alerts_dir.glob("*.json"))
        
        if not alert_files:
            return None
        
        latest = alert_files[-1]
        
        if self.last_checked_alert and latest.name == self.last_checked_alert:
            return None
        
        try:
            with open(latest) as f:
                data = json.load(f)
            
            self.last_checked_alert = latest.name
            return OrchestratorAlert(**data)
        except Exception as e:
            logger.error(f"Alert read error: {e}")
            return None
    
    async def process_position_decision(self, alert: OrchestratorAlert):
        """Use LLM to decide action on position alert"""
        data = alert.data or {}
        
        # Get current market context
        news = self.news.get_relevant_news(self.symbols, hours_back=4)
        headlines = [n["headline"] for n in news]
        
        # Ask LLM if news is significant
        if headlines:
            news_verdict = await self.llm.should_act_on_news(headlines, self.symbols)
            news_impact = news_verdict.get("summary", "None")
        else:
            news_impact = "None"
        
        market_context = {
            "news_impact": news_impact,
            "sentiment": "Neutral"
        }
        
        # LLM decision
        decision = await self.llm.decide_action(data, market_context)
        
        # Execute
        decision_type = decision.get("decision", "HOLD")
        reason = decision.get("reason", "No reason")
        trail_pct = decision.get("trail_percent")
        
        if decision_type == "TRAIL":
            self.ipc.send_command(CommandType.REPLACE_SL_TRAIL, alert.symbol, 
                                 {"trail_percent": trail_pct})
        elif decision_type == "HOLD":
            self.ipc.send_command(CommandType.HOLD, alert.symbol)
        elif decision_type == "CLOSE":
            self.ipc.send_command(CommandType.CLOSE, alert.symbol)
        
        logger.info(f"[Orchestrator] {decision_type} {alert.symbol}: {reason}")
        
        # Log
        self._log_decision(alert.symbol, decision_type, reason)
    
    def _log_decision(self, symbol: str, decision: str, reason: str):
        """Log to JSON"""
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
    
    async def run_loop(self, interval_seconds: int = 30):
        """Main orchestrator loop"""
        logger.info("[OrchestratorV2] Starting LLM-powered orchestrator...")
        
        while True:
            try:
                # 1. Check for position alerts
                alert = await self.check_for_alerts()
                
                if alert:
                    logger.info(f"[OrchestratorV2] Alert: {alert.alert_type} for {alert.symbol}")
                    
                    if alert.alert_type == "EXTENSION_NEEDED":
                        await self.process_position_decision(alert)
                    elif alert.alert_type == "POSITION_CLOSED":
                        logger.info(f"Position closed: {alert.symbol}")
                    elif alert.alert_type == "ORDER_FILLED":
                        logger.info(f"Order filled: {alert.symbol}")
                
                # 2. Periodic health check
                await self.health.maybe_audit(self.ipc, self.llm)
                
                # 3. Update status
                status = self.ipc.get_status()
                if status:
                    positions = list(status.get("positions", {}).keys())
                    if positions:
                        logger.debug(f"[OrchestratorV2] Monitoring: {positions}")
                
                await asyncio.sleep(interval_seconds)
                
            except asyncio.CancelledError:
                logger.info("[OrchestratorV2] Stopping...")
                break
            except Exception as e:
                logger.error(f"[OrchestratorV2] Error: {e}")
                await asyncio.sleep(5)

# =============================================================================
# Entry Point
# =============================================================================
async def main():
    orch = OrchestratorV2()
    await orch.run_loop(interval_seconds=30)

if __name__ == "__main__":
    asyncio.run(main())
