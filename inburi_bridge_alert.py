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
import pandas as pd

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


def send_line_message(msg: str):
    print("[INFO] send_line_message ถูกปิดการใช้งานใน inburi_bridge_alert.py")


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
    opts.add_argument("--window-size=1920,1080") # เพิ่มขนาดหน้าต่าง
    opts.add_argument("--disable-gpu") # สำหรับบางสภาพแวดล้อม

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=opts
    )
    driver.get(url)
    try:
        # รอจนกว่าตารางจะโหลดสมบูรณ์ โดยดูจาก element ที่คาดว่าจะอยู่ในตาราง
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table.table-striped tbody tr"))
        )
        # อาจจะรออีกนิดเพื่อให้ JS ทำงานเสร็จ
        import time
        time.sleep(2) 
    except Exception as e:
        print(f"[WARN] Selenium timeout หรือไม่พบ element ที่คาดหวัง: {e}")
    html = driver.page_source
    driver.quit()
    return html


def get_water_data():
    """Parse ข้อมูลสถานี 'อินทร์บุรี' จาก HTML"""
    print("[DEBUG] ดึง HTML จากเว็บ...")
    html = fetch_rendered_html("https://singburi.thaiwater.net/wl")
    print(f"[DEBUG] HTML length = {len(html)} chars")

    soup = BeautifulSoup(html, "html.parser")

    # ค้นหาแถวที่มี "อินทร์บุรี"
    target_row = None
    for th in soup.select("th[scope='row']"):
        if "อินทร์บุรี" in th.get_text(strip=True):
            target_row = th.find_parent("tr")
            break

    if not target_row:
        print("[ERROR] ไม่พบข้อมูลสถานี อินทร์บุรี ใน HTML")
        return None

    cols = target_row.find_all("td")

    # ตรวจสอบจำนวนคอลัมน์
    if len(cols) < 7: # ควรมีอย่างน้อย 7 คอลัมน์ (0-6)
        print(f"[ERROR] จำนวนคอลัมน์ไม่เพียงพอสำหรับสถานีอินทร์บุรี: พบ {len(cols)} คอลัมน์")
        return None

    # ดึงข้อมูลและแปลงเป็น float/string
    # ใช้ .get_text(strip=True) เพื่อลบช่องว่าง
    water_level_str = cols[1].get_text(strip=True) if len(cols) > 1 else 'N/A'
    bank_level_str  = cols[2].get_text(strip=True) if len(cols) > 2 else 'N/A'
    status_span = cols[3].select_one("span.badge") if len(cols) > 3 else None # สถานะมักจะอยู่ใน cols[3]
    status_str = status_span.get_text(strip=True) if status_span else (cols[3].get_text(strip=True) if len(cols) > 3 else 'N/A')
    report_time_str = cols[6].get_text(strip=True) if len(cols) > 6 else 'N/A'

    # พยายามแปลงเป็น float หากมีค่า
    water_level = float(water_level_str) if water_level_str and water_level_str.replace('.', '', 1).isdigit() else None
    bank_level  = float(bank_level_str) if bank_level_str and bank_level_str.replace('.', '', 1).isdigit() else None

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
        TZ_TH = pytz.timezone('Asia/Bangkok')
        now_th = datetime.now(TZ_TH)
        with open(INBURI_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"{now_th.isoformat()},N/A,N/A,N/A,N/A,N/A\n")
        print(f"[INFO] อัปเดต {INBURI_LOG_FILE} เรียบร้อย (มีข้อผิดพลาดในการดึงข้อมูล)")
        return

    # ตรวจสอบว่ามีค่า water_level ที่ถูกต้องหรือไม่
    current_water_level = data.get("water_level")
    if current_water_level is None or pd.isna(current_water_level):
        print("WARN: ไม่สามารถดึงค่า water_level ที่ถูกต้องได้จากหน้าเว็บ")
        TZ_TH = pytz.timezone('Asia/Bangkok')
        now_th = datetime.now(TZ_TH)
        water_level_val = data.get('water_level', 'N/A')
        bank_level_val = data.get('bank_level', 'N/A')
        status_val = data.get('status', 'N/A')
        below_bank_val = data.get('below_bank', 'N/A')
        time_val = data.get('time', 'N/A')
        with open(INBURI_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"{now_th.isoformat()},{water_level_val},{bank_level_val},{status_val},{below_bank_val},{time_val}\n")
        print(f"[INFO] อัปเดต {INBURI_LOG_FILE} เรียบร้อย (water_level ไม่ถูกต้อง)")
        return

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
