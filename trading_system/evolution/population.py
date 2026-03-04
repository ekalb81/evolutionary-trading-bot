#!/usr/bin/env python3
"""
Initial Population Generator for the Evolutionary Trading System.

Generates Generation 0 strategy genomes with three seeding methods:
- 40% Template Seeding (standard archetypes with randomized parameters)
- 40% Biased-Random Seeding (random AST rules with realistic constraints)
- 20% Curated Baselines (simple control strategies)

Outputs to: data/evolution/gen_000/population.json
"""

import json
import uuid
import random
import os
from typing import Any

# Configuration
POPULATION_SIZE = 200
OUTPUT_DIR = "data/evolution/gen_000"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "population.json")

# Seed for reproducibility during initial development (can be removed for true randomness)
random.seed(42)

# ============================================================================
# SCHEMA DEFINITIONS
# ============================================================================

# Supported indicator types with their required parameters
INDICATOR_TEMPLATES = {
    "SMA": {
        "params": {"period": (5, 200)},
        "value_type": "series"
    },
    "EMA": {
        "params": {"period": (5, 200)},
        "value_type": "series"
    },
    "RSI": {
        "params": {"period": (5, 30)},
        "value_type": "oscillator",
        "bounds": (0, 100)
    },
    "MACD": {
        "params": {
            "fast_period": (5, 20),
            "slow_period": (15, 50),
            "signal_period": (5, 15)
        },
        "value_type": "oscillator"
    },
    "ATR": {
        "params": {"period": (5, 30)},
        "value_type": "series"
    },
    "BB": {
        "params": {"period": (10, 30), "std_dev": (1.5, 3.0)},
        "value_type": "band"
    },
    "STOCH": {
        "params": {"k_period": (10, 20), "d_period": (3, 10)},
        "value_type": "oscillator"
    }
}

# Price sources available for comparisons
PRICE_SOURCES = ["close", "open", "high", "low", "volume"]

# Comparison operators
COMPARATORS = [">", "<", ">=", "<=", "==", "!=", "crosses_above", "crosses_below"]

# Logical operators for AST
LOGICAL_OPS = ["AND", "OR"]


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def generate_uuid() -> str:
    """Generate a unique identifier for a strategy genome."""
    return str(uuid.uuid4())


def random_int(min_val: int, max_val: int) -> int:
    """Generate a random integer in range [min_val, max_val]."""
    return random.randint(min_val, max_val)


def random_float(min_val: float, max_val: float) -> float:
    """Generate a random float in range [min_val, max_val]."""
    return random.uniform(min_val, max_val)


def random_choice(seq: list) -> Any:
    """Select a random element from a sequence."""
    return random.choice(seq)


# ============================================================================
# INDICATOR GENERATION
# ============================================================================

def generate_indicator(indicator_id: str, forced_type: str = None) -> dict:
    """
    Generate a single indicator definition.
    
    Args:
        indicator_id: Unique ID for this indicator (e.g., "ind_0")
        forced_type: If provided, force a specific indicator type
        
    Returns:
        Dictionary defining the indicator
    """
    if forced_type is None:
        indicator_type = random_choice(list(INDICATOR_TEMPLATES.keys()))
    else:
        indicator_type = forced_type
    
    template = INDICATOR_TEMPLATES[indicator_type]
    params = {}
    
    for param_name, (min_val, max_val) in template["params"].items():
        if isinstance(min_val, int):
            params[param_name] = random_int(min_val, max_val)
        else:
            params[param_name] = round(random_float(min_val, max_val), 2)
    
    return {
        "id": indicator_id,
        "type": indicator_type,
        "params": params,
        "value_type": template["value_type"]
    }


def generate_indicators(count: int) -> list:
    """
    Generate a list of indicators.
    
    Args:
        count: Number of indicators to generate
        
    Returns:
        List of indicator definitions
    """
    indicators = []
    # Force a mix of indicator types when generating multiple
    available_types = list(INDICATOR_TEMPLATES.keys())
    
    for i in range(count):
        # Distribute indicator types to ensure variety
        forced_type = available_types[i % len(available_types)] if count <= len(available_types) else None
        indicators.append(generate_indicator(f"ind_{i}", forced_type))
    
    return indicators


# ============================================================================
# AST GENERATION
# ============================================================================

