from datetime import datetime, timezone
from types import SimpleNamespace

import yaml

from src.broker.ig.config import IGDemoConfig
from src.broker.ig.ig_demo_readiness import evaluate_demo_readiness
from src.broker.ig.models import InternalTick


def _config(credentials=True):
    value = "x" if credentials else ""
    return IGDemoConfig(
        "DEMO", value, value, value, "ABC123", "DEMO", "https://demo", True, "PRICE",
        "USD/JPY", "USDJPY", False, True, __import__("pathlib").Path("ticks"),
        __import__("pathlib").Path("audit"), "INFO",
    )


def _result(credentials=True, delayed=False):
    strategy = yaml.safe_load(open("config/strategies/usdjpy_fx_swing_trend_reclaim_v1_final.yaml"))
    session = SimpleNamespace(account_id="ABC123", lightstreamer_endpoint="https://stream")
    rules = SimpleNamespace(
        status="TRADEABLE", min_stop_distance_pips=2, pip_size=.01,
        streaming_prices_available=True,
    )
    tick = InternalTick(
        datetime.now(timezone.utc), 150, 150.01, 150.005, 1, "test", "USDJPY", delayed,
        raw={"normalization_price_scale_divisor": 1.0},
    )
    order = SimpleNamespace(validation_status="READY_FOR_DEMO_DRY_RUN", dry_run_only=True)
    return evaluate_demo_readiness(
        config=_config(credentials), session=session, accounts={"accounts": [1]},
        market_rules=rules, first_tick=tick, dry_run_order=order, strategy=strategy,
    )


def test_readiness_states_never_live():
    assert _result()["status"] == "READY_FOR_DEMO_DRY_RUN"
    assert _result(credentials=False)["status"] == "NOT_READY"
    assert _result(delayed=True)["status"] == "NOT_READY"
    assert _result()["ready_for_live"] is False
