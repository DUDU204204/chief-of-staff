#!/usr/bin/env bash
# setup.sh - התקנה ראשונה של "המשרד שלי": בדיקות, יצירת data/, גילוי ראשון.
set -uo pipefail
cd "$(dirname "$0")"
PORT="${OFFICE_PORT:-17090}"

echo "המשרד שלי - התקנה"
echo "-------------------"

# 1. Python
if command -v python3 >/dev/null 2>&1; then PY=python3; elif command -v python >/dev/null 2>&1; then PY=python; else
  echo "✗ לא נמצא Python. התקן Python 3.10+ מ-python.org ונסה שוב."; exit 1; fi
ver=$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
echo "✓ Python $ver ($PY)"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' || {
  echo "✗ נדרש Python 3.10 ומעלה (יש $ver)."; exit 1; }

# 2. Claude Code - נחוץ לגילוי ולהפעלת סקילים
if command -v claude >/dev/null 2>&1; then
  echo "✓ Claude Code: $(command -v claude)"
else
  echo "  ! claude לא נמצא ב-PATH. הגילוי עדיין יעבוד (הוא קורא קבצים), אבל כפתור 'הפעל' לא."
  echo "    התקנה: curl -fsSL https://claude.ai/install.sh | bash"
fi

# 3. תיקיות
mkdir -p data data/runs
echo "✓ data/"

# 4. systems.json - העתקה מהתבנית בפעם הראשונה
if [ ! -f systems.json ]; then
  cp systems.json.example systems.json
  echo "✓ systems.json נוצר מהתבנית - ערוך אותו עם המערכות שלך (רק שמות וכתובות, בלי סיסמאות)"
else
  echo "✓ systems.json קיים"
fi

# 5. הרשאות הרצה
chmod +x office_hook.sh discover.py register.py server.py 2>/dev/null || true

# 6. הפורט
if command -v ss >/dev/null 2>&1 && ss -tln 2>/dev/null | grep -q ":$PORT "; then
  echo "  ! הפורט $PORT תפוס. הרץ עם: OFFICE_PORT=$((PORT+1)) $PY server.py"
elif command -v lsof >/dev/null 2>&1 && lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "  ! הפורט $PORT תפוס. הרץ עם: OFFICE_PORT=$((PORT+1)) $PY server.py"
else
  echo "✓ פורט $PORT פנוי"
fi

# 7. גילוי ראשון
echo
"$PY" discover.py || { echo "✗ הגילוי נכשל. הרץ ידנית: $PY discover.py"; exit 1; }

cat <<EOF

-------------------
מוכן. הצעדים הבאים:

  1. $PY server.py            ואז בדפדפן: http://127.0.0.1:$PORT
  2. ערוך את systems.json עם המערכות של העסק שלך, ולחץ "רענן" בדשבורד
  3. רישום אוטומטי של כל סקיל/סוכן חדש - הוסף את ה-hook ל-~/.claude/settings.json
     (ההוראות ב-README, בסעיף "רישום אוטומטי")

EOF
