import pytest

from quant.peer_comps import compute_peer_relative_position


def test_compute_peer_relative_position_matches_known_calculation():
    result = compute_peer_relative_position(target_value=30, peer_values=[10, 20, 25])
    # median of [10,20,25] = 20; delta = (30-20)/20*100 = 50%
    # target(30) >= all 3 peers -> percentile 100
    assert result["peer_median"] == 20
    assert result["delta_vs_median_pct"] == 50.0
    assert result["percentile_vs_peers"] == 100.0


def test_compute_peer_relative_position_below_all_peers():
    result = compute_peer_relative_position(target_value=5, peer_values=[10, 20, 25])
    assert result["percentile_vs_peers"] == 0.0
    assert result["delta_vs_median_pct"] == -75.0


def test_compute_peer_relative_position_none_when_missing_data():
    assert compute_peer_relative_position(None, [10, 20]) == {
        "peer_median": None, "delta_vs_median_pct": None, "percentile_vs_peers": None,
    }
    assert compute_peer_relative_position(10, []) == {
        "peer_median": None, "delta_vs_median_pct": None, "percentile_vs_peers": None,
    }


def test_compute_peer_relative_position_ignores_none_peer_values():
    result = compute_peer_relative_position(target_value=15, peer_values=[10, None, 20])
    assert result["peer_median"] == 15
