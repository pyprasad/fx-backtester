from src.broker_guardrails.guardrail_report import write_guardrail_report


def test_guardrail_report(tmp_path):
    path = write_guardrail_report(tmp_path, [{"variant_name": "x", "score": 90, "verdict": "PASS"}], {})
    content = path.read_text()
    assert "Executive Summary" in content
    assert "Funding Exposure" in content
    assert "Baseline vs Guardrail Variants" in content
