#!/usr/bin/env bash
# office_hook.sh - hook של Claude Code (PostToolUse על Write|Edit): אם נכתב קובץ של סוכן / סקיל / משימה
# מתוזמנת - מריץ גילוי מחדש כדי שהמשרד יתעדכן לבד. חוק הזהב, בלי לזכור אותו.
# הגדרה ב-~/.claude/settings.json:  {"hooks":{"PostToolUse":[{"matcher":"Write|Edit","hooks":[{"type":"command","command":"<נתיב>/office_hook.sh","args":[]}]}]}}
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
# בווינדוס python3 הוא לעתים קיצור דרך לחנות ולא Python אמיתי: בודקים שהוא באמת רץ
PY=""
for c in python3 python py; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys' >/dev/null 2>&1; then PY="$c"; break; fi
done
[ -z "$PY" ] && exit 0
input=$(cat)
path=$(printf '%s' "$input" | "$PY" -c 'import sys,json
try: print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))
except Exception: print("")')
case "$path" in
  *"/.claude/agents/"*|*"/.claude/skills/"*|*"/.claude/scheduled-tasks/"*|*"/systems.json"|*"/.mcp.json"|*"/.claude.json")
    (cd "$HERE" && "$PY" discover.py >/dev/null 2>&1 &)
    ;;
esac
exit 0
