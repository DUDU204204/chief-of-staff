#!/usr/bin/env python3
"""discover.py - גילוי אוטומטי של כל מה שקיים ב-Claude Code שלך, לרישום במשרד (registry.db).

מה מגלה:
  skills      ~/.claude/skills/*/SKILL.md, סקילים של תוספים (plugins), .claude/skills של תיקיית העסק
  agents      ~/.claude/agents/*.md, .claude/agents של תיקיית העסק
  connections שרתי MCP מ-~/.claude.json, ~/.claude/settings.json, .mcp.json של העסק (שמות בלבד - לא מפתחות)
  scheduled   משימות מתוזמנות: Routines מקומיים של האפליקציה (~/.claude/scheduled-tasks), systemd user timers,
              crontab, LaunchAgents (מק)
  hooks       hooks מ-settings.json (כמה, ועל אילו אירועים)
  systems     systems.json (רישום ידני של מערכות ודשבורדים)

אידמפוטנטי: הרצה חוזרת מעדכנת last_seen; פריט שנעלם מסומן active=0 (רישום ידני לא נמחק אף פעם).
שימוש: python3 discover.py            (מדפיס מונים)
       python3 discover.py --json     (מדפיס JSON)
משתני סביבה: OFFICE_HOME (ברירת מחדל: הבית), OFFICE_BUSINESS_DIR (ברירת מחדל: שתי תיקיות מעל הקובץ הזה)
"""
from __future__ import annotations

import json
import os
import plistlib
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOME = Path(os.environ.get("OFFICE_HOME") or Path.home())
BUSINESS = Path(os.environ.get("OFFICE_BUSINESS_DIR") or HERE.parent.parent)
DB = HERE / "data" / "registry.db"
SYSTEMS_JSON = HERE / "systems.json"

# רעש של מערכת ההפעלה שלא מעניין אף אחד במשרד
NOISE = ("systemd-", "dbus", "xdg-", "gvfs", "snap.", "apt-", "fwupd", "man-db", "logrotate", "e2scrub",
         "motd", "ua-", "update-notifier", "com.apple.", "pipewire", "wireplumber", "at-spi", "tracker")

# תיוג אוטומטי לפי מילים בשם/בתיאור (עברית + אנגלית)
TAG_RULES = {
    "קופי": ["קופי", "copy", "כותרת", "headline", "ניסוח"],
    "ניוזלטר": ["ניוזלטר", "newsletter", "מייל", "email"],
    "שיווק": ["שיווק", "marketing", "מודע", "ads", "קמפיין", "campaign", "דף נחיתה", "landing"],
    "מכירות": ["מכיר", "sales", "הצעת מחיר", "quote", "proposal"],
    "תמלול": ["תמלול", "transcri", "whisper"],
    "וידאו": ["וידאו", "video", "ריל", "reel", "כתוביות", "caption"],
    "כספים": ["חשבונ", "invoice", "כספ", "finance", "בנק", "bank", "תזרים"],
    "לקוחות": ["לקוח", "client", "crm", "ליווי"],
    "אוטומציה": ["אוטומצ", "automation", "cron", "timer", "מתוזמן", "schedule"],
    "דוחות": ["דוח", "report", "סיכום", "summary", "דשבורד", "dashboard"],
    "עיצוב": ["עיצוב", "design", "תמונה", "image", "frontend"],
    "אבטחה": ["אבטח", "security", "secret", "סוד"],
    "ניהול": ["ניהול", "משימ", "task", "פגישה", "meeting", "יומן", "calendar"],
}


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def tags_for(*texts: str) -> list[str]:
    blob = " ".join(t or "" for t in texts).lower()
    return [tag for tag, words in TAG_RULES.items() if any(w in blob for w in words)]


