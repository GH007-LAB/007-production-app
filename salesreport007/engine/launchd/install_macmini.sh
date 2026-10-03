#!/bin/bash
# ติดตั้งรายงานขายอัตโนมัติบน Mac mini — รันจาก clone ของ repo:  bash salesreport007/engine/launchd/install_macmini.sh
# ก๊อปโค้ด (+ dbf.py/paths.py ตัวเดียวกับ approve007) → MD5SUMS → launchd 08:30–16:30 → preflight → inspect + inspect-pay เมื่อวาน
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"          # salesreport007/engine
REPO="$(cd "$HERE/../.." && pwd)"
AOC="${APPROVE007_ALL_ON_CLOUD:-$HOME/ไดรฟ์ของฉัน (007skn0777@gmail.com)/All_on_Cloud}"
[ -d "$AOC/AutoExport" ] || { echo "❌ ไม่เจอ $AOC/AutoExport — ตั้ง APPROVE007_ALL_ON_CLOUD แล้วรันใหม่ (ห้ามเดา path)"; exit 1; }
DEST="$AOC/AutoExport/scripts/salesreport007"
mkdir -p "$DEST/engine/config" "$DEST/_backup"
if [ -f "$DEST/engine/salesreport.py" ]; then
  tar -czf "$DEST/_backup/salesreport007.$(date +%y%m%d%H%M).tgz" -C "$DEST" engine
fi
cp "$HERE"/salesreport.py "$HERE"/calc.py "$REPO"/approve007/engine/dbf.py "$REPO"/approve007/engine/paths.py "$DEST/engine/"
# sources.json: ถ้ามีของเดิมที่ CTO แก้ตาม Step 0 แล้ว ห้ามทับ
[ -f "$DEST/engine/config/sources.json" ] || cp "$HERE"/config/sources.json "$DEST/engine/config/"
( cd "$DEST" && find engine -type f \( -name '*.py' -o -name '*.json' \) -exec md5 -r {} \; > MD5SUMS )
mkdir -p "$AOC/AutoExport/sales_report"/{BK,SKN,PPS}
echo "✅ ก๊อปโค้ดไป $DEST"

PLIST="$HOME/Library/LaunchAgents/com.007metals.salesreport.plist"
sed -e "s|__ENGINE__|$DEST/engine|" -e "s|__AOC__|$AOC|" "$HERE/launchd/com.007metals.salesreport.plist" > "$PLIST"
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "✅ launchd ติดตั้งแล้ว (08:30 · 10:30 · 12:30 · 14:30 · 15:55 · 16:30 ทุกวัน) → $PLIST"

export APPROVE007_ALL_ON_CLOUD="$AOC"
python3 "$DEST/engine/salesreport.py" preflight
python3 "$DEST/engine/salesreport.py" inspect
python3 "$DEST/engine/salesreport.py" inspect-pay
echo "👉 Step 0: เทียบยอดข้างบน (เมื่อวาน) กับฟอร์มเดิม · หาฟิลด์เงินสด/โอนของ RE จาก inspect-pay แล้วใส่ใน sources.json ก่อนเปิดใช้"
