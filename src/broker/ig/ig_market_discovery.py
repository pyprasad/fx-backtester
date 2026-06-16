import json
from pathlib import Path

from .ig_market_rules import extract_market_rules


def _markets(response: dict) -> list[dict]:
    return response if isinstance(response, list) else response.get("markets", [])


def discover_usdjpy(client, config, search_term: str | None = None) -> tuple[dict, list[str]]:
    if config.market_epic:
        return client.get_market(config.market_epic), []
    candidates = _markets(client.search_markets(search_term or config.market_search_term))
    scored = []
    for candidate in candidates:
        text = f"{candidate.get('instrumentName', '')} {candidate.get('epic', '')}".upper()
        score = (4 if "USD/JPY" in text or "USDJPY" in text else 0)
        score += 2 if candidate.get("marketStatus", "").upper() == "TRADEABLE" else 0
        score += 1 if candidate.get("expiry", "").upper() in {"-", "DFB", "CASH"} else 0
        score += 1 if candidate.get("instrumentType", "").upper() in {"CURRENCIES", "FOREX"} else 0
        scored.append((score, candidate))
    if not scored or max(scored, key=lambda item: item[0])[0] < 4:
        raise ValueError("No plausible USDJPY market found")
    scored.sort(key=lambda item: item[0], reverse=True)
    warnings = ["MULTIPLE_SIMILAR_MARKETS_REQUIRE_REVIEW"] if len(scored) > 1 and scored[0][0] == scored[1][0] else []
    return client.get_market(scored[0][1]["epic"]), warnings


def write_market_discovery_report(output: str | Path, metadata: dict, warnings: list[str]) -> Path:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    rules = extract_market_rules(metadata)
    result = {"selected_market": rules.to_dict(), "warnings": warnings}
    (output / "market_discovery_usdjpy.json").write_text(json.dumps(result, indent=2, default=str))
    path = output / "market_discovery_usdjpy.md"
    path.write_text(
        "# IG DEMO USDJPY Market Discovery\n\n"
        f"- EPIC: `{rules.epic}`\n- Name: {rules.name}\n- Status: {rules.status}\n"
        f"- Expiry: {rules.expiry}\n- Warnings: {', '.join(warnings) or 'none'}\n\n"
        "This report is read-only and does not authorize order placement.\n"
    )
    return path


def write_market_rules_report(output: str | Path, rules) -> Path:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    result = {**rules.to_dict(), "strategy_validation": rules.validation()}
    (output / "usdjpy_market_rules.json").write_text(json.dumps(result, indent=2, default=str))
    path = output / "usdjpy_market_rules.md"
    path.write_text(
        "# IG DEMO USDJPY Market Rules\n\n"
        f"- EPIC: `{rules.epic}`\n- Status: {rules.status}\n- Pip size: {rules.pip_size}\n"
        f"- Currency code: {rules.currency}\n"
        f"- Minimum deal size: {rules.min_deal_size}\n"
        f"- Minimum stop distance: {rules.min_stop_distance_pips}\n"
        f"- Strategy validation: `{rules.validation()}`\n\nNo order was sent.\n"
    )
    return path
