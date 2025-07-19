name: Weather Alert

on:
  schedule:
    - cron: '45 0 * * *' # รันทุกวันเวลา 00:45 UTC (07:45 น. ICT)
  workflow_dispatch: {}

jobs:
  check_weather:
    runs-on: ubuntu-latest
    permissions:
      contents: write # เพิ่มสิทธิ์ write เพื่อให้ commit ได้
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0 # ดึงประวัติทั้งหมด เพื่อป้องกันปัญหา merge
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.x'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run Weather Forecaster Script
        env:
          OPENWEATHER_API_KEY: ${{ secrets.OPENWEATHER_API_KEY }}
          LINE_CHANNEL_ACCESS_TOKEN: ${{ secrets.LINE_CHANNEL_ACCESS_TOKEN }} # แม้จะปิดในโค้ด Python แต่ env นี้ก็ต้องมี
          LINE_TARGET_ID: ${{ secrets.LINE_TARGET_ID }} # เช่นกัน
        run: python weather_forecaster.py
      - name: Commit and push weather_log.csv
        uses: EndBug/add-and-commit@v9 # ใช้ Action สำเร็จรูปสำหรับการ Commit และ Push
        with:
          author_name: "github-actions[bot]"
          author_email: "github-actions[bot]@users.noreply.github.com"
          message: "chore: Update weather log"
          add: "weather_log.csv"
          push: true
