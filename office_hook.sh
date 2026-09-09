#!/usr/bin/env bash
# office_hook.sh - hook של Claude Code (PostToolUse על Write|Edit): אם נכתב קובץ של סוכן / סקיל / משימה
# מתוזמנת - מריץ גילוי מחדש כדי שהמשרד יתעדכן לבד. חוק הזהב, בלי לזכור אותו.
# הגדרה ב-~/.claude/settings.json:  {"hooks":{"PostToolUse":[{"matcher":"Write|Edit","hooks":[{"type":"command","command":"<נתיב>/office_hook.sh","args":[]}]}]}}
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
input=$(cat)
path=$(printf '%s' "$input" | python3 -c 'import sys,json
try: print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))
except Exception: print("")')
case "$path" in
  *"/.claude/agents/"*|*"/.claude/skills/"*|*"/.claude/scheduled-tasks/"*|*"/systems.json"|*"/.mcp.json"|*"/.claude.json")
    (cd "$HERE" && python3 discover.py >/dev/null 2>&1 &)
    ;;
esac
exit 0
