#!/usr/bin/env python3
import os
import json
import requests
from datetime import datetime, timedelta, timezone
import pytz
import pandas as pd

# -------- CONFIGURATION --------
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
WEATHER_LOG_FILE    = "weather_log.csv"
DATA_FILE           = "weather_data.json"

# ENV FLAGS
DRY_RUN = os.getenv("DRY_RUN", "").lower() in ("1", "true")

# ตั้งค่าพิกัดสำหรับ อินทร์บุรี จ.สิงห์บุรี
LATITUDE  = 14.8966
LONGITUDE = 100.3892
LOCATION_NAME = 'อินทร์บุรี จ.สิงห์บุรี'

# ตั้งค่า timezone
TZ = pytz.timezone('Asia/Bangkok')

# Thresholds
RAIN_CONF_THRESHOLD = 0.3
MIN_RAIN_MM         = 5.0
HEAT_THRESHOLD      = 35.0


def send_line_message(msg: str):
    print("[INFO] send_line_message ถูกปิดการใช้งานใน weather_forecaster.py")


def fetch_weather_forecast():
    if not OPENWEATHER_API_KEY:
        print("[ERROR] OPENWEATHER_API_KEY ไม่ได้ตั้งค่า! ไม่สามารถดึงข้อมูลพยากรณ์อากาศได้.")
        return None

    url = (
        f"http://api.openweathermap.org/data/2.5/forecast?"
        f"lat={LATITUDE}&lon={LONGITUDE}&appid={OPENWEATHER_API_KEY}&units=metric"
    )
    try:
        print(f"[DEBUG] ดึงข้อมูลจาก OpenWeatherMap: {url}")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] ไม่สามารถดึงข้อมูลพยากรณ์อากาศได้: {e}")
        return None


def parse_weather_data(forecast_data):
    events_list = [] # เปลี่ยนชื่อตัวแปรเป็น events_list เพื่อไม่ให้ชนกับ events ทั่วไป
    if not forecast_data or "list" not in forecast_data:
        print("[WARN] forecast_data ไม่มีข้อมูลหรือไม่มี 'list'.")
        return events_list

    # ล้าง weather_log.csv ก่อนบันทึกข้อมูลพยากรณ์ใหม่
    if os.path.exists(WEATHER_LOG_FILE):
        try:
            os.remove(WEATHER_LOG_FILE)
            print(f"[INFO] ลบไฟล์ {WEATHER_LOG_FILE} เดิมทิ้งก่อนบันทึกใหม่")
        except OSError as e:
            print(f"[ERROR] ไม่สามารถลบไฟล์ {WEATHER_LOG_FILE} ได้: {e}")

    with open(WEATHER_LOG_FILE, 'a', encoding='utf-8') as f:
        for item in forecast_data["list"]:
            dt_txt = item["dt_txt"]

            # แปลง string เป็น datetime object ก่อน
            dt_utc = datetime.strptime(dt_txt, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            dt_local = dt_utc.astimezone(TZ) # แปลงเป็นเวลาท้องถิ่น

            weather_main = item["weather"][0]["main"].lower() if "weather" in item and item["weather"] else 'n/a'
            weather_desc = item["weather"][0]["description"].lower() if "weather" in item and item["weather"] else 'n/a'

            temp_max = item.get('main', {}).get('temp_max', None)

            event_type = None
            event_value = None

            if "rain" in weather_main or "drizzle" in weather_main:
                event_type = "ฝนตก"
                event_value = item.get("rain", {}).get("3h", 0.0)
            elif "thunderstorm" in weather_main:
                event_type = "พายุฝนฟ้าคะนอง"
                event_value = item.get("rain", {}).get("3h", 0.0)
            elif "clear" in weather_main:
                event_type = "ท้องฟ้าแจ่มใส"
                event_value = item.get("clouds", {}).get("all", 0)
            elif "clouds" in weather_main:
                event_type = "มีเมฆ"
                event_value = item.get("clouds", {}).get("all", 0)

            # บันทึกเหตุการณ์สภาพอากาศหลัก (ถ้ามี)
            if event_type:
                f.write(f"{dt_local.isoformat()},{event_type},{event_value}\n")

            # ถ้ามีอุณหภูมิร้อนจัด ก็บันทึกเพิ่ม (อาจจะบันทึกซ้ำเวลาได้ถ้ามีหลายเหตุการณ์ในเวลาเดียวกัน)
            if temp_max is not None and temp_max >= HEAT_THRESHOLD:
                f.write(f"{dt_local.isoformat()},อากาศร้อนจัด,{temp_max}\n")

    # อ่านข้อมูลกลับมาเพื่อส่งคืน (ถ้ามีข้อมูล)
    try:
        df_log = pd.read_csv(WEATHER_LOG_FILE, names=['ts', 'event_type', 'value'], parse_dates=['ts'])
        # ตรวจสอบว่าคอลัมน์ ts มี timezone หรือไม่ ก่อนที่จะใช้ tz_localize
        if df_log['ts'].dt.tz is None:
            # ใช้ .dt.tz_localize(TZ, ambiguous='infer', nonexistent='shift_forward')
            # หรือกำหนด timezone ตั้งแต่ตอน read_csv ถ้าทำได้ง่ายกว่า
            # สำหรับตอนนี้ ขอให้แน่ใจว่า ts_utc ใน summary_report.py จัดการถูกต้อง
            df_log['ts'] = df_log['ts'].dt.tz_localize(TZ, ambiguous=True) # ใช้ ambiguous=True
        return df_log.to_dict('records') # ส่งคืนเป็น list ของ dicts
    except Exception as e:
        print(f"[ERROR] ไม่สามารถอ่านข้อมูลจาก {WEATHER_LOG_FILE} หลังบันทึก: {e}")
        return []


def main():
    print("=== เริ่ม weather_forecaster ===")

    forecast_data = fetch_weather_forecast()
    if not forecast_data:
        print("[ERROR] ไม่สามารถดึงข้อมูลพยากรณ์อากาศได้, ข้ามการประมวลผล")
        # ถ้ามีข้อผิดพลาดในการดึงข้อมูล จะล้างไฟล์และบันทึก N/A เพื่อให้ summary_report ทราบว่ามีปัญหา
        if os.path.exists(WEATHER_LOG_FILE):
            os.remove(WEATHER_LOG_FILE) # ลบไฟล์เก่า
        TZ_TH = pytz.timezone('Asia/Bangkok')
        now_th = datetime.now(TZ_TH)
        with open(WEATHER_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"{now_th.isoformat()},N/A,N/A\n") # บันทึก N/A
        print(f"[INFO] อัปเดต {WEATHER_LOG_FILE} เรียบร้อย (มีข้อผิดพลาดในการดึงข้อมูล)")
        return

    events = parse_weather_data(forecast_data)

    # ไม่มีการแจ้งเตือน LINE ตรงนี้แล้ว

    print("=== จบ weather_forecaster ===")


if __name__ == "__main__":
    main()
