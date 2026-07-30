import pandas as pd
from datetime import time


def standardize_data(df):
    for col in df.columns:
        if col.lower() in ['date', 'datetime', 'time', 'timestamp']:
            df.rename(columns={col: 'Datetime'}, inplace=True)
            break

    rename_map = {col: col.capitalize() for col in df.columns if col.lower() in ['open', 'high', 'low', 'close', 'volume']}
    df.rename(columns=rename_map, inplace=True)
    return df


def calculate_indicators(df):
    df = df.copy()
    df = standardize_data(df)

    if 'Datetime' in df.columns:
        df['Datetime'] = pd.to_datetime(df['Datetime'])
        try:
            df['Datetime'] = df['Datetime'].dt.tz_localize(None)
        except TypeError:
            pass
        df.set_index("Datetime", inplace=True)

    df['Time'] = df.index.time
    df['Date_Str'] = df.index.strftime('%Y-%m-%d')

    df['H-L'] = df['High'] - df['Low']
    df['H-PC'] = abs(df['High'] - df['Close'].shift(1))
    df['L-PC'] = abs(df['Low'] - df['Close'].shift(1))
    df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    # BUG FIX: min_periods=1 so early candles get a usable (if noisy) ATR
    # instead of NaN silently producing phantom zero-quantity trades.
    df['ATR'] = df['TR'].rolling(14, min_periods=1).mean()

    if 'Volume' in df.columns:
        df['Vol_SMA'] = df['Volume'].rolling(20, min_periods=1).mean()
    else:
        df['Vol_SMA'] = 0
        df['Volume'] = 0

    df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
    df['TP_V'] = df['Typical_Price'] * df['Volume']
    df['Cum_Vol'] = df.groupby('Date_Str')['Volume'].cumsum()
    df['Cum_TP_V'] = df.groupby('Date_Str')['TP_V'].cumsum()
    df['VWAP'] = df['Cum_TP_V'] / (df['Cum_Vol'] + 1e-8)

    or_data = df[(df['Time'] >= time(9, 15)) & (df['Time'] < time(10, 0))]
    or_high_dict = or_data.groupby('Date_Str')['High'].max().to_dict()
    or_low_dict = or_data.groupby('Date_Str')['Low'].min().to_dict()

    df['OR_High'] = df['Date_Str'].apply(lambda x: or_high_dict.get(x, None))
    df['OR_Low'] = df['Date_Str'].apply(lambda x: or_low_dict.get(x, None))

    return df.reset_index()


def _generate_r_trades(data_dict, allow_long, allow_short, atr_mult, rr_ratio, vol_mult=1.5):
    """Pass 1: determine WHICH trades happen and their R-multiple outcome,
    independent of position sizing (fixes the non-compounding bug) and
    filled at the NEXT candle's open (fixes the same-candle lookahead bug)."""
    r_trades = []

    for symbol, raw_df in data_dict.items():
        df = standardize_data(raw_df)
        if df.empty or 'Volume' not in df.columns or 'Datetime' not in df.columns:
            continue
        df = calculate_indicators(df)

        in_trade = False
        pending = None  # signal fires this candle, fills NEXT candle's open
        trade_dir = 0
        entry_price = sl = target = sl_dist = 0.0
        entry_time = None

        for i in range(1, len(df)):
            row = df.iloc[i]
            current_time = row['Datetime'].time()

            # Fill any pending signal at this candle's open (no lookahead)
            if pending is not None and not in_trade:
                entry_price = row['Open']
                trade_dir = pending['dir']
                sl_dist = pending['sl_dist']
                entry_time = row['Datetime']
                if trade_dir == 1:
                    sl = entry_price - sl_dist
                    target = entry_price + (sl_dist * rr_ratio)
                else:
                    sl = entry_price + sl_dist
                    target = entry_price - (sl_dist * rr_ratio)
                in_trade = True
                pending = None
                # fall through: this candle's H/L can still hit SL/target immediately

            if in_trade and current_time >= time(15, 15):
                exit_price = row['Close']
                move = (exit_price - entry_price) if trade_dir == 1 else (entry_price - exit_price)
                r_trades.append(_pack(symbol, trade_dir, entry_time, entry_price, row['Datetime'],
                                       exit_price, "Time Exit", move / sl_dist))
                in_trade = False
                continue

            if in_trade:
                if trade_dir == 1:
                    if row['Low'] <= sl:
                        r_trades.append(_pack(symbol, 1, entry_time, entry_price, row['Datetime'], sl, "SL Hit", -1.0))
                        in_trade = False
                    elif row['High'] >= target:
                        r_trades.append(_pack(symbol, 1, entry_time, entry_price, row['Datetime'], target, "Target Hit", rr_ratio))
                        in_trade = False
                else:
                    if row['High'] >= sl:
                        r_trades.append(_pack(symbol, -1, entry_time, entry_price, row['Datetime'], sl, "SL Hit", -1.0))
                        in_trade = False
                    elif row['Low'] <= target:
                        r_trades.append(_pack(symbol, -1, entry_time, entry_price, row['Datetime'], target, "Target Hit", rr_ratio))
                        in_trade = False
                continue

            if pending is None and time(10, 0) <= current_time <= time(14, 25):
                if pd.isna(row['OR_High']) or pd.isna(row['VWAP']) or pd.isna(row['Vol_SMA']) or pd.isna(row['ATR']) or row['ATR'] <= 0:
                    continue

                vol_condition = row['Volume'] > (row['Vol_SMA'] * vol_mult)
                sl_dist_candidate = row['ATR'] * atr_mult
                if sl_dist_candidate <= 0:
                    continue

                if allow_long and row['Close'] > row['OR_High'] and row['Close'] > row['VWAP'] and vol_condition:
                    pending = {'dir': 1, 'sl_dist': sl_dist_candidate}
                elif allow_short and row['Close'] < row['OR_Low'] and row['Close'] < row['VWAP'] and vol_condition:
                    pending = {'dir': -1, 'sl_dist': sl_dist_candidate}

    return pd.DataFrame(r_trades)


