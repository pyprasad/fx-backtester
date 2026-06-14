from pathlib import Path

import yaml


EXPECTED_CANDIDATES = {
    "ig_min_stop_only",
    "min_risk_3pips",
    "recommended_research_guardrail",
}


def load_bakeoff_config(path: str | Path) -> dict:
    config = yaml.safe_load(Path(path).read_text())
    names = {candidate["name"] for candidate in config["candidates"]}
    if names != EXPECTED_CANDIDATES:
        raise ValueError(f"FX-2H requires exactly these candidates: {sorted(EXPECTED_CANDIDATES)}")
    return config
