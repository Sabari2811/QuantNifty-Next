"""Standalone QuantNifty post-market strategy research lab."""

from .runner import LabConfig, run_single_leg_tournament, run_strategy
from .strategies import all_strategies
from .multi_leg import MULTI_LEG_STRATEGIES, run_multi_leg_strategy, run_multi_leg_tournament
from .robustness import monte_carlo, slippage_stress, robustness_gate, add_monte_carlo

__all__ = ["LabConfig", "run_single_leg_tournament", "run_strategy", "all_strategies", "MULTI_LEG_STRATEGIES", "run_multi_leg_strategy", "run_multi_leg_tournament", "monte_carlo", "slippage_stress", "robustness_gate", "add_monte_carlo"]
