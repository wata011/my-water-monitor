#!/usr/bin/env python3
import os
import json
import requests
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from datetime import datetime
import pytz
import pandas as pd # เพิ่มบรรทัดนี้สำหรับ pd.notna

# -------- CONFIGURATION --------
DATA_FILE         = "inburi_bridge_data.json"
DEFAULT_THRESHOLD = 0.1   # เมตร (10 ซม.)
INBURI_LOG_FILE   = "inburi_log.csv"

# ENV FLAGS
DRY_RUN        = os.getenv("DRY_RUN", "").lower() in ("1", "true")
USE_LOCAL_HTML = os.getenv("USE_LOCAL_HTML", "").lower() in ("1", "true")
LOCAL_HTML     = os.getenv("LOCAL_HTML_PATH", "page.html")

# Read threshold from env (meters)
_raw = os.getenv("NOTIFICATION_THRESHOLD_M", "")
try:
    NOTIFICATION_THRESHOLD = float(_raw) if _raw else DEFAULT_THRESHOLD
except ValueError:
    print(f"[WARN] แปลง NOTIFICATION_THRESHOLD_M='{_raw}' ไม่สำเร็จ → ใช้ default={DEFAULT_THRESHOLD:.2f} m")
    NOTIFICATION_THRESHOLD = DEFAULT_THRESHOLD

LINE_TOKEN  = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_TARGET = os.getenv("LINE_TARGET_ID")


def send_line_message(msg: str):
    """ส่งข้อความผ่าน LINE (หรือ Dry‑run)"""
    if DRY_RUN:
        print("[DRY‑RUN] send_line_message would send:")
        print(msg)
        return

    if not (LINE_TOKEN and LINE_TARGET):
        print("[ERROR] LINE_TOKEN/LINE_TARGET ไม่ครบ!")
        return

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type":  "application/json"
    }
    payload = {
        "to": LINE_TARGET,
        "messages": [{"type": "text", "text": msg}]
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=10)
    if resp.status_code != 200:
        print(f"[ERROR] ส่ง LINE ล้มเหลว: {resp.status_code} {resp.text}")


def fetch_rendered_html(url: str, timeout: int = 15) -> str:
    """โหลดหน้าเว็บด้วย Selenium หรือจากไฟล์ mock"""
    if USE_LOCAL_HTML:
        print(f"[INFO] USE_LOCAL_HTML=TRUE, อ่านจากไฟล์ '{LOCAL_HTML}'")
        with open(LOCAL_HTML, "r", encoding="utf-8") as f:
            return f.read()

    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=opts
    )
    driver.get(url)
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "th[scope='row']"))
        )
    except Exception:
        print("[WARN] Selenium timeout รอ table JS โหลด")
    html = driver.page_source
    driver.quit()
    return html


def get_water_data():
    """Parse ข้อมูลสถานี 'อินทร์บุรี' จาก HTML"""
    print("[DEBUG] ดึง HTML จากเว็บ...")
    html = fetch_rendered_html("https://singburi.thaiwater.net/wl")
    print(f"[DEBUG] HTML length = {len(html)} chars")

    soup = BeautifulSoup(html, "html.parser")
    for th in soup.select("th[scope='row']"):
        if "อินทร์บุรี" in th.get_text(strip=True):
            tr   = th.find_parent("tr")
            cols = tr.find_all("td")

            # ดึงข้อมูลและแปลงเป็น float/string
            water_level_str = cols[1].get_text(strip=True)
            bank_level_str  = cols[2].get_text(strip=True)
            status_str      = tr.select_one("span.badge").get_text(strip=True)
            report_time_str = cols[6].get_text(strip=True)

            # พยายามแปลงเป็น float หากมีค่า
            water_level = float(water_level_str) if water_level_str else None
            bank_level  = float(bank_level_str) if bank_level_str else None

            below_bank = None
            if water_level is not None and bank_level is not None:
                below_bank = round(bank_level - water_level, 2)

            print(f"[DEBUG] Parsed water={water_level}, bank={bank_level}, status={status_str}, below={below_bank}, time={report_time_str}")
            return {
                "station_name": "อินทร์บุรี",
                "water_level":   water_level,
                "bank_level":    bank_level,
                "status":        status_str,
                "below_bank":    below_bank,
                "time":          report_time_str,
            }
    print("[ERROR] ไม่พบข้อมูลสถานี อินทร์บุรี ใน HTML")
    return None


