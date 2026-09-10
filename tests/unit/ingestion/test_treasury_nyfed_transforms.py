import pandas as pd

from cross_asset.ingestion.treasury_nyfed_transforms import (
    auction_stats,
    net_liquidity_components,
    rolling_percentile,
    rolling_zscore,
    tga_balances,
)


def test_tga_change_and_net_liquidity_are_causal_components():
    tga = tga_balances(
        [
            {
                "observation_date": "2026-09-02",
                "account_type": "Treasury General Account (TGA)",
                "close_today_bal": "100",
            },
            {
                "observation_date": "2026-09-03",
                "account_type": "Treasury General Account (TGA)",
                "close_today_bal": "110",
            },
        ]
    )
    onrrp = pd.Series({pd.Timestamp("2026-09-02"): 50.0, pd.Timestamp("2026-09-03"): 40.0})
    soma = pd.Series({pd.Timestamp("2026-09-02"): 20.0, pd.Timestamp("2026-09-03"): 21.0})
    components = net_liquidity_components(tga=tga, onrrp=onrrp, soma=soma)
    assert components["allocation_signal"] is False
    assert components["tga_change"] == 10.0
    assert components["onrrp_change"] == -10.0
    assert components["net_liquidity_research_component"] == 1.0


def test_auction_stats_and_dealer_zscore():
    stats = auction_stats(
        [
            {"bid_to_cover_ratio": "2.5", "high_yield": "4.20", "avg_med_yield": "4.10", "security_type": "Bill"},
            {"bid_to_cover_ratio": "1.5", "high_yield": "4.00", "avg_med_yield": "3.90", "security_type": "Note"},
        ]
    )
    assert stats["count"] == 2
    assert stats["mean_bid_to_cover"] == 2.0
    assert abs(stats["mean_tail"] - 0.1) < 1e-9
    series = pd.Series([1.0, 2.0, 3.0, 10.0])
    z = rolling_zscore(series, window=3, min_periods=3)
    p = rolling_percentile(series, window=3, min_periods=3)
    assert z.notna().sum() >= 1
    assert 0.0 <= float(p.dropna().iloc[-1]) <= 1.0
