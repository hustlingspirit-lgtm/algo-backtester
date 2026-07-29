import pandas as pd
from datetime import time

def calculate_indicators(df):
    df = df.copy()
    if 'Datetime' in df.columns:
        df['Datetime'] = pd.to_datetime(df['Datetime'], utc=True)
        df.set_index("Datetime", inplace=True)
        
    df['Time'] = df.index.time
    df['Date_Str'] = df.index.strftime('%Y-%m-%d')
    
    # ATR Calculation
    df['H-L'] = df['High'] - df['Low']
    df['H-PC'] = abs(df['High'] - df['Close'].shift(1))
    df['L-PC'] = abs(df['Low'] - df['Close'].shift(1))
    df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    df['ATR'] = df['TR'].rolling(14).mean()
    
    # Volume SMA Filter
    if 'Volume' in df.columns:
        df['Vol_SMA'] = df['Volume'].rolling(20).mean()
    else:
        df['Vol_SMA'] = 0
        df['Volume'] = 0
        
    # VWAP Calculation (Daily Reset)
    df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
    df['TP_V'] = df['Typical_Price'] * df['Volume']
    df['Cum_Vol'] = df.groupby('Date_Str')['Volume'].cumsum()
    df['Cum_TP_V'] = df.groupby('Date_Str')['TP_V'].cumsum()
    df['VWAP'] = df['Cum_TP_V'] / df['Cum_Vol']
    
    # Opening Range High/Low (09:15 to 09:55)
    or_data = df[(df['Time'] >= time(9, 15)) & (df['Time'] < time(10, 0))]
    or_high_dict = or_data.groupby('Date_Str')['High'].max().to_dict()
    or_low_dict = or_data.groupby('Date_Str')['Low'].min().to_dict()
    
    df['OR_High'] = df['Date_Str'].apply(lambda x: or_high_dict.get(x, None))
    df['OR_Low'] = df['Date_Str'].apply(lambda x: or_low_dict.get(x, None))
    
    return df.reset_index()

def run_strategy(data_dict, initial_capital, risk_per_trade, allow_long, allow_short, ema1, ema2, atr_mult, rr_ratio):
    # Note: ema1 and ema2 are passed from app.py but ignored for this strategy
    vol_mult = 1.5 
    trades = []
    
    for symbol, df in data_dict.items():
        if df.empty or 'Volume' not in df.columns:
            continue
            
        df = calculate_indicators(df)
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
            
            # Auto Square-Off at 15:15
            if in_trade and current_time >= time(15, 15):
                exit_price = row['Close']
                pnl = (exit_price - entry_price) * qty if trade_dir == 1 else (entry_price - exit_price) * qty
                trades.append([symbol, "Long" if trade_dir==1 else "Short", entry_time, entry_price, row['Datetime'], exit_price, "Time Exit", pnl])
                in_trade = False
                continue
                
            # Trade Management
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
                
            # Entry Logic (10:00 to 14:30)
            if time(10, 0) <= current_time <= time(14, 30):
                if pd.isna(row['OR_High']) or pd.isna(row['VWAP']) or pd.isna(row['Vol_SMA']):
                    continue
                    
                vol_condition = row['Volume'] > (row['Vol_SMA'] * vol_mult)
                
                # Long Condition
                if allow_long and row['Close'] > row['OR_High'] and row['Close'] > row['VWAP'] and vol_condition:
                    in_trade = True
                    trade_dir = 1
                    entry_price = row['Close']
                    entry_time = row['Datetime']
                    sl = entry_price - (row['ATR'] * atr_mult)
                    risk_amount = initial_capital * (risk_per_trade / 100)
                    qty = risk_amount / (entry_price - sl) if (entry_price - sl) > 0 else 0
                    target = entry_price + ((entry_price - sl) * rr_ratio)
                    
                # Short Condition
                elif allow_short and row['Close'] < row['OR_Low'] and row['Close'] < row['VWAP'] and vol_condition:
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
                                       