class ASTGenerator:
    """Generates Abstract Syntax Trees for trading rules with repair constraints."""
    
    def __init__(self, indicators: list):
        """
        Initialize AST generator with a set of indicators.
        
        Args:
            indicators: List of indicator definitions available for rule generation
        """
        self.indicators = indicators
        self.indicator_ids = [ind["id"] for ind in indicators]
        self._rebuild_reference_pools()
    
    def _rebuild_reference_pools(self):
        """Rebuild the pools of valid references for rule generation."""
        # Valid left-side references: indicators + price sources
        self.left_refs = self.indicator_ids + PRICE_SOURCES
        
        # Valid right-side references: indicators + price sources + constants
        self.right_refs = self.indicator_ids + PRICE_SOURCES + ["constant"]
        
        # For crosses, we only allow indicator-to-indicator or price-to-indicator
        self.cross_valid_rights = self.indicator_ids + PRICE_SOURCES
    
    def _generate_constant(self) -> dict:
        """Generate a random constant value."""
        # RSI is most common, so bias constants toward 30, 70
        if random.random() < 0.5:
            return random_choice([30, 50, 70])
        return round(random_float(0, 100), 2)
    
    def _generate_condition(self) -> dict:
        """Generate a single condition node (leaf of AST)."""
        # Select left reference
        left = random_choice(self.left_refs)
        
        # Select comparator
        comparator = random_choice(COMPARATORS)
        
        # Determine right value based on comparator
        if comparator in ["crosses_above", "crosses_below"]:
            right = random_choice(self.cross_valid_rights)
        else:
            right = random_choice(self.right_refs)
        
        # If right is constant, generate the value
        if right == "constant":
            right_value = self._generate_constant()
            right = {"type": "constant", "value": right_value}
        
        return {
            "type": "condition",
            "left": left,
            "comparator": comparator,
            "right": right
        }
    
    def _generate_node(self, max_depth: int, current_depth: int = 0) -> dict:
        """
        Recursively generate an AST node.
        
        Args:
            max_depth: Maximum tree depth
            current_depth: Current recursion depth
            
        Returns:
            AST node dictionary
        """
        # Base case: reached max depth or random leaf
        if current_depth >= max_depth or (current_depth > 0 and random.random() < 0.4):
            return self._generate_condition()
        
        # Internal node: logical operator
        if current_depth < max_depth:
            operator = random_choice(LOGICAL_OPS)
            # Reduce depth for children to prevent extremely deep trees
            child_max_depth = max_depth - 1 if current_depth > 0 else max_depth
            
            return {
                "type": "logical",
                "operator": operator,
                "left": self._generate_node(child_max_depth, current_depth + 1),
                "right": self._generate_node(child_max_depth, current_depth + 1)
            }
        
        return self._generate_condition()
    
    def generate_rule(self, target_depth: int = None) -> dict:
        """
        Generate a complete rule AST.
        
        Args:
            target_depth: Target complexity (1-3). If None, random.
            
        Returns:
            Root node of the rule AST
        """
        if target_depth is None:
            target_depth = random.choices([1, 2, 3], weights=[0.5, 0.35, 0.15])[0]
        
        # Ensure minimum depth of 1
        target_depth = max(1, target_depth)
        
        return self._generate_node(target_depth, 0)


# ============================================================================
# SEEDING STRATEGIES
# ============================================================================