def frontmatter(path: Path) -> tuple[dict, str]:
    """קורא frontmatter פשוט (key: value) מקובץ Markdown. מחזיר (מטא, גוף)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}, ""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta = {}
    for line in parts[1].splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, parts[2]


def item(kind, slug, name, description="", source="", path="", tags=None, meta=None):
    return {"kind": kind, "slug": slug, "name": name or slug, "description": (description or "")[:600],
            "source": source, "path": str(path) if path else "", "tags": tags or tags_for(name, description),
            "meta": meta or {}}


# ---------------------------------------------------------------- scanners
def scan_skills() -> list[dict]:
    out = []
    roots = [(HOME / ".claude" / "skills", "user"), (BUSINESS / ".claude" / "skills", "project")]
    for root, source in roots:
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            f = d / "SKILL.md"
            if d.is_dir() and f.exists():
                meta, _ = frontmatter(f)
                out.append(item("skill", meta.get("name") or d.name, meta.get("name") or d.name,
                                meta.get("description"), source, f,
                                meta={"invocable": meta.get("user-invocable", "")}))
    # סקילים של תוספים (plugins): הם יושבים בתוך ה-cache, בעומק משתנה
    cache = HOME / ".claude" / "plugins" / "cache"
    if cache.is_dir():
        for f in cache.glob("*/*/*/skills/*/SKILL.md"):
            meta, _ = frontmatter(f)
            plugin = f.parents[2].name
            name = meta.get("name") or f.parent.name
            out.append(item("skill", f"{plugin}:{name}", name, meta.get("description"), f"plugin:{plugin}", f))
        for f in cache.glob("*/*/skills/*/SKILL.md"):
            meta, _ = frontmatter(f)
            plugin = f.parents[2].name
            name = meta.get("name") or f.parent.name
            out.append(item("skill", f"{plugin}:{name}", name, meta.get("description"), f"plugin:{plugin}", f))
    return out


def scan_agents() -> list[dict]:
    out = []
    for root, source in [(HOME / ".claude" / "agents", "user"), (BUSINESS / ".claude" / "agents", "project")]:
        if not root.is_dir():
            continue
        for f in sorted(root.glob("*.md")):
            meta, _ = frontmatter(f)
            out.append(item("agent", meta.get("name") or f.stem, meta.get("name") or f.stem, meta.get("description"),
                            source, f, meta={"tools": meta.get("tools", ""), "model": meta.get("model", "")}))
    return out


def _mcp_entry(name: str, cfg: dict, scope: str) -> dict:
    transport = cfg.get("type") or ("http" if cfg.get("url") else "stdio")
    target = cfg.get("url") or " ".join([cfg.get("command", "")] + list(cfg.get("args") or []))
    # רק שמות של משתני סביבה - לעולם לא הערכים
    env_keys = sorted((cfg.get("env") or {}).keys())
    return item("connection", name, name, f"{transport} · {target[:80]}", scope, "", ["חיבור"],
                {"transport": transport, "target": target[:200], "env_keys": env_keys})


def scan_connections() -> list[dict]:
    out, seen = [], set()

    def add(servers: dict, scope: str):
        for name, cfg in (servers or {}).items():
            if isinstance(cfg, dict) and name not in seen:
                seen.add(name)
                out.append(_mcp_entry(name, cfg, scope))

    cj = HOME / ".claude.json"
    if cj.exists():
        try:
            data = json.loads(cj.read_text(encoding="utf-8"))
            add(data.get("mcpServers"), "user")
            for proj, pdata in (data.get("projects") or {}).items():
                if isinstance(pdata, dict):
                    add(pdata.get("mcpServers"), f"project:{Path(proj).name}")
        except (OSError, ValueError):
            pass
    st = HOME / ".claude" / "settings.json"
    if st.exists():
        try:
            add(json.loads(st.read_text(encoding="utf-8")).get("mcpServers"), "settings")
        except (OSError, ValueError):
            pass
    pm = BUSINESS / ".mcp.json"
    if pm.exists():
        try:
            add(json.loads(pm.read_text(encoding="utf-8")).get("mcpServers"), "business")
        except (OSError, ValueError):
            pass
    return out


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def scan_scheduled() -> list[dict]:
    out = []
    # Routines מקומיים של אפליקציית Claude Code Desktop
    st = HOME / ".claude" / "scheduled-tasks"
    if st.is_dir():
        for d in sorted(st.iterdir()):
            f = d / "SKILL.md"
            if f.exists():
                meta, _ = frontmatter(f)
                out.append(item("scheduled", f"routine:{d.name}", meta.get("name") or d.name, meta.get("description"),
                                "desktop-routine", f, ["אוטומציה"], {"kind": "routine"}))
    # systemd user timers (לינוקס)
    txt = _run(["systemctl", "--user", "list-timers", "--all", "--no-pager", "--no-legend"])
    for line in txt.splitlines():
        m = re.search(r"(\S+\.timer)\s+(\S+\.service)", line)
        if not m or m.group(1).startswith(NOISE):
            continue
        cols = re.split(r"\s{2,}", line.strip())
        out.append(item("scheduled", f"timer:{m.group(1)}", m.group(1).replace(".timer", ""),
                        f"systemd timer → {m.group(2)}", "systemd", "", ["אוטומציה"],
                        {"kind": "systemd", "next": cols[0] if cols else "", "raw": line.strip()[:200]}))
    # crontab
    for line in _run(["crontab", "-l"]).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 5)
        if len(parts) == 6:
            slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", parts[5])[:40].strip("-") or "cron"
            out.append(item("scheduled", f"cron:{slug}", parts[5][:60], f"cron {' '.join(parts[:5])}", "cron", "",
                            ["אוטומציה"], {"kind": "cron", "schedule": " ".join(parts[:5]), "command": parts[5][:200]}))
    # LaunchAgents (מק)
    la = HOME / "Library" / "LaunchAgents"
    if la.is_dir():
        for f in sorted(la.glob("*.plist")):
            if f.name.startswith(NOISE):
                continue
            try:
                p = plistlib.loads(f.read_bytes())
            except Exception:  # noqa: BLE001
                continue
            label = p.get("Label", f.stem)
            prog = " ".join(p.get("ProgramArguments") or [p.get("Program", "")])
            out.append(item("scheduled", f"launchd:{label}", label, prog[:120], "launchd", f, ["אוטומציה"],
                            {"kind": "launchd", "interval": p.get("StartInterval"), "calendar": str(p.get("StartCalendarInterval", ""))[:120]}))
    return out


def scan_hooks() -> list[dict]:
    out = []
    for f, scope in [(HOME / ".claude" / "settings.json", "user"), (BUSINESS / ".claude" / "settings.json", "project")]:
        if not f.exists():
            continue
        try:
            hooks = json.loads(f.read_text(encoding="utf-8")).get("hooks") or {}
        except (OSError, ValueError):
            continue
        for event, entries in hooks.items():
            n = sum(len(e.get("hooks") or []) for e in entries if isinstance(e, dict))
            matchers = ", ".join(str(e.get("matcher", "*")) for e in entries if isinstance(e, dict))
            out.append(item("hook", f"{scope}:{event}", event, f"{n} hooks · {matchers[:80]}", scope, f, ["אוטומציה"]))
    return out


def scan_systems() -> list[dict]:
    out = []
    if not SYSTEMS_JSON.exists():
        return out
    try:
        data = json.loads(SYSTEMS_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"  ! systems.json לא תקין: {e}", file=sys.stderr)
        return out
    for s in data.get("systems") or []:
        if not isinstance(s, dict) or not s.get("slug"):
            continue
        out.append(item("system", s["slug"], s.get("name") or s["slug"], s.get("description", ""), "manual", "",
                        [s.get("room", "כללי")] + (["דשבורד"] if s.get("port") else []),
                        {"url": s.get("url", ""), "port": s.get("port"), "icon": s.get("icon", ""),
                         "room": s.get("room", "כללי"), "category": s.get("category", "")}))
    return out


# ---------------------------------------------------------------- db
SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, slug TEXT NOT NULL, name TEXT NOT NULL, description TEXT,
  source TEXT, path TEXT, tags TEXT, meta TEXT, first_seen TEXT, last_seen TEXT, active INTEGER DEFAULT 1,
  UNIQUE(kind, slug));
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, skill TEXT, prompt TEXT, started_at TEXT, finished_at TEXT, status TEXT, log_path TEXT, exit_code INTEGER);
CREATE TABLE IF NOT EXISTS observations (
  id INTEGER PRIMARY KEY, ts TEXT, source TEXT, severity TEXT, title TEXT, body TEXT, acknowledged INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS discoveries (id INTEGER PRIMARY KEY, ts TEXT, counts TEXT);
"""


