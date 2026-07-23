from mobile_pilot.evaluation.grid_development import freeze_unique_grid


def test_freeze_unique_grid_selects_one_winner_with_predeclared_tiebreaker():
    summary = [
        {"variant": "grid_10x20", "correct": 20, "invalid_outputs": 0, "grid_density": 200},
        {"variant": "grid_8x16", "correct": 22, "invalid_outputs": 0, "grid_density": 128},
        {"variant": "grid_10x10", "correct": 22, "invalid_outputs": 0, "grid_density": 100},
    ]

    frozen = freeze_unique_grid(summary)

    assert frozen["selected_variant"] == "grid_10x10"
    assert frozen["public_test_results_used"] is False
    assert len(frozen["freeze_sha256"]) == 64