def generate_template_seeding(indicators: list) -> dict:
    """
    Generate a strategy from template archetypes (Trend Following, Mean Reversion, Breakout).
    
    Slightly randomizes parameters while maintaining valid strategy logic.
    """
    archetype = random_choice(["trend_following", "mean_reversion", "breakout"])
    
    if archetype == "trend_following":
        # Trend Following: Fast MA crosses above Slow MA
        ind_slow = generate_indicator("ind_0", "SMA")
        ind_fast = generate_indicator("ind_1", "SMA")
        
        # Ensure fast < slow period
        slow_period = random_int(20, 50)
        fast_period = random_int(5, slow_period - 1)
        
        ind_slow["params"]["period"] = slow_period
        ind_fast["params"]["period"] = fast_period
        
        indicators = [ind_slow, ind_fast]
        
        entry_rule = {
            "type": "logical",
            "operator": "AND",
            "left": {
                "type": "condition",
                "left": "ind_1",
                "comparator": "crosses_above",
                "right": "ind_0"
            },
            "right": {
                "type": "condition",
                "left": "ind_1",
                "comparator": ">",
                "right": "ind_0"
            }
        }
        
        exit_rule = {
            "type": "logical",
            "operator": "OR",
            "left": {
                "type": "condition",
                "left": "ind_1",
                "comparator": "crosses_below",
                "right": "ind_0"
            },
            "right": {
                "type": "condition",
                "left": "ind_1",
                "comparator": "<",
                "right": "ind_0"
            }
        }
        
        name = f"TF_SMA_{fast_period}_{slow_period}"
    
    elif archetype == "mean_reversion":
        # Mean Reversion: Price crosses below lower BB or RSI oversold
        ind_bb = generate_indicator("ind_0", "BB")
        ind_rsi = generate_indicator("ind_1", "RSI")
        
        bb_period = random_int(15, 25)
        bb_std = round(random_float(1.5, 2.5), 1)
        rsi_period = random_int(10, 20)
        
        ind_bb["params"]["period"] = bb_period
        ind_bb["params"]["std_dev"] = bb_std
        ind_rsi["params"]["period"] = rsi_period
        
        indicators = [ind_bb, ind_rsi]
        
        entry_rule = {
            "type": "logical",
            "operator": "OR",
            "left": {
                "type": "condition",
                "left": "close",
                "comparator": "<",
                "right": "ind_0"  # Price below lower BB (BB value is the lower band)
            },
            "right": {
                "type": "condition",
                "left": "ind_1",
                "comparator": "<",
                "right": {"type": "constant", "value": 35}
            }
        }
        
        exit_rule = {
            "type": "logical",
            "operator": "OR",
            "left": {
                "type": "condition",
                "left": "close",
                "comparator": ">",
                "right": "ind_0"  # Price above middle BB (using just ind_0 for simplicity)
            },
            "right": {
                "type": "condition",
                "left": "ind_1",
                "comparator": ">",
                "right": {"type": "constant", "value": 55}
            }
        }
        
        name = f"MR_BB_{bb_period}_RSI_{rsi_period}"
    
    else:  # breakout
        # Breakout: Price crosses above high of last N bars
        ind_atr = generate_indicator("ind_0", "ATR")
        ind_high = generate_indicator("ind_1", "SMA")  # Using SMA on high price conceptually
        
        atr_period = random_int(10, 20)
        lookback = random_int(10, 30)
        
        ind_atr["params"]["period"] = atr_period
        
        indicators = [ind_atr, ind_high]
        
        entry_rule = {
            "type": "condition",
            "left": "high",
            "comparator": ">",
            "right": {"type": "constant", "value": lookback * 100}  # Simplified
        }
        
        exit_rule = {
            "type": "condition",
            "left": "ind_0",
            "comparator": ">",
            "right": {"type": "constant", "value": 2.0}
        }
        
        name = f"BO_ATR_{atr_period}_LB_{lookback}"
    
    # Generate risk management
    risk_management = generate_risk_management()
    
    # Generate position sizing
    position_sizing = generate_position_sizing()
    
    return {
        "id": generate_uuid(),
        "name": name,
        "generation": 0,
        "seeding_type": "template",
        "archetype": archetype,
        "indicators": indicators,
        "entry_rule": entry_rule,
        "exit_rule": exit_rule,
        "risk_management": risk_management,
        "position_sizing": position_sizing
    }


def generate_biased_random_seeding() -> dict:
    """
    Generate a biased-random strategy.
    
    Uses AST generator with biased probabilities to ensure:
    - Realistic indicator counts (2-4)
    - Logical depth (1-3)
    - Valid reference repair
    """
    # Determine indicator count with bias toward 2-3
    indicator_count = random.choices([1, 2, 3, 4], weights=[0.1, 0.4, 0.35, 0.15])[0]
    
    # Generate indicators
    indicators = generate_indicators(indicator_count)
    
    # Create AST generator with these indicators
    ast_gen = ASTGenerator(indicators)
    
    # Generate entry rule with biased depth
    entry_depth = random.choices([1, 2, 3], weights=[0.5, 0.35, 0.15])[0]
    entry_rule = ast_gen.generate_rule(entry_depth)
    
    # Generate exit rule (often simpler than entry)
    exit_depth = random.choices([1, 2], weights=[0.6, 0.4])[0]
    exit_rule = ast_gen.generate_rule(exit_depth)
    
    # Generate risk management
    risk_management = generate_risk_management()
    
    # Generate position sizing
    position_sizing = generate_position_sizing()
    
    # Generate name based on first indicator type
    ind_types = "_".join([ind["type"] for ind in indicators[:2]])
    
    return {
        "id": generate_uuid(),
        "name": f"BR_{ind_types}_{random_int(1000, 9999)}",
        "generation": 0,
        "seeding_type": "biased_random",
        "archetype": None,
        "indicators": indicators,
        "entry_rule": entry_rule,
        "exit_rule": exit_rule,
        "risk_management": risk_management,
        "position_sizing": position_sizing
    }


