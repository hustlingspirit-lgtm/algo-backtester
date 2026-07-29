import pandas as pd
import numpy as np

def run_strategy(data_dict, initial_capital, risk_per_trade, allow_long, allow_short, ema_period, vol_period, atr_mult, rr_ratio):
    all_trades = []
    
    for symbol, df in data_dict.items():
        # Safely parse Date and Time
        df.columns = df.columns.str.strip().str.lower()
        
        if 'datetime' not in df.columns:
            if 'date' in df.columns and 'time' in df.columns:
                df['datetime'] = pd.to_datetime(df['date'].astype(str) + ' ' + df['time'].astype(str))
            elif 'timestamp' in df.columns:
                df['datetime'] = pd.to_datetime(df['timestamp'])
            elif 'date' in df.columns:
                df['datetime'] = pd.to_datetime(df['date'])
            elif 'time' in df.columns:
                df['datetime'] = pd.to_datetime(df['time'])
            else:
                continue

        df['datetime'] = pd.to_datetime(df['datetime'])
        df = df.sort_values('datetime').reset_index(drop=True)
        
        # Core Indicators
        df['ATR'] = calculate_atr(df, 14)
        df['Vol_SMA'] = df['volume'].rolling(window=20).mean() # Hardcoded 20-period per rules
        
        # Daily VWAP Calculation
        df['date_only'] = df['datetime'].dt.date
        df['TP'] = (df['high'] + df['low'] + df['close']) / 3
        df['TPV'] = df['TP'] * df['volume']
        df['Cum_TPV'] = df.groupby('date_only')['TPV'].cumsum()
        df['Cum_Vol'] = df.groupby('date_only')['volume'].cumsum()
        df['VWAP'] = df['Cum_TPV'] / df['Cum_Vol']
        
        current_capital = initial_capital
        
        for date_val, group in df.groupby('date_only'):
            # 09:15 to 09:59 Opening Range
            morning_session = group[(group['datetime'].dt.time >= pd.to_datetime('09:15').time()) & 
                                      (group['datetime'].dt.time <= pd.to_datetime('09:59').time())]
            
            if morning_session.empty:
                continue
                
            or_high = morning_session['high'].max()
            or_low = morning_session['low'].min()
            
            # 10:00 to 14:30 Trading Window
            trading_session = group[(group['datetime'].dt.time >= pd.to_datetime('10:00').time()) & 
                                      (group['datetime'].dt.time <= pd.to_datetime('14:30').time())]
            
            in_position = False
            
            for idx, row in trading_session.iterrows():
                if in_position:
                    if direction == 'Long':
                        if row['low'] <= stop_loss:
                            exit_price = stop_loss
                            exit_time = row['datetime']
                            reason = 'Stop Loss'
                            in_position = False
                        elif row['high'] >= target:
                            exit_price = target
                            exit_time = row['datetime']
                            reason = 'Target'
                            in_position = False
                        elif row['datetime'].time() >= pd.to_datetime('15:15').time():
                            exit_price = row['close']
                            exit_time = row['datetime']
                            reason = 'Time Square-off'
                            in_position = False
                    else: # Short
                        if row['high'] >= stop_loss:
                            exit_price = stop_loss
                            exit_time = row['datetime']
                            reason = 'Stop Loss'
                            in_position = False
                        elif row['low'] <= target:
                            exit_price = target
                            exit_time = row['datetime']
                            reason = 'Target'
                            in_position = False
                        elif row['datetime'].time() >= pd.to_datetime('15:15').time():
                            exit_price = row['close']
                            exit_time = row['datetime']
                            reason = 'Time Square-off'
                            in_position = False
                    
                    if not in_position:
                        gross_pnl = (exit_price - entry_price) * qty if direction == 'Long' else (entry_price - exit_price) * qty
                        net_pnl = gross_pnl - 15 # Deduct fixed friction
                        
                        all_trades.append({
                            'Symbol': symbol,
                            'Direction': direction,
                            'Entry Time': entry_time,
                            'Entry Price': entry_price,
                            'Exit Time': exit_time,
                            'Exit Price': exit_price,
                            'Reason': reason,
                            'Gross PnL': gross_pnl,
                            'Net PnL': net_pnl,
                            'Quantity': qty
                        })
                else:
                    if pd.isna(row['ATR']) or pd.isna(row['Vol_SMA']) or pd.isna(row['VWAP']):
                        continue
                        
                    # Volume Rule: Strictly > 1.5x Vol_SMA
                    is_volume_high = row['volume'] > (1.5 * row['Vol_SMA'])
                    
                    # Long Entry
                    if allow_long and (row['close'] > or_high) and (row['close'] > row['VWAP']) and is_volume_high:
                        direction = 'Long'
                        entry_price = row['close']
                        entry_time = row['datetime']
                        stop_loss = entry_price - (row['ATR'] * atr_mult)
                        risk_per_share = entry_price - stop_loss
                        
                        if risk_per_share > 0:
                            target = entry_price + (risk_per_share * rr_ratio)
                            risk_amount = current_capital * (risk_per_trade / 100.0)
                            qty = int(risk_amount / risk_per_share)
                            if qty > 0:
                                in_position = True
                            
                    # Short Entry
                    elif allow_short and (row['close'] < or_low) and (row['close'] < row['VWAP']) and is_volume_high:
                        direction = 'Short'
                        entry_price = row['close']
                        entry_time = row['datetime']
                        stop_loss = entry_price + (row['ATR'] * atr_mult)
                        risk_per_share = stop_loss - entry_price
                        
                        if risk_per_share > 0:
                            target = entry_price - (risk_per_share * rr_ratio)
                            risk_amount = current_capital * (risk_per_trade / 100.0)
                            qty = int(risk_amount / risk_per_share)
                            if qty > 0:
                                in_position = True

    return pd.DataFrame(all_trades)

def calculate_atr(df, period):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    return ranges.max(axis=1).rolling(period).mean()
