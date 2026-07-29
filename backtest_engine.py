import pandas as pd
import numpy as np

def run_strategy(data_dict, initial_capital, risk_per_trade, allow_long, allow_short, atr_mult, rr_ratio):
    all_trades = []
    
    for symbol, df in data_dict.items():
        # --- NEW: Robust Column Normalization ---
        df.columns = df.columns.str.strip().str.lower()
        
        # Map common time columns to 'datetime'
        if 'datetime' not in df.columns:
            if 'date' in df.columns:
                df = df.rename(columns={'date': 'datetime'})
            elif 'time' in df.columns:
                df = df.rename(columns={'time': 'datetime'})
            elif 'timestamp' in df.columns:
                df = df.rename(columns={'timestamp': 'datetime'})
            else:
                raise ValueError(f"Missing time column in {symbol} data. Found: {list(df.columns)}")
                
        # Ensure correct column formatting and sorting
        df['datetime'] = pd.to_datetime(df['datetime'])
        df = df.sort_values('datetime').reset_index(drop=True)
        
        # Calculate Indicators
        df['ATR'] = calculate_atr(df, 14)
        df['Vol_SMA'] = df['volume'].rolling(window=20).mean()
        
        # Calculate VWAP
        df['date_only'] = df['datetime'].dt.date
        df['TP'] = (df['high'] + df['low'] + df['close']) / 3
        df['TPV'] = df['TP'] * df['volume']
        df['Cum_TPV'] = df.groupby('date_only')['TPV'].cumsum()
        df['Cum_Vol'] = df.groupby('date_only')['volume'].cumsum()
        df['VWAP'] = df['Cum_TPV'] / df['Cum_Vol']
        
        # VWAP Slope (Current VWAP > VWAP 3 periods ago)
        df['VWAP_Prev_3'] = df['VWAP'].shift(3)
        df['VWAP_Rising'] = df['VWAP'] > df['VWAP_Prev_3']
        df['VWAP_Falling'] = df['VWAP'] < df['VWAP_Prev_3']
        
        current_capital = initial_capital
        
        for date_val, group in df.groupby('date_only'):
            # Skip Thursdays (Expiry manipulation filter)
            if pd.to_datetime(date_val).day_name() == 'Thursday':
                continue
                
            morning_session = group[(group['datetime'].dt.time >= pd.to_datetime('09:15').time()) & 
                                      (group['datetime'].dt.time <= pd.to_datetime('09:59').time())]
            
            if morning_session.empty:
                continue
                
            or_high = morning_session['high'].max()
            or_low = morning_session['low'].min()
            
            # Trading Session (12:00 PM to 02:30 PM)
            trading_session = group[(group['datetime'].dt.time >= pd.to_datetime('12:00').time()) & 
                                      (group['datetime'].dt.time <= pd.to_datetime('02:30').time())]
            
            in_position = False
            
            for idx, row in trading_session.iterrows():
                if in_position:
                    # Check exit conditions for active trade
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
                        elif row['datetime'].dt.time >= pd.to_datetime('15:15').time():
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
                        elif row['datetime'].dt.time >= pd.to_datetime('15:15').time():
                            exit_price = row['close']
                            exit_time = row['datetime']
                            reason = 'Time Square-off'
                            in_position = False
                    
                    if not in_position:
                        # Record trade
                        gross_pnl = (exit_price - entry_price) * qty if direction == 'Long' else (entry_price - exit_price) * qty
                        all_trades.append({
                            'Symbol': symbol,
                            'Direction': direction,
                            'Entry Time': entry_time,
                            'Entry Price': entry_price,
                            'Exit Time': exit_time,
                            'Exit Price': exit_price,
                            'Reason': reason,
                            'Gross PnL': gross_pnl,
                            'Quantity': qty
                        })
                else:
                    # Look for new entry
                    if pd.isna(row['ATR']) or pd.isna(row['Vol_SMA']) or pd.isna(row['VWAP_Prev_3']):
                        continue
                        
                    is_volume_high = row['volume'] > (1.5 * row['Vol_SMA'])
                    
                    # Long Entry
                    if allow_long and (row['close'] > or_high) and (row['close'] > row['VWAP']) and row['VWAP_Rising'] and is_volume_high:
                        direction = 'Long'
                        entry_price = row['close']
                        entry_time = row['datetime']
                        stop_loss = entry_price - (row['ATR'] * atr_mult)
                        risk_per_share = entry_price - stop_loss
                        target = entry_price + (risk_per_share * rr_ratio)
                        
                        risk_amount = current_capital * (risk_per_trade / 100.0)
                        qty = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0
                        if qty > 0:
                            in_position = True
                            
                    # Short Entry
                    elif allow_short and (row['close'] < or_low) and (row['close'] < row['VWAP']) and row['VWAP_Falling'] and is_volume_high:
                        direction = 'Short'
                        entry_price = row['close']
                        entry_time = row['datetime']
                        stop_loss = entry_price + (row['ATR'] * atr_mult)
                        risk_per_share = stop_loss - entry_price
                        target = entry_price - (risk_per_share * rr_ratio)
                        
                        risk_amount = current_capital * (risk_per_trade / 100.0)
                        qty = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0
                        if qty > 0:
                            in_position = True

    return pd.DataFrame(all_trades)

def calculate_atr(df, period):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    return true_range.rolling(period).mean()
