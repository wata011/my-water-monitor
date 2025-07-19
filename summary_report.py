#!/usr/bin/env python3
import os
import json
from datetime import datetime, timedelta
import pytz
import pandas as pd
import matplotlib.pyplot as plt
import requests
import matplotlib.dates as mdates

# ── CONFIG ──
TZ = pytz.timezone('Asia/Bangkok')
LINE_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_TARGET = os.getenv('LINE_TARGET_ID')

# Paths to your existing logs/state files
CHAOP_LOG    = 'historical_log.csv'
INBURI_LOG   = 'inburi_log.csv'
WEATHER_LOG  = 'weather_log.csv'

# ── 1) Load & plot Chaop storage ──
try:
    df_c = pd.read_csv(CHAOP_LOG, names=['ts','storage'], parse_dates=['ts'])
    df_c['storage'] = df_c['storage'].str.replace(r'\s*cms','',regex=True).astype(float)

    # กรองข้อมูลย้อนหลัง 7 วัน
    cutoff = datetime.now(TZ) - timedelta(days=7)
    sub_chaop = df_c[df_c['ts'] >= cutoff].copy()

    # ตรวจสอบว่ามีข้อมูลเพียงพอสำหรับการพล็อตหรือไม่
    if sub_chaop.empty:
        print(f"WARN: ไม่มีข้อมูลเพียงพอใน {CHAOP_LOG} สำหรับการสร้างกราฟ 7 วันล่าสุด")
        last_chaop = None
    else:
        last_chaop = sub_chaop.iloc[-1]

    # --- การปรับปรุง UI กราฟ ---
    plt.style.use('seaborn-v0_8-darkgrid') # ใช้สไตล์ darkgrid เพื่อความทันสมัย
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Tahoma', 'Arial Unicode MS', 'DejaVu Sans'] # เพิ่มฟอนต์ที่รองรับภาษาไทยได้ดีขึ้น
    plt.rcParams['axes.labelweight'] = 'bold'
    plt.rcParams['axes.titleweight'] = 'bold'
    plt.rcParams['text.color'] = 'white' # สีตัวอักษรบนกราฟ (ชื่อแกน, หัวข้อ)
    plt.rcParams['axes.labelcolor'] = 'white'
    plt.rcParams['xtick.color'] = 'white'
    plt.rcParams['ytick.color'] = 'white'
    plt.rcParams['grid.color'] = '#444444' # สีเส้นกริด

    fig, ax = plt.subplots(figsize=(14, 8)) # ปรับขนาดกราฟให้ใหญ่ขึ้น

    # พล็อตกราฟเส้น
    ax.plot(sub_chaop['ts'], sub_chaop['storage'],
            marker='o', markersize=7,
            linestyle='-', linewidth=2.5,
            color='#87CEEB', # สีฟ้าสดใส (SkyBlue)
            label='ปริมาณน้ำ (ลบ.ม./วินาที)')

    # เพิ่มข้อความบนกราฟ (ค่าสุดท้าย)
    if last_chaop is not None:
        ax.annotate(f'{last_chaop.storage:.1f} cms',
                    xy=(last_chaop.ts, last_chaop.storage),
                    xytext=(10, -10), textcoords='offset points',
                    ha='left', va='top', fontsize=12, color='#00FF7F', # สีเขียวสด (SpringGreen)
                    bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="#00FF7F", lw=1, alpha=0.9))

    ax.set_title('ระดับน้ำเขื่อนเจ้าพระยา (ย้อนหลัง 7 วัน)', fontsize=20, color='white', pad=20)
    ax.set_xlabel('วันที่และเวลา', fontsize=15, color='white')
    ax.set_ylabel('ปริมาณน้ำ (ลบ.ม./วินาที)', fontsize=15, color='white')

    # ปรับแกน X (วันที่)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b %H:%M')) # รูปแบบ: 19 ก.ค. 10:30
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1)) # แสดงทุกวัน
    ax.xaxis.set_minor_locator(mdates.HourLocator(interval=6)) # แสดงทุก 6 ชั่วโมง
    plt.xticks(rotation=45, ha='right', fontsize=12)

    # ปรับแกน Y (ปริมาณน้ำ)
    ax.tick_params(axis='y', labelsize=12)

    ax.legend(fontsize=12, loc='upper left', frameon=True, facecolor='lightgray', edgecolor='white') # ปรับ Legend

    # ตั้งค่าพื้นหลัง
    fig.set_facecolor('#1a1a1a') # พื้นหลังของ Figure
    ax.set_facecolor('#2d2d2d') # พื้นหลังของพื้นที่กราฟ

    plt.tight_layout()
    plt.savefig('chaop_summary.png', dpi=200, bbox_inches='tight') # เพิ่ม dpi เพื่อคุณภาพดีขึ้นมาก
    plt.close()

