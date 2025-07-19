#!/usr/bin/env python3
import os
import json
from datetime import datetime, timedelta
import pytz
import pandas as pd
import matplotlib.pyplot as plt
import requests
import matplotlib.dates as mdates # เพิ่มบรรทัดนี้สำหรับจัดการวันที่ในกราฟ

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

    # กรองข้อมูลย้อนหลัง 7 วันตามคำขอ
    cutoff = datetime.now(TZ) - timedelta(days=7)
    sub = df_c[df_c['ts'] >= cutoff].copy() # ใช้ .copy() เพื่อหลีกเลี่ยง SettingWithCopyWarning

    # ตั้งค่าสไตล์กราฟให้สวยงามและทันสมัย
    plt.style.use('seaborn-v0_8-darkgrid') # ใช้สไตล์ seaborn-darkgrid ที่ดูดี
    plt.rcParams['font.family'] = 'sans-serif' # ตั้งค่าฟอนต์
    plt.rcParams['font.sans-serif'] = ['Arial', 'Tahoma', 'DejaVu Sans'] # เพิ่มฟอนต์ที่อ่านง่าย
    plt.rcParams['axes.labelweight'] = 'bold' # ทำให้ตัวหนา

    plt.figure(figsize=(12, 7)) # ปรับขนาดกราฟให้ใหญ่ขึ้นและดูสมส่วน

    # พล็อตกราฟเส้นพร้อมจุด
    plt.plot(sub['ts'], sub['storage'], 
            marker='o', markersize=6, # เพิ่มขนาดจุด
            linestyle='-', linewidth=2.5, # ปรับความหนาของเส้น
            color='#1f77b4', # สีน้ำเงินสวยงาม (matplotlib default blue)
            label='ปริมาณน้ำ') 

    # เพิ่มเส้นแนวโน้ม (Trendline - Optional, ถ้าต้องการ)
    # z = np.polyfit(mdates.date2num(sub['ts']), sub['storage'], 1)
    # p = np.poly1d(z)
    # plt.plot(sub['ts'], p(mdates.date2num(sub['ts'])), color='red', linestyle='--', label='แนวโน้ม')

    # เพิ่มข้อความบนกราฟ (เช่น ค่าล่าสุด)
    if not sub.empty:
        last_value_ts = sub['ts'].iloc[-1]
        last_value_storage = sub['storage'].iloc[-1]
        plt.annotate(f'{last_value_storage:.1f} cms', 
                    xy=(last_value_ts, last_value_storage), 
                    xytext=(5, 5), textcoords='offset points', 
                    ha='left', va='bottom', fontsize=10, color='darkgreen',
                    bbox=dict(boxstyle="round,pad=0.3", fc="yellow", ec="darkgreen", lw=0.5, alpha=0.7))


    plt.title('ระดับน้ำเขื่อนเจ้าพระยา (ย้อนหลัง 7 วัน)', fontsize=18, color='white', pad=20) # สีขาวบนพื้นหลังดำ
    plt.xlabel('วันที่', fontsize=14, color='white') # สีขาว
    plt.ylabel('ปริมาณน้ำ (ลบ.ม./วินาที)', fontsize=14, color='white') # สีขาว

    # ปรับการแสดงผลของแกนวันที่
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M')) # รูปแบบ เดือน/วัน ชั่วโมง:นาที
    plt.gca().xaxis.set_major_locator(mdates.DayLocator()) # แสดงวันหลัก
    plt.gca().xaxis.set_minor_locator(mdates.HourLocator(interval=6)) # แสดงทุก 6 ชั่วโมง
    plt.xticks(rotation=45, ha='right', fontsize=12, color='white') # เอียงฉลากวันที่
    plt.yticks(fontsize=12, color='white') # สีขาว

    plt.tick_params(axis='x', colors='white') # สีของขีดบนแกน X
    plt.tick_params(axis='y', colors='white') # สีของขีดบนแกน Y

    plt.legend(fontsize=12, loc='upper left') # แสดง Legend
    plt.tight_layout() # ปรับระยะห่างให้พอดี

    # ตั้งค่าพื้นหลังของกราฟให้เข้มขึ้น
    plt.gca().set_facecolor('#2d2d2d') # สีเทาเข้ม
    plt.gcf().set_facecolor('#1a1a1a') # สีดำสนิทสำหรับพื้นหลังทั้งหมด

    plt.savefig('chaop_summary.png', dpi=150, bbox_inches='tight') # เพิ่ม dpi เพื่อคุณภาพดีขึ้น
    plt.close()
    last_chaop = sub.iloc[-1] if not sub.empty else None # ใช้ sub แทน df_c สำหรับ last_chaop

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
    # แปลง ts ใน df_w ให้เป็น UTC ก่อนเทียบ แล้วแปลงกลับเป็น TZ เพื่อแสดงผล
    df_w['ts_utc'] = df_w['ts'].dt.tz_localize(TZ, errors='coerce').dt.tz_convert(pytz.UTC)
    upcoming = df_w[df_w['ts_utc'] > now_utc].copy() # ใช้ .copy()

    # เรียงลำดับเวลาที่ใกล้ที่สุด
    upcoming = upcoming.sort_values(by='ts_utc').reset_index(drop=True)

    next_evt = None
    if not upcoming.empty:
        # ใช้ ts เดิมที่อยู่ใน timezone ที่ถูกต้องสำหรับการแสดงผล
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
    lines.append("🌊 เขื่อนเจ้าพระยา: ไม่มีข้อมูล")

if last_inb is not None:
    lines.append(f"🏞️ อินทร์บุรี: {last_inb.level:.2f} ม. ณ {last_inb.ts.strftime('%H:%M')}")
else:
    lines.append("🏞️ อินทร์บุรี: ไม่มีข้อมูล")

if next_evt is not None:
    lines += [
        "",
        f"⛅ ต่อไป: {next_evt['event']} at {next_evt['ts'].strftime('%H:%M')} (value: {next_evt['value']})"
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
    'Authorization': f"Bearer {LINE_TOKEN}",
    'Content-Type':  "application/json"
}
payload = {
    "to": LINE_TARGET,
    "messages": [
        {"type":"text", "text": text},
        {
          "type":"image",
          "originalContentUrl":"https://wata011.github.io/my-water-monitor/chaop_summary.png", # URL ที่แก้ไขแล้ว
          "previewImageUrl":"https://wata011.github.io/my-water-monitor/chaop_summary.png" # URL ที่แก้ไขแล้ว
        }
    ]
}
try:
    resp = requests.post(push_url, headers=headers, json=payload)
    resp.raise_for_status()
    print("Daily summary sent.")
except requests.exceptions.RequestException as e:
    print(f"Failed to send LINE message: {e}")
