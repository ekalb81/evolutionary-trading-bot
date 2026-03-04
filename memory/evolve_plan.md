Evolution loop:
1. Load genome data from data/evolution/gen_000/population.json.
2. We need a way to parse AST and indicators into a computable form.
    - We will need indicator functions (we can just use pandas/ta, but since it's a simple backtest let's implement the required ones: SMA, EMA, RSI, MACD, ATR, BB, STOCH). We can use `ta` library or write basic pandas implementations.
    - We will need an AST evaluator that takes a row of `(open, high, low, close, volume, indicators...)` and returns True/False for entry/exit.
3. For each strategy:
    For each symbol in universe:
        Fetch bars from DataProvider.
        Compute indicators.
        Evaluate entry/exit rules row by row (or vectorized if possible, but row by row or shifted vectors is fine).
        Simulate trades (Entry: True -> Position Open. Exit: True or Hit Stop Loss/Take Profit or Max Hold Bars -> Position Close).
        Record trades: entry_time, exit_time, entry_price, exit_price, pnl_pct
    Aggregate all trades.
    Create a daily equity curve (start with 1.0, apply daily returns of active positions or simple trade-based compounding).
    Since trade freq penalty expects ~50 trades *total* (or per year? "frequency: ~50 trades for full score" - let's assume total trades since 2 years on 20 stocks = 40 stock-years. 50 trades total over 20 stocks is very low, probably it's total trades in the backtest).
    Calculate metrics (Sortino, Calmar, ProfitFactor).
4. Save results to data/evolution/gen_000/results.json
