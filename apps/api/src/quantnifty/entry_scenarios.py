from __future__ import annotations

from typing import Any

SCENARIO_SCHEMA = "entry-scenarios-v1"

# These are the only live paper-entry pathways currently supported by the Brain.
# Range/compression/liquidity states are explicitly non-entry states.
ENTRY_SCENARIOS: dict[str, dict[str, Any]] = {
    "EARLY_ACCUMULATION": {
        "strategy": "early_accumulation",
        "description": "Early directional accumulation confirmed before a larger move.",
        "confirmation": "EARLY_ACCUMULATION_CONFIRMATION",
    },
    "DIRECTIONAL": {
        "strategy": "directional",
        "description": "Confirmed directional trend or breakout/breakdown.",
        "confirmation": "DIRECTIONAL_CONFIRMATION",
    },
    "NEGATIVE_GAMMA_EXPANSION": {
        "strategy": "gamma_blast",
        "description": "Negative-gamma expansion with qualifying volatility and gamma evidence.",
        "confirmation": "GAMMA_BLAST_CONFIRMATION",
    },
    "GAMMA_TRANSITION": {
        "strategy": "transition",
        "description": "Price is transitioning through the gamma-flip region with directional confirmation.",
        "confirmation": "GAMMA_TRANSITION_CONFIRMATION",
    },
    "CAS_REENTRY": {
        "strategy": "cas_reentry",
        "description": "Late-session re-entry authorized only from an already-produced live CAS decision.",
        "confirmation": "CAS_REENTRY_CONFIRMATION",
    },
}

NON_ENTRY_SCENARIOS = {
    "LIQUIDITY_RISK": "Execution safety failure; do not enter.",
    "POSITIVE_GAMMA_RANGE": "Range regime; standby rather than directional entry.",
    "COMPRESSION": "Compression; wait for release/breakout confirmation.",
    "TRANSITION": "Insufficiently specific transition; standby until a supported entry scenario is confirmed.",
}


def classify_entry_scenario(regime: str | None, strategy: str | None, direction: str | None = None) -> str:
    r = str(regime or "").upper()
    s = str(strategy or "").lower()
    d = str(direction or "").upper()

    if s == "cas_reentry":
        return "CAS_REENTRY"
    if s == "early_accumulation" or r == "EARLY_ACCUMULATION":
        return "EARLY_ACCUMULATION"
    if s == "gamma_blast" or r == "NEGATIVE_GAMMA_EXPANSION":
        return "NEGATIVE_GAMMA_EXPANSION"
    if s == "transition" or r == "GAMMA_TRANSITION":
        return "GAMMA_TRANSITION"
    if s == "directional" or r in {"BREAKOUT_UP", "BREAKDOWN_DOWN", "TREND_UP", "TREND_DOWN"}:
        return "DIRECTIONAL"
    return "NO_ENTRY"


def scenario_contract(regime: str | None, strategy: str | None, direction: str | None = None) -> dict[str, Any]:
    scenario = classify_entry_scenario(regime, strategy, direction)
    if scenario in ENTRY_SCENARIOS:
        spec = ENTRY_SCENARIOS[scenario]
        return {
            "schema": SCENARIO_SCHEMA,
            "scenario": scenario,
            "strategy": spec["strategy"],
            "confirmation": spec["confirmation"],
            "description": spec["description"],
            "entry_capable": True,
            "direction": str(direction or "NEUTRAL").upper(),
        }
    return {
        "schema": SCENARIO_SCHEMA,
        "scenario": "NO_ENTRY",
        "strategy": str(strategy or "standby").lower(),
        "confirmation": None,
        "description": NON_ENTRY_SCENARIOS.get(str(regime or "").upper(), "No supported entry scenario is confirmed."),
        "entry_capable": False,
        "direction": str(direction or "NEUTRAL").upper(),
    }
