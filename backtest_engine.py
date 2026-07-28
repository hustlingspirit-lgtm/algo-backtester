import pandas as pd
from datetime import time

def calculate_indicators(df, ema1_period, ema2_period):
    df = df.copy()
    if 'Datetime' in df.columns:
        df['Datetime'] = pd.to_datetime(df['Datetime'], utc=True)
        df.set_index("Datetime", inplace=True)
    
    df['EMA1'] = df['Close'].ewm(span=ema1_period, adjust=False).mean()
    df['EMA2'] = df['Close'].ewm(span=ema2_period, adjust=False).mean()
    
    df['H-L'] = df['High'] - df['Low']
    df['H-PC'] = abs(df['High'] - df['Close'].shift(1))
    df['L-PC'] = abs(df['Low'] - df['Close'].shift(1))
    df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    df['ATR'] = df['TR'].rolling(14).mean()
    
    daily = df.resample('D').agg({'High':'max', 'Low':'min', 'Close':'last'}).dropna()
    daily['PDH'] = daily['High'].shift(1)
    daily['PDL'] = daily['Low'].shift(1)
    daily['P'] = (daily['High'].shift(1) + daily['Low'].shift(1) + daily['Close'].shift(1)) / 3
    daily['R1'] = (2 * daily['P']) - daily['Low'].shift(1)
    daily['S1'] = (2 * daily['P']) - daily['High'].shift(1)
    
    # Bypass Pandas merge completely to eliminate the ValueError
    daily.index = daily.index.strftime('%Y-%m-%d')
    df['date_str'] = df.index.strftime('%Y-%m-%d')
    
    df['PDH'] = df['date_str'].map(daily['PDH'])
    df['PDL'] = df['date_str'].map(daily['PDL'])
    df['P'] = df['date_str'].map(daily['P'])
    df['R1'] = df['date_str'].map(daily['R1'])
    df['S1'] = df['date_str'].map(daily['S1'])
    
    df.drop(columns=['date_str'], inplace=True)
    return df.reset_index()

def run_strategy(data_dict, initial_capital, risk_per_trade, allow_long, allow_short, ema1, ema2, atr_mult, rr_ratio):
    trades = []
    for symbol, df in data_dict.items():
        df = calculate_indicators(df, ema1, ema2)
        in_trade = False
        trade_dir = 0
        entry_price = 0
        sl = 0
        target = 0
        entry_time = None
        qty = 0
        
        for i in range(1, len(df)):
            row = df.iloc[i]
            current_time = row['Datetime'].time()
            
            if in_trade and current_time >= time(15, 15):
                exit_price = row['Close']
                pnl = (exit_price - entry_price) * qty if trade_dir == 1 else (entry_price - exit_price) * qty
                trades.append([symbol, "Long" if trade_dir==1 else "Short", entry_time, entry_price, row['Datetime'], exit_price, "Time Exit", pnl])
                in_trade = False
                continue
                
            if in_trade:
                if trade_dir == 1:
                    if row['Low'] <= sl:
                        trades.append([symbol, "Long", entry_time, entry_price, row['Datetime'], sl, "SL Hit", (sl - entry_price) * qty])
                        in_trade = False
                    elif row['High'] >= target:
                        trades.append([symbol, "Long", entry_time, entry_price, row['Datetime'], target, "Target Hit", (target - entry_price) * qty])
                        in_trade = False
                elif trade_dir == -1:
                    if row['High'] >= sl:
                        trades.append([symbol, "Short", entry_time, entry_price, row['Datetime'], sl, "SL Hit", (entry_price - sl) * qty])
                        in_trade = False
                    elif row['Low'] <= target:
                        trades.append([symbol, "Short", entry_time, entry_price, row['Datetime'], target, "Target Hit", (entry_price - target) * qty])
                        in_trade = False
                continue
                
            if time(10, 0) <= current_time <= time(13, 0):
                if allow_long and row['Close'] > row['PDH'] and row['Close'] > row['R1'] and row['Low'] <= row['EMA1'] and row['Close'] > row['Open'] and row['Close'] > row['EMA1']:
                    in_trade = True
                    trade_dir = 1
                    entry_price = row['Close']
                    entry_time = row['Datetime']
                    sl = entry_price - (row['ATR'] * atr_mult)
                    risk_amount = initial_capital * (risk_per_trade / 100)
                    qty = risk_amount / (entry_price - sl) if (entry_price - sl) > 0 else 0
                    target = entry_price + ((entry_price - sl) * rr_ratio)
                    
                elif allow_short and row['Close'] < row['PDL'] and row['Close'] < row['S1'] and row['High'] >= row['EMA1'] and row['Close'] < row['Open'] and row['Close'] < row['EMA1']:
                    in_trade = True
                    trade_dir = -1
                    entry_price = row['Close']
                    entry_time = row['Datetime']
                    sl = entry_price + (row['ATR'] * atr_mult)
                    risk_amount = initial_capital * (risk_per_trade / 100)
                    qty = risk_amount / (sl - entry_price) if (sl - entry_price) > 0 else 0
                    target = entry_price - ((sl - entry_price) * rr_ratio)
                    
    trades_df = pd.DataFrame(trades, columns=["Symbol", "Direction", "Entry Time", "Entry Price", "Exit Time", "Exit Price", "Reason", "Gross PnL"])
    if not trades_df.empty:
        trades_df['Net PnL'] = trades_df['Gross PnL'] - (trades_df['Entry Price'] * 0.00025) - (trades_df['Exit Price'] * 0.00025)
    return trades_df
