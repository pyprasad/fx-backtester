from src.bakeoff.candidate_config import EXPECTED_CANDIDATES, load_bakeoff_config


def test_load_bakeoff_config():
    config = load_bakeoff_config("config/final_guardrail_bakeoff.usdjpy.yaml")
    assert {candidate["name"] for candidate in config["candidates"]} == EXPECTED_CANDIDATES
