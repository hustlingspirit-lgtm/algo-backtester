import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import zipfile
from backtest_engine import run_strategy

if 'runs' not in st.session_state:
    st.session_state.runs = {}

def highlight_pnl(val):
    try:
        color = '#d4edda' if val > 0 else '#f8d7da'
        text_color = '#155724' if val > 0 else '#721c24'
        return f'background-color: {color}; color: {text_color}'
    except:
        return ''

st.set_page_config(page_title="Quantitative Backtester", layout="wide")
st.title("📈 Indian Equities Backtesting Dashboard")

st.sidebar.header("Strategy Parameters")
capital = st.sidebar.number_input("Initial Capital (₹)", value=100000, step=10000)
risk_pct = st.sidebar.slider("Risk per Trade (%)", 0.1, 5.0, 1.0, 0.1)
trade_dir = st.sidebar.radio("Trade Direction", ["Both", "Long Only", "Short Only"])
allow_long = trade_dir in ["Both", "Long Only"]
allow_short = trade_dir in ["Both", "Short Only"]

st.sidebar.header("Indicator Settings")
ema1 = st.sidebar.slider("EMA 1 Period", 5, 50, 10)
ema2 = st.sidebar.slider("EMA 2 Period", 10, 100, 20)
atr_mult = st.sidebar.slider("ATR Multiplier (SL)", 0.5, 3.0, 1.0, 0.1)
rr_ratio = st.sidebar.slider("Target R:R Ratio", 1.0, 5.0, 1.0, 0.1)

uploaded_file = st.file_uploader("Upload .zip with 5-min CSVs", type="zip")
data_dict = {}

if uploaded_file is not None:
    with zipfile.ZipFile(uploaded_file) as z:
        for filename in z.namelist():
            if filename.endswith(".csv"):
                with z.open(filename) as f:
                    data_dict[filename.replace('.csv', '')] = pd.read_csv(f)
else:
    st.info("Upload a ZIP file containing your CSVs to proceed.")

if data_dict and st.button("Run Backtest"):
    with st.spinner("Executing Strategy Engine..."):
        trades_df = run_strategy(data_dict, capital, risk_pct, allow_long, allow_short, ema1, ema2, atr_mult, rr_ratio)
        
        if not trades_df.empty:
            trades_df['Cumulative PnL'] = trades_df['Net PnL'].cumsum()
            trades_df['Equity'] = capital + trades_df['Cumulative PnL']
            trades_df['Drawdown'] = (trades_df['Equity'].cummax() - trades_df['Equity']) / trades_df['Equity'].cummax() * 100
            
            net_profit = trades_df['Net PnL'].sum()
            win_rate = (len(trades_df[trades_df['Net PnL'] > 0]) / len(trades_df)) * 100
            profit_factor = trades_df[trades_df['Net PnL'] > 0]['Net PnL'].sum() / abs(trades_df[trades_df['Net PnL'] < 0]['Net PnL'].sum()) if len(trades_df[trades_df['Net PnL'] < 0]) > 0 else np.inf
            max_dd = trades_df['Drawdown'].max()
            
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("Net Profit (₹)", f"₹{net_profit:,.2f}")
            col2.metric("Win Rate", f"{win_rate:.2f}%")
            col3.metric("Profit Factor", f"{profit_factor:.2f}")
            col4.metric("Max Drawdown", f"{max_dd:.2f}%")
            col5.metric("Total Trades", len(trades_df))
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(y=trades_df['Equity'], mode='lines', name='Equity Curve'))
            fig.update_layout(title="Cumulative Equity Curve (₹)", template="plotly_dark")
            st.plotly_chart(fig, use_container_width=True)
            
            st.subheader("Detailed Trade Log")
            styled_df = trades_df.style.map(highlight_pnl, subset=['Net PnL', 'Gross PnL']).format({'Entry Price': '{:.2f}', 'Exit Price': '{:.2f}', 'Net PnL': '₹{:.2f}', 'Gross PnL': '₹{:.2f}'})
            st.dataframe(styled_df, use_container_width=True)
        else:
            st.warning("No trades executed with the current parameters.")
          
