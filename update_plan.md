Evolution System Upgrades for v2:

1. Gename Expansion: Options Support
   - Add `execution_target` array to genomes:
     - Equities: {"type": "equity", "fractional": true}
     - Options: {"type": "option", "side": "call"|"put", "target_dte": int, "target_delta": float}
2. Breeder Updates
   - Needs to know how to mutate/crossover the `execution_target` block.
3. Evolve (Backtesting) Updates
   - Need to simulate Options returns. Options pricing backtesting is very hard without historical OPRA data.
   - For paper evolution, we can approximate options returns using the underlying's price change multiplied by the target delta, and decay the time value (theta).
   - Alternatively, we train the genome pure-equity, but let the `execution_target` dictate how the orchestrator takes the trade. (Much simpler).

Plan:
Let's modify `population.py` to inject the `execution_target` node.
Let's modify `breeder.py` to mutate `target_dte` and `target_delta`.
Let's modify the fitness function (`evolve.py`) so options returns apply leverage to the equity moves.