except FileNotFoundError:
    print(f"Error: {CHAOP_LOG} not found. Skipping Chaopraya data.")
    last_chaop = None
except Exception as e:
    print(f"Error processing {CHAOP_LOG}: {e}")
    last_chaop = None

# ── 2) Latest readings for Inburi ──
# อ่านข้อมูลอินทร์บุรี (คาดว่า format ใน log file เป็น ts,water_level,bank_level,status,below_bank,time)
try:
    df_i = pd.read_csv(INBURI_LOG, names=['ts','water_level','bank_level','status','below_bank','time'], parse_dates=['ts'])
    last_inb_data = df_i.iloc[-1] if not df_i.empty else None
except FileNotFoundError:
    print(f"Error: {INBURI_LOG} not found. Skipping Inburi data.")
    last_inb_data = None
except Exception as e:
    print(f"Error processing {INBURI_LOG}: {e}")
    last_inb_data = None

# ── 3) Next weather event (if any) ──
try:
    df_w = pd.read_csv(WEATHER_LOG, names=['ts','event','value'], parse_dates=['ts'])
    now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
    df_w['ts_utc'] = df_w['ts'].dt.tz_localize(TZ, errors='coerce').dt.tz_convert(pytz.UTC)
    upcoming = df_w[df_w['ts_utc'] > now_utc].copy()
    upcoming = upcoming.sort_values(by='ts_utc').reset_index(drop=True)

    next_evt = None
    if not upcoming.empty:
        next_evt_row = upcoming.iloc[0]
        next_evt = {
            'ts': next_evt_row['ts'], 
            'event': next_evt_row['event'], 
            'value': next_evt_row['value']
        }

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
    lines.append("🌊 เขื่อนเจ้าพระยา: ไม่มีข้อมูลเขื่อนเจ้าพระยา")

# ปรับปรุงข้อความอินทร์บุรีให้ชัดเจนยิ่งขึ้น
if last_inb_data is not None and isinstance(last_inb_data.get('water_level'), (int, float)):
    status_text = f" ({last_inb_data.get('status', 'ไม่ระบุสถานะ')})" if last_inb_data.get('status') else ""
    lines.append(f"🏞️ อินทร์บุรี (ระดับน้ำ): {last_inb_data['water_level']:.2f} ม.{status_text} ณ {last_inb_data['time']}")
    if isinstance(last_inb_data.get('below_bank'), (int, float)):
         lines.append(f"  └ ห่างจากตลิ่ง: {last_inb_data['below_bank']:.2f} ม.")
else:
    lines.append("🏞️ อินทร์บุรี: ไม่มีข้อมูลระดับน้ำ")

if next_evt is not None:
    lines += [
        "",
        f"⛅ พยากรณ์อากาศ: {next_evt['event']} ที่ {next_evt['ts'].strftime('%H:%M')} (ค่า: {next_evt['value']})"
    ]
else:
    lines.append("\n⛅ พยากรณ์อากาศ: ไม่มีเหตุการณ์สำคัญใน 12 ชม. ข้างหน้า") # ปรับข้อความให้ชัดเจน

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
        {"type":"text", "text": text},
        {
          "type":"image",
          "originalContentUrl":"https://wata011.github.io/my-water-monitor/chaop_summary.png",
          "previewImageUrl":"https://wata011.github.io/my-water-monitor/chaop_summary.png"
        }
    ]
}
try:
    resp = requests.post(push_url, headers=headers, json=payload)
    resp.raise_for_status()
    print("Daily summary sent.")
except requests.exceptions.RequestException as e:
    print(f"Failed to send LINE message: {e}")