def main():
    print("=== เริ่ม inburi_bridge_alert ===")
    print(f"[INFO] Using NOTIFICATION_THRESHOLD = {NOTIFICATION_THRESHOLD:.2f} m")

    # โหลดข้อมูลเก่า (state)
    last_data = {}
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            last_data = json.load(f)
        print(f"[DEBUG] last_data = {last_data}")

    data = get_water_data()
    if not data:
        # หากดึงข้อมูลไม่ได้ ก็ยังคงบันทึกข้อผิดพลาดใน log
        TZ_TH = pytz.timezone('Asia/Bangkok') # ใช้ TZ_TH เพื่อความชัดเจน
        now_th = datetime.now(TZ_TH)
        # บันทึก N/A สำหรับค่าที่ไม่มี
        with open(INBURI_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"{now_th.isoformat()},N/A,N/A,N/A,N/A,N/A\n") # บันทึก N/A ครบ 6 คอลัมน์
        print(f"[INFO] อัปเดต {INBURI_LOG_FILE} เรียบร้อย (มีข้อผิดพลาดในการดึงข้อมูล)")
        return

    # ตรวจสอบว่ามีค่า water_level ที่ถูกต้องหรือไม่
    current_water_level = data.get("water_level")
    if current_water_level is None or pd.isna(current_water_level):
        print("WARN: ไม่สามารถดึงค่า water_level ที่ถูกต้องได้จากหน้าเว็บ")
        TZ_TH = pytz.timezone('Asia/Bangkok')
        now_th = datetime.now(TZ_TH)
        # บันทึก N/A สำหรับค่าที่ไม่มี แม้จะดึง data ได้ แต่ water_level เป็น None/NaN
        water_level_val = data.get('water_level', 'N/A')
        bank_level_val = data.get('bank_level', 'N/A')
        status_val = data.get('status', 'N/A')
        below_bank_val = data.get('below_bank', 'N/A')
        time_val = data.get('time', 'N/A')
        with open(INBURI_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"{now_th.isoformat()},{water_level_val},{bank_level_val},{status_val},{below_bank_val},{time_val}\n")
        print(f"[INFO] อัปเดต {INBURI_LOG_FILE} เรียบร้อย (water_level ไม่ถูกต้อง)")
        return


    prev = last_data.get("water_level")
    if prev is None:
        print("[INFO] ไม่มีข้อมูลเก่า, บันทึกแต่ไม่แจ้งครั้งแรก")
        need_alert = False
        diff       = 0.0
        direction  = ""
    else:
        diff = current_water_level - prev # ใช้ current_water_level
        print(f"[DEBUG] prev={prev:.2f}, new={current_water_level:.2f}, diff={diff:.2f}")
        if abs(diff) >= NOTIFICATION_THRESHOLD:
            direction = "⬆️" if diff > 0 else "⬇️"
            need_alert = True
        else:
            print("[INFO] diff น้อยกว่า threshold, ไม่แจ้ง")
            need_alert = False

    # ส่วนนี้จะถูกข้ามหากต้องการแค่รายงานสรุป (เราปิด river_alert.yml ไปแล้ว)
    # แต่ถ้าเปิด river_alert.yml และต้องการแจ้งเตือนแยก ก็จะทำงาน
    if need_alert:
        msg = (
            f"📢 แจ้งระดับน้ำ {direction}{abs(diff):.2f} ม. (อินทร์บุรี)\n"
            "══════════════════\n"
            f"🌊 ระดับน้ำ     : {data['water_level']} ม.\n"
            f"🏞️ ระดับตลิ่ง    : {data['bank_level']} ม.\n"
            f"🚦 สถานะ       : {data['status']}\n"
            f"📐 ห่างจากตลิ่ง : {data['below_bank']} ม.\n"
            "───────────────\n"
            f"🕒 เวลา        : {data['time']}"
        )
        send_line_message(msg)
    else:
        print("[INFO] ไม่มีการแจ้งเตือนในรอบนี้")

    # บันทึกค่าระดับน้ำปัจจุบันลง inburi_log.csv เสมอ
    TZ_TH = pytz.timezone('Asia/Bangkok')
    now_th = datetime.now(TZ_TH)

    water_level_val = data.get('water_level', 'N/A')
    bank_level_val = data.get('bank_level', 'N/A')
    status_val = data.get('status', 'N/A')
    below_bank_val = data.get('below_bank', 'N/A')
    time_val = data.get('time', 'N/A')

    with open(INBURI_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{now_th.isoformat()},{water_level_val},{bank_level_val},{status_val},{below_bank_val},{time_val}\n")
    print(f"[INFO] อัปเดต {INBURI_LOG_FILE} เรียบร้อย")

    # บันทึก state เสมอ
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("=== จบ inburi_bridge_alert ===")


if __name__ == "__main__":
    main()