def connect() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def upsert(con: sqlite3.Connection, items: list[dict]) -> dict:
    ts = now()
    seen = set()
    for it in items:
        seen.add((it["kind"], it["slug"]))
        con.execute(
            """INSERT INTO items(kind, slug, name, description, source, path, tags, meta, first_seen, last_seen, active)
               VALUES(?,?,?,?,?,?,?,?,?,?,1)
               ON CONFLICT(kind, slug) DO UPDATE SET name=excluded.name, description=excluded.description,
                 source=excluded.source, path=excluded.path, tags=excluded.tags, meta=excluded.meta,
                 last_seen=excluded.last_seen, active=1""",
            (it["kind"], it["slug"], it["name"], it["description"], it["source"], it["path"],
             json.dumps(it["tags"], ensure_ascii=False), json.dumps(it["meta"], ensure_ascii=False), ts, ts))
    # מה שלא נראה הפעם - לא פעיל (רישום ידני דרך register.py נשאר)
    for row in con.execute("SELECT kind, slug, source FROM items WHERE active=1").fetchall():
        if (row["kind"], row["slug"]) not in seen and row["source"] != "register":
            con.execute("UPDATE items SET active=0 WHERE kind=? AND slug=?", (row["kind"], row["slug"]))
    counts = {k: v for k, v in con.execute("SELECT kind, COUNT(*) FROM items WHERE active=1 GROUP BY kind")}
    con.execute("INSERT INTO discoveries(ts, counts) VALUES(?,?)", (ts, json.dumps(counts, ensure_ascii=False)))
    con.commit()
    return counts


def discover() -> dict:
    items = scan_skills() + scan_agents() + scan_connections() + scan_scheduled() + scan_hooks() + scan_systems()
    con = connect()
    try:
        return upsert(con, items)
    finally:
        con.close()


if __name__ == "__main__":
    counts = discover()
    if "--json" in sys.argv:
        print(json.dumps(counts, ensure_ascii=False))
    else:
        labels = {"skill": "סקילים", "agent": "סוכנים", "connection": "חיבורים", "scheduled": "משימות מתוזמנות",
                  "hook": "hooks", "system": "מערכות"}
        print(f"גילוי הושלם ({now()}), בית: {HOME}, עסק: {BUSINESS}")
        for k, label in labels.items():
            print(f"  {label:18s} {counts.get(k, 0)}")
