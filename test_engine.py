import pytest
import pandas as pd
from backtest_engine import calculate_indicators, run_strategy

@pytest.fixture
def sample_data():
    data = {
        "Datetime": pd.to_datetime([
            "2023-01-02 09:15:00",
            "2023-01-02 09:20:00",
            "2023-01-02 10:15:00", 
            "2023-01-02 11:30:00", 
            "2023-01-02 15:15:00", 
        ]),
        "Open": [1000.0, 1002.0, 1010.0, 1020.0, 1015.0],
        "High": [1005.0, 1010.0, 1015.0, 1030.0, 1020.0],
        "Low": [995.0, 1000.0, 1005.0, 1015.0, 1010.0],
        "Close": [1002.0, 1008.0, 1014.0, 1025.0, 1012.0],
        "Volume": [5000, 6000, 7000, 8000, 5000]
    }
    return pd.DataFrame(data)

def test_calculate_indicators(sample_data):
    df = calculate_indicators(sample_data, ema1_period=10, ema2_period=20)
    assert "EMA1" in df.columns
    assert "EMA2" in df.columns
    assert "ATR" in df.columns
    assert len(df) == 5

def test_run_strategy(sample_data):
    data_dict = {"TEST_TICKER": sample_data}
    trades_df = run_strategy(
        data_dict=data_dict,
        initial_capital=100000,
        risk_per_trade=1.0,
        allow_long=True,
        allow_short=True,
        ema1=10,
        ema2=20,
        atr_mult=1.0,
        rr_ratio=2.0
    )
    assert isinstance(trades_df, pd.DataFrame)
