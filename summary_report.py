#!/usr/bin/env python3
import os
import json
from datetime import datetime, timedelta
import pytz
import pandas as pd
import requests

# ── CONFIG ──
TZ = pytz.timezone('Asia/Bangkok')
LINE_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_TARGET = os.getenv('LINE_TARGET_ID')

# Paths to your existing logs/state files
CHAOP_LOG    = 'historical_log.csv'
INBURI_LOG   = 'inburi_log.csv'
WEATHER_LOG  = 'weather_log.csv'

# ── Helper function to get data and 24-hour prior data ──
def get_data_with_24hr_prior(df, ts_col, value_col):
    if df.empty:
        return None, None, None

    df = df.sort_values(by=ts_col).drop_duplicates(subset=[ts_col], keep='last')

    latest_data = df.iloc[-1]

    # หาข้อมูลเมื่อ 24 ชั่วโมงที่แล้ว
    time_24hr_ago = latest_data[ts_col] - timedelta(hours=24)

    # ค้นหาข้อมูลที่ใกล้เคียงที่สุดกับ 24 ชั่วโมงที่แล้ว
    idx_24hr_ago = (df[ts_col] - time_24hr_ago).abs().idxmin()
    data_24hr_ago = df.loc[idx_24hr_ago]

    # ตรวจสอบว่าข้อมูล 24 ชั่วโมงที่แล้วห่างจากเวลาที่ต้องการไม่เกิน 2 ชั่วโมง
    if abs((data_24hr_ago[ts_col] - time_24hr_ago).total_seconds()) > 7200:
        data_24hr_ago = None

    return latest_data, data_24hr_ago, df

# ── 1) Load Chaopraya storage data ──
latest_chaop = None
chaop_24hr_ago = None
try:
    df_c = pd.read_csv(CHAOP_LOG, names=['ts','storage'], parse_dates=['ts'])
    df_c['storage'] = df_c['storage'].str.replace(r'\s*cms','',regex=True).astype(float)
    latest_chaop, chaop_24hr_ago, _ = get_data_with_24hr_prior(df_c, 'ts', 'storage')
except FileNotFoundError:
    print(f"Error: {CHAOP_LOG} not found. Skipping Chaopraya data.")
except Exception as e:
    print(f"Error processing {CHAOP_LOG}: {e}")

# ── 2) Load Inburi water level data ──
latest_inb = None
inb_24hr_ago = None
try:
    df_i = pd.read_csv(INBURI_LOG, names=['ts','water_level','bank_level','status','below_bank','time'], parse_dates=['ts'])
    latest_inb, inb_24hr_ago, _ = get_data_with_24hr_prior(df_i, 'ts', 'water_level')
except FileNotFoundError:
    print(f"Error: {INBURI_LOG} not found. Skipping Inburi data.")
except Exception as e:
    print(f"Error processing {INBURI_LOG}: {e}")

# ── 3) Next weather event (if any) ──
next_evt = None
try:
    df_w = pd.read_csv(WEATHER_LOG, names=['ts','event','value'], parse_dates=['ts'])
    now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
    
    if df_w['ts'].dt.tz is None:
        df_w['ts_utc'] = df_w['ts'].dt.tz_localize(TZ, nonexistent='NaT').dt.tz_convert(pytz.UTC)
    else:
        df_w['ts_utc'] = df_w['ts'].dt.tz_convert(pytz.UTC)

    upcoming = df_w[df_w['ts_utc'] > now_utc].copy()
    upcoming = upcoming.sort_values(by='ts_utc').reset_index(drop=True)

    if not upcoming.empty:
        next_evt_row = upcoming.iloc[0]
        next_evt = {
            'ts': next_evt_row['ts'],
            'event': next_evt_row['event'],
            'value': next_evt_row['value']
        }
except FileNotFoundError:
    print(f"Error: {WEATHER_LOG} not found. Skipping weather data.")
except Exception as e:
    print(f"Error processing {WEATHER_LOG}: {e}")

# ── 4) Build message ──
lines = [
    "📊 **สรุปรายงานสถานการณ์น้ำและอากาศ**",
    f"🗓️ วันที่: {datetime.now(TZ).strftime('%d/%m/%Y %H:%M น.')}",
    "",
]

