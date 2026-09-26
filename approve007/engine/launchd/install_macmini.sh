#!/bin/bash
# ติดตั้ง Approve007 บน Mac mini (CTO) — รันจาก clone ของ repo:  bash approve007/engine/launchd/install_macmini.sh
# 1) ก๊อป engine + app ไปไว้ All_on_Cloud/AutoExport/scripts/approve007/ (ที่เก็บโค้ดรันตาม HANDOVER ข้อ 10)
# 2) เขียน md5 ของทุกไฟล์ (Drive เคย sync byte เพี้ยนจน SyntaxError — ตรวจ md5 ก่อนไล่แก้โค้ด)
# 3) ติดตั้ง launchd 06:30 → PRE-FLIGHT → build รอบแรก
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"          # approve007/engine
APPROOT="$(dirname "$HERE")"
AOC="${APPROVE007_ALL_ON_CLOUD:-$HOME/ไดรฟ์ของฉัน (007skn0777@gmail.com)/All_on_Cloud}"
[ -d "$AOC/AutoExport" ] || { echo "❌ ไม่เจอ $AOC/AutoExport — ตั้ง APPROVE007_ALL_ON_CLOUD แล้วรันใหม่ (ห้ามเดา path)"; exit 1; }
DEST="$AOC/AutoExport/scripts/approve007"
mkdir -p "$DEST/engine/config" "$DEST/app" "$DEST/_backup"
if [ -f "$DEST/engine/build.py" ]; then
  tar -czf "$DEST/_backup/approve007.$(date +%y%m%d%H%M).tgz" -C "$DEST" engine app
fi
cp "$HERE"/*.py "$DEST/engine/"
cp "$HERE"/config/*.json "$DEST/engine/config/"
cp "$APPROOT"/app/approve007.html "$DEST/app/"
( cd "$DEST" && find engine app -type f \( -name '*.py' -o -name '*.json' -o -name '*.html' \) -exec md5 -r {} \; > MD5SUMS )
echo "✅ ก๊อปโค้ดไป $DEST (MD5SUMS เขียนแล้ว)"

python3 -c "import openpyxl" 2>/dev/null || pip3 install --user openpyxl
PLIST="$HOME/Library/LaunchAgents/com.007metals.approve007.plist"
sed -e "s|__ENGINE__|$DEST/engine|" -e "s|__AOC__|$AOC|" "$HERE/launchd/com.007metals.approve007.plist" > "$PLIST"
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "✅ launchd ติดตั้งแล้ว (ทุกวัน 06:30) → $PLIST"

# เฟส 1: ส่งข้อมูลขึ้น API ทุก 15 นาที — ต้องมี token เดียวกับ APPROVE007_PUSH_TOKEN บน Vercel
if [ -n "${APPROVE007_PUSH_TOKEN:-}" ]; then
  PPLIST="$HOME/Library/LaunchAgents/com.007metals.approve007.push.plist"
  sed -e "s|__ENGINE__|$DEST/engine|" -e "s|__AOC__|$AOC|" -e "s|__TOKEN__|$APPROVE007_PUSH_TOKEN|" \
      "$HERE/launchd/com.007metals.approve007.push.plist" > "$PPLIST"
  chmod 600 "$PPLIST"                              # token อยู่ในเครื่อง Mac mini เท่านั้น ไม่ลง Drive/GitHub
  launchctl unload "$PPLIST" 2>/dev/null || true
  launchctl load "$PPLIST"
  echo "✅ launchd push ทุก 15 นาที ติดตั้งแล้ว → $PPLIST"
else
  echo "ℹ️ ข้ามเฟส 1 (push ขึ้น API) — รันใหม่พร้อม APPROVE007_PUSH_TOKEN=... เมื่อ deploy API แล้ว"
fi

export APPROVE007_ALL_ON_CLOUD="$AOC"
python3 "$DEST/engine/build.py" preflight
python3 "$DEST/engine/build.py" --inspect
python3 "$DEST/engine/build.py"
python3 "$DEST/engine/build.py" verify || echo "⚠️ VERIFY ยังไม่ผ่าน — แก้ config/families.json ตามผล --inspect แล้วรันใหม่ (ห้ามเปิดทดลองจนกว่าจะผ่าน)"
