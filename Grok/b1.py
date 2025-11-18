# gold_m15_ultimate_2025.py
# Phiên bản cuối cùng - Partial + Telegram Alert + 30s check
# Tác giả: Grok Trader VN (dựa yêu cầu bạn)

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
import datetime as dt
import requests
import matplotlib.pyplot as plt
import os
from typing import Optional

# ========================== CẤU HÌNH ==========================
YOUR_LOGIN = 272736909          # ← ĐỔI THÀNH LOGIN EXNESS CỦA BẠN
YOUR_PASSWORD = "@Dinhhieu273"    # ← ĐỔI THÀNH PASS
SERVER = "Exness-MT5Trial14"      # hoặc Exness-MT5Trial / Exness-MT5Real2...
PATH="C:\\Program Files\\MetaTrader 5 EXNESS -14\\terminal64.exe"
# Telegram config (tạo bot tại @BotFather)

TELEGRAM_TOKEN = "6398751744:AAGp7VH7B00_kzMqdaFB59xlqAXnlKTar-g"

# Chat ID để nhận thông báo (ID của user hoặc group trên Telegram)
# Để lấy Chat ID: Gửi tin nhắn cho bot @userinfobot hoặc tìm trong bot logs
CHAT_ID = "1887610382"
SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_M15
DEVIATION = 10
MAGIC = 18112025
RISK_PERCENT = 0.7
ATR_MULTIPLIER = 1.3

# ========================== KHỞI TẠO ==========================
def send_telegram(msg: str, image_path: str = None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}
    try:
        requests.post(url, data=data)
        if image_path:
            with open(image_path, "rb") as f:
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
                              data={"chat_id": CHAT_ID}, files={"photo": f})
    except: pass

def capture_chart():
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 100)
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    plt.figure(figsize=(12,7), facecolor='black')
    ax = plt.gca()
    ax.set_facecolor('black')
    
    plt.plot(df['time'], df['close'], color='gold', linewidth=2, label='XAUUSD')
    plt.title(f"XAUUSD M15 - {dt.datetime.now().strftime('%H:%M %d/%m/%Y')}", color='white', fontsize=16)
    plt.grid(True, alpha=0.3)
    plt.legend()
    
    path = "chart_signal.png"
    plt.savefig(path, dpi=200, bbox_inches='tight', facecolor='black')
    plt.close()
    return path

def init_mt5():
    if not mt5.initialize(path=PATH,login=YOUR_LOGIN, password=YOUR_PASSWORD, server=SERVER):
        print("LỖI KẾT NỐI MT5:", mt5.last_error())
        return False
    print(f"✓ Đã kết nối Exness | Balance: {mt5.account_info().balance:,}$")
    return True

# ========================== INDICATORS ==========================
def get_data() -> pd.DataFrame:
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 300)
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    df['ema8'] = df['close'].ewm(span=8, adjust=False).mean()
    df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['ema55'] = df['close'].ewm(span=55, adjust=False).mean()
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    delta = df['close'].diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ma_up = up.ewm(com=13, adjust=False).mean()
    ma_down = down.ewm(com=13, adjust=False).mean()
    df['rsi'] = 100 - (100 / (1 + ma_up/ma_down))
    
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.ewm(span=14, adjust=False).mean()
    
    return df

# ========================== QUẢN LÝ LỆNH ==========================
def close_partial(ticket: int, volume: float, price: float, comment: str):
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": volume,
        "type": mt5.ORDER_TYPE_SELL if mt5.positions_get(ticket=ticket)[0].type == 0 else mt5.ORDER_TYPE_BUY,
        "position": ticket,
        "price": price,
        "deviation": DEVIATION,
        "magic": MAGIC,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    mt5.order_send(request)

