def sequence_stress_rows(trades, sampler, simulator) -> list[dict]:
    scenarios = {
        "historical_order": trades,
        "worst_trades_first": sampler.worst_trades_first(trades),
        "best_trades_first": sampler.best_trades_first(trades),
        "loss_clusters": sampler.alternating_loss_clusters(trades),
    }
    rows = []
    for name, sequence in scenarios.items():
        result = simulator.simulate(sequence)
        rows.append({
            "scenario_name": name, "ending_balance": result["ending_balance"],
            "total_return_percent": result["total_return_percent"],
            "max_drawdown_percent": result["max_drawdown_percent"],
            "max_consecutive_losses": result["consecutive_losses_max"],
            "worst_equity_point": result["min_equity"],
            "verdict": "PASS" if result["total_return_percent"] > 0 and result["max_drawdown_percent"] <= 15 else "FAIL",
        })
    return rows
