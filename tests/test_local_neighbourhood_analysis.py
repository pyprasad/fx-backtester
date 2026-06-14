from src.robustness.sensitivity_analysis import local_neighbourhood_analysis


def test_baseline_isolated():
    rows = [
        {"variant_name": name, "test_type": "local_neighbourhood", "pass_flag": passed}
        for name, passed in (("baseline_minus_small", False), ("baseline_original", True),
                             ("baseline_plus_small", False))
    ]
    _, summary = local_neighbourhood_analysis(rows)
    assert summary["baseline_isolated_flag"]
