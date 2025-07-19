#!/usr/bin/env python3
import os
import json
import requests
from datetime import datetime, timedelta
import pytz
import pandas as pd # เพิ่มบรรทัดนี้

# -------- CONFIGURATION --------
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
# LINE_TOKEN          = os.getenv("LINE_CHANNEL_ACCESS_TOKEN") # ไม่ใช้แล้ว
# LINE_TARGET         = os.getenv("LINE_TARGET_ID") # ไม่ใช้แล้ว
WEATHER_LOG_FILE    = "weather_log.csv"
DATA_FILE           = "weather_data.json"

# ENV FLAGS
DRY_RUN = os.getenv("DRY_RUN", "").lower() in ("1", "true")

# ตั้งค่าพิกัดสำหรับ สิงห์บุรี (ตัวอย่าง)
# คุณสามารถหาพิกัดที่แม่นยำได้จาก Google Maps หรือ OpenWeatherMap API docs
LATITUDE  = 14.8966 # ละติจูดของสิงห์บุรี
LONGITUDE = 100.3892 # ลองจิจูดของสิงห์บุรี

# ตั้งค่า timezone
TZ = pytz.timezone('Asia/Bangkok')


def send_line_message(msg: str):
    """
    ฟังก์ชันนี้ถูกปิดการใช้งานแล้ว เพื่อป้องกันการแจ้งเตือนซ้ำซ้อน
    การแจ้งเตือนทั้งหมดจะถูกส่งจาก daily_summary.py เท่านั้น
    """
    print("[INFO] send_line_message ถูกปิดการใช้งานใน weather_forecaster.py")
    # if DRY_RUN:
    #     print("[DRY‑RUN] send_line_message would send:")
    #     print(msg)
    #     return

    # if not (LINE_TOKEN and LINE_TARGET):
    #     print("[ERROR] LINE_TOKEN/LINE_TARGET ไม่ครบ!")
    #     return

    # url = "https://api.line.me/v2/bot/message/push"
    # headers = {
    #     "Authorization": f"Bearer {LINE_TOKEN}",
    #     "Content-Type":  "application/json"
    # }
    # payload = {
    #     "to": LINE_TARGET,
    #     "messages": [{"type": "text", "text": msg}]
    # }
    # resp = requests.post(url, headers=headers, json=payload, timeout=10)
    # if resp.status_code != 200:
    #     print(f"[ERROR] ส่ง LINE ล้มเหลว: {resp.status_code} {resp.text}")


def fetch_weather_forecast():
    """ดึงข้อมูลพยากรณ์อากาศ 5 วัน / 3 ชั่วโมงจาก OpenWeatherMap"""
    if not OPENWEATHER_API_KEY:
        print("[ERROR] OPENWEATHER_API_KEY ไม่ได้ตั้งค่า!")
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
    """Parse ข้อมูลพยากรณ์อากาศเพื่อหาเหตุการณ์สำคัญ"""
    events = []
    if not forecast_data or "list" not in forecast_data:
        return events

    for item in forecast_data["list"]:
        dt_txt = item["dt_txt"] # เวลา UTC
        dt_utc = datetime.strptime(dt_txt, "%Y-%m-%d %H:%M:%S").replace(tzinfo=pytz.utc)
        dt_local = dt_utc.astimezone(TZ) # แปลงเป็นเวลาท้องถิ่น

        # ตรวจสอบเหตุการณ์ฝนตก (rain) หรือพายุ (thunderstorm)
        weather_main = item["weather"][0]["main"].lower()
        weather_desc = item["weather"][0]["description"].lower()

        event_type = None
        event_value = None

        if "rain" in weather_main or "drizzle" in weather_main:
            event_type = "ฝนตก"
            event_value = item.get("rain", {}).get("3h", 0) # ปริมาณฝนใน 3 ชั่วโมง
        elif "thunderstorm" in weather_main:
            event_type = "พายุฝนฟ้าคะนอง"
            event_value = item.get("rain", {}).get("3h", 0)
        elif "clouds" in weather_main and "overcast clouds" in weather_desc:
            event_type = "เมฆครึ้ม"
            event_value = item["clouds"]["all"] # เปอร์เซ็นต์เมฆ
        elif "clear" in weather_main:
            event_type = "ท้องฟ้าแจ่มใส"
            event_value = item["clouds"]["all"] # เปอร์เซ็นต์เมฆ (ควรเป็น 0)

        if event_type:
            events.append({
                "timestamp": dt_local,
                "event_type": event_type,
                "value": event_value
            })
    return events


def main():
    print("=== เริ่ม weather_forecaster ===")

    forecast_data = fetch_weather_forecast()
    if not forecast_data:
        print("[ERROR] ไม่สามารถดึงข้อมูลพยากรณ์อากาศได้, ข้ามการประมวลผล")
        # บันทึก N/A ลง log เพื่อให้ summary_report ไม่ขึ้น NaN
        TZ_TH = pytz.timezone('Asia/Bangkok')
        now_th = datetime.now(TZ_TH)
        with open(WEATHER_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"{now_th.isoformat()},N/A,N/A\n")
        return

    events = parse_weather_data(forecast_data)

    # บันทึกข้อมูลสภาพอากาศลง weather_log.csv เสมอ
    with open(WEATHER_LOG_FILE, 'a', encoding='utf-8') as f:
        for event in events:
            f.write(f"{event['timestamp'].isoformat()},{event['event_type']},{event['value']}\n")
    print(f"[INFO] อัปเดต {WEATHER_LOG_FILE} เรียบร้อย ({len(events)} เหตุการณ์)")

    # ส่วนนี้เป็น logic การแจ้งเตือนที่ถูกปิดการใช้งานแล้ว
    # last_alert_time = None
    # if os.path.exists(DATA_FILE):
    #     with open(DATA_FILE, "r", encoding="utf-8") as f:
    #         saved_data = json.load(f)
    #         if "last_alert_time" in saved_data:
    #             last_alert_time = datetime.fromisoformat(saved_data["last_alert_time"]).astimezone(TZ)

    # now_local = datetime.now(TZ)
    # alert_sent = False

    # for event in events:
    #     # แจ้งเตือนเฉพาะเหตุการณ์ในอนาคตอันใกล้ (เช่น 24 ชั่วโมงข้างหน้า)
    #     # และยังไม่เคยแจ้งเตือนเหตุการณ์นี้มาก่อน
    #     if event["timestamp"] > now_local and \
    #        (event["timestamp"] - now_local) <= timedelta(hours=24) and \
    #        (last_alert_time is None or event["timestamp"] > last_alert_time):
    #         
    #         msg = (
    #             f"📢 พยากรณ์อากาศ: {event['event_type']} "
    #             f"(ค่า: {event['value']})\n"
    #             f"🕒 เวลา: {event['timestamp'].strftime('%d/%m/%Y %H:%M น.')}"
    #         )
    #         send_line_message(msg)
    #         alert_sent = True
    #         break # แจ้งเตือนแค่เหตุการณ์แรกที่สำคัญที่สุด

    # if alert_sent:
    #     with open(DATA_FILE, "w", encoding="utf-8") as f:
    #         json.dump({"last_alert_time": events[0]["timestamp"].isoformat()}, f, ensure_ascii=False, indent=2)

    print("=== จบ weather_forecaster ===")


if __name__ == "__main__":
    main()
