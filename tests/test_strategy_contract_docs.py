from pathlib import Path


DOCS = Path("docs/strategies")
REQUIRED = {
    "usdjpy_fx_swing_trend_reclaim_v1_final_strategy.md",
    "usdjpy_final_research_baseline_summary.md",
    "usdjpy_strategy_pipeline_contract.md",
    "usdjpy_signal_rules.md",
    "usdjpy_execution_rules.md",
    "usdjpy_risk_and_guardrails.md",
    "usdjpy_funding_awareness.md",
    "usdjpy_validation_history.md",
    "usdjpy_demo_readiness_prerequisites.md",
}


def test_required_strategy_contract_docs_exist_and_state_research_boundary():
    assert REQUIRED.issubset({path.name for path in DOCS.glob("*.md")})
    combined = "\n".join((DOCS / name).read_text() for name in REQUIRED)
    assert "min_risk_3pips" in combined
    assert "ig_min_stop_only" in combined
    assert "recommended_research_guardrail" in combined
    assert "not production-ready" in combined


def test_pipeline_contract_contains_required_contract_sections():
    text = (DOCS / "usdjpy_strategy_pipeline_contract.md").read_text()
    for required in (
        "Tick Input", "Candle Input", "Signal Output", "Trade Output",
        "Guardrail Decision Output", "funding_cutoff_proximity",
    ):
        assert required in text
