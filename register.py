#!/usr/bin/env python3
"""register.py - רישום ידני במשרד. חוק הזהב: סוכן / סקיל / אוטומציה / מערכת חדשים = רישום. מה שלא רשום - לא קיים.

discover.py מגלה לבד את מה שחי בתוך Claude Code. הסקריפט הזה משלים את מה שאין לו גילוי אוטומטי:
  --kind system     דשבורד או מערכת חיצונית (CRM, גיליון, אתר)         (או: שורה ב-systems.json)
  --kind scheduled  אוטומציה שרצה במקום שהגילוי לא רואה (שרת אחר, Zapier)
  --kind agent / skill   סוכן או סקיל שחיים במקום לא סטנדרטי

דוגמאות:
  python3 register.py --kind system --slug crm --name "ה-CRM שלי" --url https://crm.example.com --room לקוחות --icon 📇
  python3 register.py --kind scheduled --slug weekly-report --name "דוח שבועי" --description "ראשון 08:00" --tags אוטומציה,דוחות
  python3 register.py --list
  python3 register.py --remove system crm
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from discover import connect, now  # noqa: E402

KINDS = ["system", "scheduled", "agent", "skill", "connection"]


def main() -> None:
    p = argparse.ArgumentParser(description="רישום ידני במשרד")
    p.add_argument("--kind", choices=KINDS)
    p.add_argument("--slug", help="מזהה באנגלית, אותיות קטנות ומקפים")
    p.add_argument("--name", help="שם לתצוגה, בעברית")
    p.add_argument("--description", default="")
    p.add_argument("--url", default="")
    p.add_argument("--port", type=int, default=None, help="לדשבורד מקומי - המשרד יבדוק אם הוא חי")
    p.add_argument("--room", default="כללי", help="קבוצה בתצוגה: כללי / כספים / לקוחות / שיווק / תפעול")
    p.add_argument("--icon", default="")
    p.add_argument("--tags", default="", help="תגיות מופרדות בפסיק")
    p.add_argument("--list", action="store_true")
    p.add_argument("--remove", nargs=2, metavar=("KIND", "SLUG"))
    a = p.parse_args()

    con = connect()
    try:
        if a.list:
            rows = con.execute("SELECT kind, slug, name, source, active FROM items ORDER BY kind, name").fetchall()
            for r in rows:
                flag = "" if r["active"] else " (לא פעיל)"
                print(f"{r['kind']:11s} {r['slug']:32s} {r['name']}  [{r['source']}]{flag}")
            print(f"סה\"כ {len(rows)}")
            return
        if a.remove:
            con.execute("DELETE FROM items WHERE kind=? AND slug=?", tuple(a.remove))
            con.commit()
            print("הוסר:", *a.remove)
            return
        if not (a.kind and a.slug and a.name):
            p.error("--kind, --slug ו---name חובה (או --list / --remove)")
        tags = [t.strip() for t in a.tags.split(",") if t.strip()] or ([a.room] if a.kind == "system" else [])
        meta = {"url": a.url, "port": a.port, "icon": a.icon, "room": a.room}
        ts = now()
        con.execute(
            """INSERT INTO items(kind, slug, name, description, source, path, tags, meta, first_seen, last_seen, active)
               VALUES(?,?,?,?,'register','',?,?,?,?,1)
               ON CONFLICT(kind, slug) DO UPDATE SET name=excluded.name, description=excluded.description,
                 tags=excluded.tags, meta=excluded.meta, last_seen=excluded.last_seen, active=1, source='register'""",
            (a.kind, a.slug, a.name, a.description, json.dumps(tags, ensure_ascii=False),
             json.dumps(meta, ensure_ascii=False), ts, ts))
        con.commit()
        print(f"נרשם: {a.kind} / {a.slug} - {a.name}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