def manage_positions():
    positions = mt5.positions_get(symbol=SYMBOL)
    if not positions: return
    
    for pos in positions:
        if pos.magic != MAGIC: continue
        df = get_data()
        last = df.iloc[-1]
        profit_pips = (mt5.symbol_info_tick(SYMBOL).bid - pos.price_open) / 0.1 if pos.type == 0 else (pos.price_open - mt5.symbol_info_tick(SYMBOL).ask) / 0.1
        sl_pips = abs(pos.price_open - pos.sl) / 0.1 if pos.sl > 0 else 30
        
        # Breakeven
        if profit_pips > 1.0 * sl_pips and pos.sl < pos.price_open + 0.1:
            new_sl = pos.price_open + 0.5 if pos.type == 0 else pos.price_open - 0.5
            mt5.position_modify(ticket=pos.ticket, sl=new_sl, tp=pos.tp)
        
        # Partial 1.5R
        if profit_pips >= 1.5 * sl_pips and pos.volume >= 0.03:
            close_partial(pos.ticket, round(pos.volume * 0.5, 2), 
                         mt5.symbol_info_tick(SYMBOL).bid if pos.type == 0 else mt5.symbol_info_tick(SYMBOL).ask,
                         "Partial 50% @1.5R")
            send_telegram(f"🟢 <b>PARTIAL 50%</b> {pos.volume*0.5} lot\nGiá: {pos.price_current:.2f} | Lãi: {profit_pips:.1f} pips")
        
        # Partial 2.5R
        elif profit_pips >= 2.5 * sl_pips and pos.volume >= 0.02:
            close_partial(pos.ticket, round(pos.volume * 0.6, 2), 
                         mt5.symbol_info_tick(SYMBOL).bid if pos.type == 0 else mt5.symbol_info_tick(SYMBOL).ask,
                         "Partial 30% @2.5R")
        
        # Trailing EMA8
        trail = last['ema8']
        if pos.type == 0 and trail > pos.sl + 1.0:
            mt5.position_modify(ticket=pos.ticket, sl=trail - 1.0)
        elif pos.type == 1 and trail < pos.sl - 1.0:
            mt5.position_modify(ticket=pos.ticket, sl=trail + 1.0)

# ========================== VÀO LỆNH ==========================
def trading_logic():
    if mt5.positions_total() >= 1: 
        manage_positions()
        return
    
    df = get_data()
    last, prev = df.iloc[-1], df.iloc[-2]
    
    # Điều kiện siêu chặt (phiên bản cuối)
    crossover_up = prev.ema8 <= prev.ema21 and last.ema8 > last.ema21
    crossover_down = prev.ema8 >= prev.ema21 and last.ema8 < last.ema21
    rsi_buy = 50 < last.rsi < 78 and prev.rsi <= 50
    rsi_sell = 22 < last.rsi < 50 and prev.rsi >= 50
    volume_spike = last.tick_volume > df.tick_volume.rolling(20).mean().iloc[-1] * 2
    price_above_ema200 = last.close > last.ema200
    atr_pips = last.atr * ATR_MULTIPLIER
    
    balance = mt5.account_info().balance
    risk_money = balance * RISK_PERCENT / 100
    lot = max(0.01, round(risk_money / (atr_pips * 10), 2))
    
    current_price = mt5.symbol_info_tick(SYMBOL).ask
    
    if (crossover_up and rsi_buy and volume_spike and price_above_ema200 and 
        last.close > last.ema55 and dt.datetime.now().hour >= 13):  # Chỉ trade từ 13h VN
        
        sl = round(current_price - atr_pips * 0.1, 2)
        tp = round(current_price + atr_pips * 2.5 * 0.1, 2)
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": lot,
            "type": mt5.ORDER_TYPE_BUY,
            "price": current_price,
            "sl": sl,
            "tp": tp,
            "deviation": DEVIATION,
            "magic": MAGIC,
            "comment": "GoldM15_Ultimate",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            chart_path = capture_chart()
            send_telegram(
                f"🚀 <b>NEW BUY ORDER</b>\n"
                f"💰 Lot: <b>{lot}</b> | SL: {atr_pips:.1f} pips\n"
                f"🎯 Entry: <b>{current_price}</b> | TP: {tp}\n"
                f"⏰ {dt.datetime.now().strftime('%H:%M %d/%m/%Y')}",
                chart_path
            )
            os.remove(chart_path)
    else:
        print("No valid trade signal at this time.")
# ========================== MAIN LOOP ==========================
if not init_mt5():
    exit()

print("=== EA Gold M15 ULTIMATE 2025 ĐANG CHẠY - CHECK 30S/LẦN ===")
send_telegram("🟢 <b>EA đã sẵn sàng săn pips!</b>")

while True:
    try:
        trading_logic()
        time.sleep(30)  # Chính xác 30 giây kiểm tra 1 lần
    except Exception as e:
        send_telegram(f"⚠️ Lỗi EA: {e}")
        time.sleep(60)

mt5.shutdown()