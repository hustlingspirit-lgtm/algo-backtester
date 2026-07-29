import streamlit as st
import pandas as pd
import zipfile
from backtest_engine import run_strategy

st.set_page_config(page_title="Indian Equities Backtesting", layout="wide")
st.title("📈 Indian Equities Backtesting Dashboard")

st.sidebar.header("Strategy Parameters")
initial_capital = st.sidebar.number_input("Initial Capital (₹)", min_value=1000, value=100000, step=1000)
risk_per_trade = st.sidebar.slider("Risk per Trade (%)", min_value=0.1, max_value=5.0, value=1.0, step=0.1)

trade_direction = st.sidebar.radio("Trade Direction", ["Both", "Long Only", "Short Only"])
allow_long = trade_direction in ["Both", "Long Only"]
allow_short = trade_direction in ["Both", "Short Only"]

st.sidebar.header("Indicator Settings")
atr_mult = st.sidebar.slider("ATR Multiplier (SL)", min_value=0.5, max_value=5.0, value=1.5, step=0.1)
rr_ratio = st.sidebar.slider("Target R:R Ratio", min_value=1.0, max_value=5.0, value=2.0, step=0.1)

uploaded_file = st.file_uploader("Upload .zip with 5-min CSVs", type="zip")

if st.button("Run Backtest"):
    if uploaded_file is not None:
        data_dict = {}
        with zipfile.ZipFile(uploaded_file, 'r') as z:
            for filename in z.namelist():
                if filename.endswith('.csv'):
                    with z.open(filename) as f:
                        df = pd.read_csv(f)
                        data_dict[filename.replace('.csv', '')] = df
        
        if data_dict:
            try:
                trades_df = run_strategy(
                    data_dict, initial_capital, risk_per_trade, 
                    allow_long, allow_short, 10, 20, atr_mult, rr_ratio
                )
                
                if trades_df.empty:
                    st.warning("No trades generated with current parameters.")
                else:
                    net_profit = trades_df['Net PnL'].sum()
                    win_rate = (len(trades_df[trades_df['Net PnL'] > 0]) / len(trades_df)) * 100
                    gross_profit = trades_df[trades_df['Net PnL'] > 0]['Net PnL'].sum()
                    gross_loss = abs(trades_df[trades_df['Net PnL'] < 0]['Net PnL'].sum())
                    profit_factor = gross_profit / gross_loss if gross_loss != 0 else float('inf')
                    total_trades = len(trades_df)
                    
                    cum_pnl = trades_df['Net PnL'].cumsum()
                    max_drawdown = ((cum_pnl.cummax() - cum_pnl) / (initial_capital + cum_pnl.cummax()) * 100).max()
                    
                    col1, col2, col3, col4, col5 = st.columns(5)
                    col1.metric("Net Profit (₹)", f"₹{net_profit:.2f}")
                    col2.metric("Win Rate", f"{win_rate:.2f}%")
                    col3.metric("Profit Factor", f"{profit_factor:.2f}")
                    col4.metric("Max Drawdown", f"{max_drawdown:.2f}%")
                    col5.metric("Total Trades", total_trades)
                    
                    st.dataframe(trades_df)
            except Exception as e:
                st.error(f"Error during backtest: {e}")
    else:
        st.error("Please upload a .zip file first.")
