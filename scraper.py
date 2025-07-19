import os
import re
import requests
import json
from datetime import datetime, timedelta
import pytz

# --- ค่าคงที่ ---
URL = 'https://tiwrm.hii.or.th/DATA/REPORT/php/chart/chaopraya/small/chaopraya.php'
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_TARGET_ID = os.environ.get('LINE_TARGET_ID')
TIMEZONE_THAILAND = pytz.timezone('Asia/Bangkok')
HISTORICAL_LOG_FILE = 'historical_log.csv'
LAST_DATA_FILE = 'last_data.txt'


def get_water_data(timeout=30):
    """
    ดึงข้อมูลจาก JSON ที่ฝังอยู่ใน JavaScript ของหน้าเว็บ
    ซึ่งเป็นวิธีที่เสถียรและแม่นยำที่สุด
    """
    try:
        headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache'
}
        response = requests.get(URL, headers=headers, timeout=timeout)
        response.raise_for_status()
        response.encoding = 'utf-8' # ระบุ encoding เป็น utf-8
        
        # 1. ค้นหาข้อมูล JSON ที่อยู่ในตัวแปรชื่อ "json_data" จากเนื้อหาของหน้าเว็บ
        match = re.search(r'var json_data = (\[.*\]);', response.text)
        
        if not match:
            print("Error: ไม่พบข้อมูล JSON (ตัวแปร json_data) ในหน้าเว็บ")
            return None
            
        # 2. แปลงข้อความ JSON ที่หาเจอให้กลายเป็น Dictionary ของ Python
        json_string = match.group(1)
        data = json.loads(json_string)
        
        # 3. ดึงค่าที่ต้องการจากโครงสร้าง JSON โดยตรง
        # data[0] -> itc_water -> C13 -> storage
        water_storage = data[0]['itc_water']['C13']['storage']
        
        if water_storage:
            return f"{water_storage} cms"

    except requests.exceptions.RequestException as e:
        print(f"เกิดข้อผิดพลาดในการดึง URL: {e}")
        return None
    except (KeyError, IndexError):
        print("Error: ไม่พบ Key 'C13' หรือ 'storage' ในโครงสร้าง JSON")
        return None
    except json.JSONDecodeError:
        print("Error: ไม่สามารถแปลงข้อมูลที่ได้มาเป็น JSON")
        return None
    except Exception as e:
        print(f"เกิดข้อผิดพลาดที่ไม่คาดคิด: {e}")
        return None

    print("Error: ไม่พบข้อมูลปริมาณน้ำในรูปแบบที่คาดไว้")
    return None


def get_historical_data(target_date):
    if not os.path.exists(HISTORICAL_LOG_FILE):
        return None
    start = target_date - timedelta(hours=12)
    end = target_date + timedelta(hours=12)
    best, best_diff = None, timedelta.max
    with open(HISTORICAL_LOG_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                ts, val = line.strip().split(",", 1)
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = TIMEZONE_THAILAND.localize(dt)
                diff = abs(target_date - dt)
                if start <= dt <= end and diff < best_diff:
                    best_diff, best = diff, val
            except ValueError:
                continue
    return best


def append_to_historical_log(now, data):
    with open(HISTORICAL_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{now.isoformat()},{data}\n")


def send_line_message(message):
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_TARGET_ID:
        print("Missing LINE credentials.")
        return
    url = 'https://api.line.me/v2/bot/message/push'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {LINE_CHANNEL_ACCESS_TOKEN}'
    }
    payload = {
        'to': LINE_TARGET_ID,
        'messages': [{'type': 'text', 'text': message}]
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        resp.raise_for_status()
        print("ส่งข้อความ LINE สำเร็จ:", resp.status_code)
    except Exception as e:
        print("ส่งข้อความ LINE ไม่สำเร็จ:", e)


# วางโค้ดนี้ทับฟังก์ชัน main() เดิมในไฟล์ scraper.py
def main():
    # อ่านค่าปัจจุบันและค่าเก่า
    last = ''
    if os.path.exists(LAST_DATA_FILE):
        last = open(LAST_DATA_FILE, 'r', encoding='utf-8').read().strip()

    current = get_water_data()
    if not current:
        print("ไม่สามารถดึงค่าปัจจุบันได้ จึงไม่มีการแจ้งเตือน")
        return

    print(f"ค่าปัจจุบัน: {current}, ค่าล่าสุด: {last}")

    # --- เพิ่มเงื่อนไขนี้เข้าไป ---
    if current != last:
        print("ตรวจพบการเปลี่ยนแปลง! กำลังส่งการแจ้งเตือน...")
        now_th = datetime.now(TIMEZONE_THAILAND)

        # เตรียมข้อความสำหรับข้อมูลย้อนหลัง (ถ้ามี)
        hist = get_historical_data(now_th - timedelta(days=365))
        hist_str = ""
        if hist:
            hist_date_str = (now_th - timedelta(days=365)).strftime('%d/%m/%Y')
            hist_str = f"\n\n📈 เทียบปีที่แล้ว ({hist_date_str}): {hist}"

        # จัดรูปแบบข้อความใหม่ให้อ่านง่าย
        msg = (
            f"🌊 **แจ้งเตือนปริมาณน้ำ เขื่อนเจ้าพระยา**\n"
            f"อ.สรรพยา จ.ชัยนาท\n"
            f"━━━━━━━━\n"
            f"💧 **ปริมาณน้ำปัจจุบัน**\n"
            f"╰─> {current}\n\n"
            f"⬅️ **ค่าเดิมล่าสุด**\n"
            f"╰─> {last or 'ไม่มีข้อมูลเดิม'}"
            f"{hist_str}\n"
            f"━━━━━━━━\n"
            f"🗓️ {now_th.strftime('%d/%m/%Y %H:%M น.')}"
        )
        
        send_line_message(msg)

        # อัปเดตไฟล์เก็บข้อมูล
        with open(LAST_DATA_FILE, 'w', encoding='utf-8') as f:
            f.write(current)
    else:
        print("ข้อมูลไม่เปลี่ยนแปลง ข้ามการแจ้งเตือน")

    # ส่วนนี้จะทำงานทุกครั้งเพื่อเก็บ log ไม่ว่าจะแจ้งเตือนหรือไม่
    now_th = datetime.now(TIMEZONE_THAILAND)
    append_to_historical_log(now_th, current)
    print("อัปเดต historical log เรียบร้อย")

if __name__ == "__main__":
    main()