# --- เขื่อนเจ้าพระยา ---
lines.append("🌊 **สถานการณ์น้ำเขื่อนเจ้าพระยา**")
if latest_chaop is not None and pd.notna(latest_chaop['storage']):
    lines.append(f"  • ปริมาณน้ำท้ายเขื่อนล่าสุด: {latest_chaop['storage']:.1f} ลบ.ม./วินาที ณ {latest_chaop['ts'].strftime('%H:%M น.')}")
    if chaop_24hr_ago is not None and pd.notna(chaop_24hr_ago['storage']):
        diff_chaop = latest_chaop['storage'] - chaop_24hr_ago['storage']
        change_text = "เพิ่มขึ้น" if diff_chaop > 0 else "ลดลง" if diff_chaop < 0 else "คงที่"
        lines.append(f"  • เปลี่ยนแปลงจาก 24 ชม. ที่แล้ว: {change_text} {abs(diff_chaop):.1f} ลบ.ม./วินาที")
    else:
        lines.append("  • ไม่มีข้อมูลเปรียบเทียบ 24 ชม. ที่แล้ว")
else:
    lines.append("  • ไม่มีข้อมูลปริมาณน้ำท้ายเขื่อน")
lines.append("")

# --- อินทร์บุรี ---
lines.append("🏞️ **สถานการณ์น้ำสะพานอินทร์บุรี**")
if latest_inb is not None and pd.notna(latest_inb['water_level']):
    status_text = f" ({latest_inb.get('status', 'ไม่ระบุสถานะ')})" if latest_inb.get('status') else ""
    lines.append(f"  • ระดับน้ำล่าสุด: {latest_inb['water_level']:.2f} ม.รทก.{status_text} ณ {latest_inb['ts'].strftime('%H:%M น.')}")

    if pd.notna(latest_inb.get('below_bank')):
         lines.append(f"  • ห่างจากตลิ่ง: {latest_inb['below_bank']:.2f} ม.")

    if inb_24hr_ago is not None and pd.notna(inb_24hr_ago['water_level']):
        diff_inb = latest_inb['water_level'] - inb_24hr_ago['water_level']
        change_text = "เพิ่มขึ้น" if diff_inb > 0 else "ลดลง" if diff_inb < 0 else "คงที่"
        lines.append(f"  • เปลี่ยนแปลงจาก 24 ชม. ที่แล้ว: {change_text} {abs(diff_inb):.2f} ม.")
    else:
        lines.append("  • ไม่มีข้อมูลเปรียบเทียบ 24 ชม. ที่แล้ว")
else:
    lines.append("  • ไม่มีข้อมูลระดับน้ำสะพานอินทร์บุรี")
lines.append("")

# --- พยากรณ์อากาศ ---
lines.append("⛅ **พยากรณ์อากาศ**")
if next_evt is not None:
    lines.append(f"  • เหตุการณ์ถัดไป: {next_evt['event']} (ค่า: {next_evt['value']})")
    lines.append(f"  • เวลา: {next_evt['ts'].strftime('%d/%m/%Y %H:%M น.')}")
else:
    lines.append("  • ไม่มีเหตุการณ์สำคัญใน 12 ชั่วโมงข้างหน้า")

text = "\n".join(lines)

# ── 5) Push via LINE ──
if not (LINE_TOKEN and LINE_TARGET):
    print("Error: LINE_TOKEN/LINE_TARGET ไม่ครบ! ข้ามการแจ้งเตือน LINE.")
    exit()

push_url = 'https://api.line.me/v2/bot/message/push'
headers = {
    'Authorization': f"Bearer {LINE_TOKEN}",
    'Content-Type':  "application/json"
}
payload = {
    "to": LINE_TARGET,
    "messages": [
        {"type":"text", "text": text}
    ]
}
try:
    resp = requests.post(push_url, headers=headers, json=payload)
    resp.raise_for_status()
    print("Daily summary sent.")
except requests.exceptions.RequestException as e:
    print(f"Failed to send LINE message: {e}")
