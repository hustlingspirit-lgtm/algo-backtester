import streamlit as st
import pandas as pd
import zipfile
import plotly.express as px
from backtest_engine import run_strategy

# --- UI Configuration ---
st.set_page_config(page_title="V-ORB Strategy X-Ray", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    .reportview-container .main .block-container{ padding-top: 2rem; }
    .stMetric { background-color: #1E1E1E; padding: 15px; border-radius: 8px; border: 1px solid #333; }
</style>
""", unsafe_allow_html=True)

st.title("⚡ V-ORB Strategy: Advanced X-Ray Dashboard")

# --- Sidebar Inputs ---
st.sidebar.header("Capital & Risk")
initial_capital = st.sidebar.number_input("Initial Capital (₹)", min_value=1000, value=100000, step=1000)
risk_per_trade = st.sidebar.slider("Risk per Trade (%)", min_value=0.1, max_value=5.0, value=1.0, step=0.1)
slippage_tax = st.sidebar.number_input("Friction per Trade (₹)", min_value=0.0, value=15.0, step=1.0, help="Brokerage and slippage deducted per execution.")

st.sidebar.header("Strategy Rules")
trade_direction = st.sidebar.radio("Trade Direction", ["Both", "Long Only", "Short Only"])
allow_long = trade_direction in ["Both", "Long Only"]
allow_short = trade_direction in ["Both", "Short Only"]

atr_mult = st.sidebar.slider("ATR Multiplier (SL)", min_value=0.5, max_value=5.0, value=1.5, step=0.1)
rr_ratio = st.sidebar.slider("Target R:R Ratio", min_value=1.0, max_value=5.0, value=2.0, step=0.1)

uploaded_file = st.sidebar.file_uploader("Upload .zip with 5-min CSVs", type="zip")

chart_config = {'scrollZoom': False, 'displayModeBar': False, 'responsive': True}

if st.sidebar.button("Run Advanced Backtest", type="primary"):
    if uploaded_file is not None:
        data_dict = {}
        with zipfile.ZipFile(uploaded_file, 'r') as z:
            for filename in z.namelist():
                if filename.endswith('.csv'):
                    with z.open(filename) as f:
                        data_dict[filename.replace('.csv', '')] = pd.read_csv(f)
        
        if data_dict:
            try:
                trades_df = run_strategy(
                    data_dict, initial_capital, risk_per_trade, 
                    allow_long, allow_short, atr_mult, rr_ratio
                )
                
                if trades_df.empty:
                    st.warning("No trades generated with current parameters.")
                else:
                    trades_df['Entry Time'] = pd.to_datetime(trades_df['Entry Time'])
                    trades_df['Net PnL'] = trades_df['Gross PnL'] - slippage_tax
                    trades_df = trades_df.sort_values('Entry Time').reset_index(drop=True)
                    
                    trades_df['Cum PnL'] = trades_df['Net PnL'].cumsum()
                    trades_df['Equity'] = initial_capital + trades_df['Cum PnL']
                    trades_df['Peak Equity'] = trades_df['Equity'].cummax()
                    trades_df['Drawdown (%)'] = ((trades_df['Equity'] - trades_df['Peak Equity']) / trades_df['Peak Equity']) * 100
                    
                    trades_df['Win'] = trades_df['Net PnL'] > 0
                    trades_df['Streak'] = trades_df.groupby((trades_df['Win'] != trades_df['Win'].shift()).cumsum()).cumcount() + 1
                    max_win_streak = trades_df[trades_df['Win']]['Streak'].max() if not trades_df[trades_df['Win']].empty else 0
                    max_loss_streak = trades_df[~trades_df['Win']]['Streak'].max() if not trades_df[~trades_df['Win']].empty else 0
                    
                    net_profit = trades_df['Net PnL'].sum()
                    total_trades = len(trades_df)
                    win_rate = (trades_df['Win'].sum() / total_trades) * 100
                    gross_profit = trades_df[trades_df['Net PnL'] > 0]['Net PnL'].sum()
                    gross_loss = abs(trades_df[trades_df['Net PnL'] < 0]['Net PnL'].sum())
                    profit_factor = gross_profit / gross_loss if gross_loss != 0 else float('inf')
                    
                    avg_win = trades_df[trades_df['Net PnL'] > 0]['Net PnL'].mean() if gross_profit > 0 else 0
                    avg_loss = abs(trades_df[trades_df['Net PnL'] < 0]['Net PnL'].mean()) if gross_loss > 0 else 1
                    expectancy = (win_rate/100 * avg_win) - ((1 - win_rate/100) * avg_loss)
                    max_dd = trades_df['Drawdown (%)'].min()
                    
                    tab1, tab2, tab3 = st.tabs(["📊 Dashboard & KPIs", "🔬 Deep Analytics", "📋 Raw Trade Logs"])
                    
                    with tab1:
                        st.subheader("Core Performance")
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("Net Profit (₹)", f"₹{net_profit:,.2f}", help="Total bottom line after costs.")
                        col2.metric("Win Rate", f"{win_rate:.1f}%", help="Percentage of winning trades.")
                        col3.metric("Profit Factor", f"{profit_factor:.2f}", help="Gross Profit / Gross Loss (> 1.5 is ideal).")
                        col4.metric("Max Drawdown", f"{max_dd:.2f}%", help="Largest peak-to-trough drop.")
                        
                        col5, col6, col7, col8 = st.columns(4)
                        col5.metric("Expectancy (₹)", f"₹{expectancy:.2f}", help="Mathematical average payout per trade.")
                        col6.metric("Total Trades", total_trades, help="Total sample size.")
                        col7.metric("Max Win Streak", max_win_streak, help="Longest winning streak.")
                        col8.metric("Max Loss Streak", max_loss_streak, help="Longest losing streak.")
                        
                        st.subheader("Dynamic Equity Curve")
                        fig_equity = px.line(trades_df, x='Entry Time', y='Equity', title="Capital Growth Over Time")
                        fig_equity.update_traces(line_color='#00FFAA', line_width=2)
                        fig_equity.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', margin=dict(l=0, r=0, t=30, b=0))
                        st.plotly_chart(fig_equity, use_container_width=True, config=chart_config)

                    with tab2:
                        st.subheader("Market Context & Timing (IST)")
                        trades_df['Entry Hour'] = trades_df['Entry Time'].dt.strftime('%H:%M')
                        time_group = trades_df.groupby('Entry Hour')['Net PnL'].sum().reset_index()
                        fig_time = px.bar(time_group, x='Entry Hour', y='Net PnL', title="Profitability by Entry Time", color='Net PnL', color_continuous_scale='RdYlGn')
                        st.plotly_chart(fig_time, use_container_width=True, config=chart_config)
                        
                        col_chart1, col_chart2 = st.columns(2)
                        with col_chart1:
                            fig_dd = px.area(trades_df, x='Entry Time', y='Drawdown (%)', title="Underwater Chart")
                            fig_dd.update_traces(line_color='#FF4444', fillcolor='rgba(255, 68, 68, 0.2)')
                            st.plotly_chart(fig_dd, use_container_width=True, config=chart_config)
                        
                        with col_chart2:
                            trades_df['Day'] = trades_df['Entry Time'].dt.day_name()
                            day_order = ['Monday', 'Tuesday', 'Wednesday', 'Friday']
                            day_group = trades_df.groupby('Day')['Net PnL'].sum().reindex(day_order).reset_index()
                            fig_day = px.bar(day_group, x='Day', y='Net PnL', title="Performance by Day of Week", color='Net PnL', color_continuous_scale='RdYlGn')
                            st.plotly_chart(fig_day, use_container_width=True, config=chart_config)

                    with tab3:
                        st.subheader("Searchable Raw Trade Logs")
                        st.dataframe(trades_df[['Symbol', 'Direction', 'Entry Time', 'Entry Price', 'Exit Time', 'Exit Price', 'Reason', 'Gross PnL', 'Net PnL']], use_container_width=True, hide_index=True)
                        csv = trades_df.to_csv(index=False).encode('utf-8')
                        st.download_button("Download Full Trade Logs (CSV)", data=csv, file_name='v_orb_backtest_results.csv', mime='text/csv')
                        
            except Exception as e:
                st.error(f"Critical execution error: {e}")
    else:
        st.info("Please upload your historical 5-minute data .zip file in the sidebar to begin.")