def generate_curated_baseline(strategy_type: str = None) -> dict:
    """
    Generate a curated baseline strategy (control subject).
    
    Simple, well-understood strategies:
    - SMA Cross (Golden Cross / Death Cross)
    - RSI Oversold/Overbought
    - Buy and Hold (control)
    """
    if strategy_type is None:
        strategy_type = random_choice(["sma_cross", "rsi_oversold", "buy_and_hold"])
    
    if strategy_type == "sma_cross":
        # Simple SMA crossover
        fast_period = random_int(10, 20)
        slow_period = random_int(30, 60)
        
        indicators = [
            {"id": "ind_0", "type": "SMA", "params": {"period": fast_period}, "value_type": "series"},
            {"id": "ind_1", "type": "SMA", "params": {"period": slow_period}, "value_type": "series"}
        ]
        
        entry_rule = {
            "type": "condition",
            "left": "ind_0",
            "comparator": "crosses_above",
            "right": "ind_1"
        }
        
        exit_rule = {
            "type": "condition",
            "left": "ind_0",
            "comparator": "crosses_below",
            "right": "ind_1"
        }
        
        name = f"BASE_SMA_{fast_period}_{slow_period}"
    
    elif strategy_type == "rsi_oversold":
        # RSI oversold/overbought
        rsi_period = random_int(10, 14)
        
        indicators = [
            {"id": "ind_0", "type": "RSI", "params": {"period": rsi_period}, "value_type": "oscillator"}
        ]
        
        entry_rule = {
            "type": "condition",
            "left": "ind_0",
            "comparator": "<",
            "right": {"type": "constant", "value": 30}
        }
        
        exit_rule = {
            "type": "condition",
            "left": "ind_0",
            "comparator": ">",
            "right": {"type": "constant", "value": 70}
        }
        
        name = f"BASE_RSI_{rsi_period}"
    
    else:  # buy_and_hold
        # Simplified buy and hold (no entry rule, holds forever)
        indicators = []
        
        entry_rule = {
            "type": "condition",
            "left": "close",
            "comparator": ">",
            "right": {"type": "constant", "value": 0}
        }
        
        exit_rule = {
            "type": "condition",
            "left": "close",
            "comparator": "<",
            "right": {"type": "constant", "value": 0}
        }
        
        name = "BASE_BUY_HOLD"
    
    # Conservative risk management for baselines
    risk_management = {
        "stop_loss_pct": round(random_float(0.02, 0.05), 4),
        "take_profit_pct": round(random_float(0.05, 0.15), 4),
        "max_hold_bars": random_int(50, 100)
    }
    
    # Fixed position sizing for baselines
    position_sizing = {
        "method": "fixed",
        "fixed_pct": round(random_float(0.05, 0.10), 4)
    }
    
    return {
        "id": generate_uuid(),
        "name": name,
        "generation": 0,
        "seeding_type": "baseline",
        "archetype": strategy_type,
        "indicators": indicators,
        "entry_rule": entry_rule,
        "exit_rule": exit_rule,
        "risk_management": risk_management,
        "position_sizing": position_sizing
    }


def generate_risk_management() -> dict:
    """Generate risk management parameters."""
    return {
        "stop_loss_pct": round(random_float(0.02, 0.10), 4),
        "take_profit_pct": round(random_float(0.05, 0.25), 4),
        "max_hold_bars": random_int(20, 120)
    }


def generate_position_sizing() -> dict:
    """Generate position sizing configuration."""
    method = random_choice(["fixed", "kelly", "volatility_adjusted"])
    
    if method == "fixed":
        return {
            "method": "fixed",
            "fixed_pct": round(random_float(0.02, 0.15), 4)
        }
    elif method == "kelly":
        return {
            "method": "kelly",
            "fraction": round(random_float(0.2, 0.5), 2),
            "max_pct": round(random_float(0.10, 0.25), 4)
        }
    else:  # volatility_adjusted
        return {
            "method": "volatility_adjusted",
            "target_risk_pct": round(random_float(0.01, 0.03), 4),
            "atr_multiplier": round(random_float(1.5, 3.0), 1),
            "max_pct": round(random_float(0.10, 0.25), 4)
        }


# ============================================================================
# POPULATION GENERATION
# ============================================================================