def _pack(symbol, direction, entry_time, entry_price, exit_time, exit_price, reason, r_multiple):
    return {
        'Symbol': symbol, 'Direction': "Long" if direction == 1 else "Short",
        'Entry Time': entry_time, 'Entry Price': entry_price,
        'Exit Time': exit_time, 'Exit Price': exit_price, 'Reason': reason,
        'r_multiple': r_multiple,
    }


def run_strategy(data_dict, initial_capital, risk_per_trade, allow_long, allow_short,
                  atr_mult, rr_ratio, friction_per_leg=15.0, turnover_cost_rate=0.00025,
                  max_active_trades=3):
    """
    Two-pass backtest, same approach as the V-ORB 2.x engine:
    Pass 1 finds trades and their R-multiple outcome. Pass 2 sizes each trade off
    CURRENT running equity (compounding) and deducts costs that scale with the
    actual traded value (quantity x price), not just price alone.
    """
    r_trades = _generate_r_trades(data_dict, allow_long, allow_short, atr_mult, rr_ratio)

    if r_trades.empty:
        return pd.DataFrame()

    r_trades = r_trades.sort_values('Entry Time').reset_index(drop=True)

    # Portfolio concurrency filter across symbols
    approved = []
    active_exits = []
    for _, t in r_trades.iterrows():
        active_exits = [e for e in active_exits if e > t['Entry Time']]
        if len(active_exits) < max_active_trades:
            approved.append(t)
            active_exits.append(t['Exit Time'])

    if not approved:
        return pd.DataFrame()

    approved_df = pd.DataFrame(approved).sort_values('Entry Time').reset_index(drop=True)

    running_equity = initial_capital
    rows = []
    for _, t in approved_df.iterrows():
        risk_amount = running_equity * (risk_per_trade / 100.0)
        entry_price = t['Entry Price']

        # Recover the actual sl_dist so quantity reflects the REAL stop distance
        # (kept out of the r_trades table to keep pass 1 lightweight)
        if t['Reason'] == 'SL Hit':
            sl_dist = abs(t['Entry Price'] - t['Exit Price'])
        elif t['Reason'] == 'Target Hit':
            sl_dist = abs(t['Entry Price'] - t['Exit Price']) / rr_ratio
        else:  # Time Exit -- r_multiple = move / sl_dist, so back it out
            move = abs(t['Exit Price'] - t['Entry Price'])
            sl_dist = move / abs(t['r_multiple']) if t['r_multiple'] != 0 else max(entry_price * 0.005, 0.01)

        sl_dist = max(sl_dist, entry_price * 0.0005)  # sanity floor
        quantity = max(1, int(risk_amount / sl_dist))

        gross_pnl = t['r_multiple'] * quantity * sl_dist

        notional_entry = quantity * t['Entry Price']
        notional_exit = quantity * t['Exit Price']
        # BUG FIX: turnover-based costs now scale with quantity, not just price.
        cost = (2 * friction_per_leg) + (notional_entry * turnover_cost_rate) + (notional_exit * turnover_cost_rate)
        net_pnl = gross_pnl - cost

        running_equity += net_pnl

        rows.append({
            'Symbol': t['Symbol'], 'Direction': t['Direction'],
            'Entry Time': t['Entry Time'], 'Entry Price': t['Entry Price'],
            'Exit Time': t['Exit Time'], 'Exit Price': t['Exit Price'],
            'Reason': t['Reason'], 'Quantity': quantity,
            'Gross PnL': gross_pnl, 'Cost': cost, 'Net PnL': net_pnl,
            'Equity After': running_equity,
        })

    return pd.DataFrame(rows).sort_values('Exit Time').reset_index(drop=True)
                    
