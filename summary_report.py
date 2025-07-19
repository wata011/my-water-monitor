#!/usr/bin/env python3
import os
import json
from datetime import datetime, timedelta
import pytz
import pandas as pd
import matplotlib.pyplot as plt
import requests

# ── CONFIG ──
TZ = pytz.timezone('Asia/Bangkok')
LINE_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_TARGET = os.getenv('LINE_TARGET_ID')

# Paths to your existing logs/state files
CHAOP_LOG    = 'historical_log.csv'      # from scraper.py
INBURI_LOG   = 'inburi_log.csv'          # new: timestamp, water_level
WEATHER_LOG  = 'weather_log.csv'         # new: timestamp,event_type,value

# ── 1) Load & plot Chaop storage ──
try:
    df_c = pd.read_csv(CHAOP_LOG, names=['ts','storage'], parse_dates=['ts'])
    df_c['storage'] = df_c['storage'].str.replace(r'\s*cms','',regex=True).astype(float)
    cutoff = datetime.now(TZ) - timedelta(days=7)
    sub = df_c[df_c['ts']>=cutoff]
    plt.figure(figsize=(8,4))
    plt.plot(sub['ts'], sub['storage'], marker='o')
    plt.title('Chaopraya Storage (Last 7 days)')
    plt.xlabel('Date')
    plt.ylabel('Storage (cms)')
    plt.tight_layout()
    plt.savefig('chaop_summary.png')
    plt.close()
    last_chaop = df_c.iloc[-1]
except FileNotFoundError:
    print(f"Error: {CHAOP_LOG} not found. Skipping Chaopraya data.")
    last_chaop = None
except Exception as e:
    print(f"Error processing {CHAOP_LOG}: {e}")
    last_chaop = None

# ── 2) Latest readings ──
try:
    df_i = pd.read_csv(INBURI_LOG, names=['ts','level'], parse_dates=['ts'])
    last_inb = df_i.iloc[-1]
except FileNotFoundError:
    print(f"Error: {INBURI_LOG} not found. Skipping Inburi data.")
    last_inb = None
except Exception as e:
    print(f"Error processing {INBURI_LOG}: {e}")
    last_inb = None

# ── 3) Next weather event (if any) ──
try:
    df_w = pd.read_csv(WEATHER_LOG, names=['ts','event','value'], parse_dates=['ts'])
    # ตัวกรองสำหรับพยากรณ์ล่วงหน้า (ใช้เวลาในอนาคต)
    now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
    upcoming = df_w[df_w['ts'] > now_utc.astimezone(TZ)] # ตรวจสอบเวลาให้ตรง timezone ด้วย
    next_evt = upcoming.iloc[0] if not upcoming.empty else None
except FileNotFoundError:
    print(f"Error: {WEATHER_LOG} not found. Skipping weather data.")
    next_evt = None
except Exception as e:
    print(f"Error processing {WEATHER_LOG}: {e}")
    next_evt = None

# ── 4) Build message ──
lines = [
    "📊 **สรุปรายงานประจำวัน**",
    f"🗓️ วันที่: {datetime.now(TZ).strftime('%d/%m/%Y')}",
    "",
]

if last_chaop is not None:
    lines.append(f"🌊 เขื่อนเจ้าพระยา: {last_chaop.storage:.1f} cms ณ {last_chaop.ts.strftime('%H:%M')}")
else:
    lines.append("🌊 เขื่อนเจ้าพระยา: ไม่มีข้อมูล")

if last_inb is not None:
    lines.append(f"🏞️ อินทร์บุรี: {last_inb.level:.2f} ม. ณ {last_inb.ts.strftime('%H:%M')}")
else:
    lines.append("🏞️ อินทร์บุรี: ไม่มีข้อมูล")

if next_evt is not None:
    lines += [
        "",
        f"⛅ ต่อไป: {next_evt.event} at {next_evt.ts.strftime('%H:%M')} (value: {next_evt.value})"
    ]
else:
    lines.append("\n⛅ พยากรณ์อากาศ: ไม่มีเหตุการณ์สำคัญในอนาคตอันใกล้")

text = "\n".join(lines)

# ── 5) Push via LINE ──
if not (LINE_TOKEN and LINE_TARGET):
    print("Error: LINE_TOKEN or LINE_TARGET not set. Skipping LINE notify.")
    exit()

push_url = 'https://api.line.me/v2/bot/message/push'
headers = {
    'Authorization': f'Bearer {LINE_TOKEN}',
    'Content-Type':  'application/json'
}
payload = {
    "to": LINE_TARGET,
    "messages": [
        {"type":"text", "text": text},
        {
          "type":"image",
          "originalContentUrl":"<YOUR_PUBLIC_URL>/chaop_summary.png", # <--- **สำคัญมาก!**
          "previewImageUrl":"<YOUR_PUBLIC_URL>/chaop_summary.png"    # <--- **สำคัญมาก!**
        }
    ]
}
try:
    resp = requests.post(push_url, headers=headers, json=payload)
    resp.raise_for_status()
    print("Daily summary sent.")
except requests.exceptions.RequestException as e:
    print(f"Failed to send LINE message: {e}")