def generate_initial_population(size: int = POPULATION_SIZE) -> list:
    """
    Generate the initial population (Generation 0).
    
    Distribution:
    - 40% Template Seeding
    - 40% Biased-Random Seeding
    - 20% Curated Baselines
    
    Args:
        size: Total population size
        
    Returns:
        List of strategy genome dictionaries
    """
    population = []
    
    # Calculate counts
    template_count = int(size * 0.40)
    biased_count = int(size * 0.40)
    baseline_count = size - template_count - biased_count
    
    # Generate Template strategies
    for i in range(template_count):
        strategy = generate_template_seeding([])
        strategy["seeding_type"] = "template"
        population.append(strategy)
    
    # Generate Biased-Random strategies
    for i in range(biased_count):
        strategy = generate_biased_random_seeding()
        strategy["seeding_type"] = "biased_random"
        population.append(strategy)
    
    # Generate Baseline strategies
    baseline_types = ["sma_cross", "rsi_oversold", "buy_and_hold"]
    for i in range(baseline_count):
        strategy_type = baseline_types[i % len(baseline_types)]
        strategy = generate_curated_baseline(strategy_type)
        strategy["seeding_type"] = "baseline"
        population.append(strategy)
    
    # Shuffle population to mix types
    random.shuffle(population)
    
    return population


def validate_genome(genome: dict) -> bool:
    """
    Validate a single genome against the schema.
    
    Checks:
    - All required fields present
    - Indicator IDs in rules reference existing indicators
    - AST structure is valid
    
    Args:
        genome: Strategy genome to validate
        
    Returns:
        True if valid, False otherwise
    """
    required_fields = ["id", "name", "generation", "seeding_type", 
                       "indicators", "entry_rule", "exit_rule", 
                       "risk_management", "position_sizing"]
    
    # Check required fields
    for field in required_fields:
        if field not in genome:
            print(f"Missing field: {field}")
            return False
    
    # Collect indicator IDs
    indicator_ids = set(ind["id"] for ind in genome["indicators"])
    
    # Validate AST references
    def check_references(node: dict) -> bool:
        if node["type"] == "condition":
            left = node["left"]
            right = node["right"]
            
            # Left must be indicator ID or price source
            if left not in indicator_ids and left not in PRICE_SOURCES:
                print(f"Invalid left reference: {left}")
                return False
            
            # Right can be indicator ID, price source, or constant
            if isinstance(right, dict):
                if right.get("type") == "constant":
                    pass  # Valid
                elif right in indicator_ids or right in PRICE_SOURCES:
                    pass  # Valid
                else:
                    print(f"Invalid right reference: {right}")
                    return False
            elif isinstance(right, (int, float)):
                pass  # Valid constant value
            elif right in indicator_ids or right in PRICE_SOURCES:
                pass  # Valid reference
            else:
                print(f"Invalid right value: {right}")
                return False
            
            return True
        
        elif node["type"] == "logical":
            return check_references(node["left"]) and check_references(node["right"])
        
        return False
    
    if not check_references(genome["entry_rule"]):
        print(f"Invalid entry_rule in {genome['name']}")
        return False
    
    if not check_references(genome["exit_rule"]):
        print(f"Invalid exit_rule in {genome['name']}")
        return False
    
    return True


def main():
    """Main entry point for population generation."""
    print(f"Generating initial population of {POPULATION_SIZE} strategies...")
    
    # Generate population
    population = generate_initial_population(POPULATION_SIZE)
    
    # Validate all genomes
    print("Validating population...")
    valid_count = 0
    for genome in population:
        if validate_genome(genome):
            valid_count += 1
    
    print(f"Valid genomes: {valid_count}/{POPULATION_SIZE}")
    
    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Write to file
    with open(OUTPUT_FILE, "w") as f:
        json.dump(population, f, indent=2)
    
    print(f"Population saved to: {OUTPUT_FILE}")
    
    # Print summary
    seeding_counts = {}
    for g in population:
        st = g["seeding_type"]
        seeding_counts[st] = seeding_counts.get(st, 0) + 1
    
    print("\nPopulation Distribution:")
    for st, count in seeding_counts.items():
        print(f"  {st}: {count}")
    
    # Show sample genomes
    print("\nSample Strategies:")
    for i in range(min(3, len(population))):
        g = population[i]
        print(f"  - {g['name']} ({g['seeding_type']}, {len(g['indicators'])} indicators)")


if __name__ == "__main__":
    main()
