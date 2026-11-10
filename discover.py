#!/usr/bin/env python3
"""discover.py - גילוי אוטומטי של כל מה שקיים ב-Claude Code שלך, לרישום במשרד (registry.db).

מה מגלה:
  skills      ~/.claude/skills/*/SKILL.md, סקילים של תוספים (plugins), .claude/skills של תיקיית העסק
  agents      ~/.claude/agents/*.md, .claude/agents של תיקיית העסק
  connections שרתי MCP מ-~/.claude.json, ~/.claude/settings.json, .mcp.json של העסק. נשמרים שם וסוג בלבד:
              לא כתובת, לא פקודה, לא ארגומנטים ולא משתני סביבה (שם יושבים בדרך כלל מפתחות)
  scheduled   משימות מתוזמנות: Routines מקומיים של האפליקציה (~/.claude/scheduled-tasks), systemd user timers,
              crontab, LaunchAgents (מק). מפקודה נשמרים רק שם התוכנה ושם הסקריפט, בלי ארגומנטים
  hooks       hooks מ-settings.json (כמה, ועל אילו אירועים)
  systems     systems.json (רישום ידני של מערכות ודשבורדים)

אידמפוטנטי: הרצה חוזרת מעדכנת last_seen; פריט שנעלם מסומן active=0 (רישום ידני לא נמחק אף פעם).
שימוש: python3 discover.py            (מדפיס מונים)
       python3 discover.py --json     (מדפיס JSON)
משתני סביבה: OFFICE_HOME (ברירת מחדל: הבית), OFFICE_BUSINESS_DIR (תיקיית העסק).
בלי OFFICE_BUSINESS_DIR, תיקיית העסק היא: התיקייה שמעל _infra אם המשרד יושב ב-<עסק>/_infra/<משרד>,
אחרת ~/my-business אם היא קיימת, ואחרת תיקיית המשרד עצמה. אף פעם לא תיקיית הבית ולא תיקייה שמעליה.

registry.db נוצר עם הרשאות לבעלים בלבד (600), ומסד נתונים ישן שנשמרו בו כתובות או פקודות מנוקה בהפעלה הראשונה.
"""
from __future__ import annotations

import json
import os
import plistlib
import re
import shlex
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOME = Path(os.environ.get("OFFICE_HOME") or Path.home())


def _unsafe_workdir(d: Path) -> bool:
    """תיקייה שאסור להריץ ממנה סקיל: שורש הדיסק, תיקיית הבית, או כל תיקייה שמכילה את הבית."""
    try:
        d, home = d.resolve(), HOME.resolve()
    except OSError:
        return True
    return d == d.parent or d == home or d in home.parents


def business_dir() -> Path:
    """תיקיית העסק: ממנה נקראים סקילי הפרויקט ו-.mcp.json, ובה רץ סקיל שמופעל מהדשבורד."""
    env = os.environ.get("OFFICE_BUSINESS_DIR")
    if env:
        d = Path(env).expanduser()
        if d.is_dir() and not _unsafe_workdir(d):
            return d.resolve()
        print(f"  ! OFFICE_BUSINESS_DIR לא מתאים ({env}): לא תיקייה, או תיקיית הבית או מעליה. משתמש בברירת המחדל.", file=sys.stderr)
    if HERE.parent.name == "_infra" and not _unsafe_workdir(HERE.parent.parent):
        return HERE.parent.parent           # <עסק>/_infra/<משרד>
    kit = HOME / "my-business"
    if kit.is_dir() and not _unsafe_workdir(kit):
        return kit.resolve()
    if _unsafe_workdir(HERE):               # המשרד עצמו יושב בתיקיית הבית או מעליה: גם משם לא מריצים
        safe = HERE / "data" / "workdir"
        try:
            safe.mkdir(parents=True, exist_ok=True)
            if not _unsafe_workdir(safe):
                return safe
        except OSError:
            pass
    return HERE                             # אין תיקיית עסק: נשארים בתוך המשרד


BUSINESS = business_dir()
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
    """חיבור MCP: שם וסוג בלבד. כתובת, פקודה, ארגומנטים, כותרות ומשתני סביבה לא נקראים ולא נשמרים,
    כי שם יושבים בדרך כלל טוקנים (בנתיב הכתובת, בפרמטר, או בארגומנט כמו --api-key)."""
    transport = str(cfg.get("type") or ("http" if cfg.get("url") else "stdio"))[:20]
    transport = re.sub(r"[^a-zA-Z0-9_-]", "", transport) or "stdio"
    return item("connection", name, name, transport, scope, "", ["חיבור"], {"transport": transport})


def _split(cmd: str) -> list[str]:
    try:
        return shlex.split(cmd)
    except ValueError:
        return cmd.split()


_SCRIPT_EXT = re.compile(r"\.(py|sh|bash|zsh|js|mjs|cjs|ts|rb|pl|php|bat|cmd|ps1|command)$", re.I)
_PATH_TOKEN = re.compile(r"[\w./\\~$:+-]+")      # נתיב או שם קובץ: בלי רווחים, מירכאות, @ או סימני מעטפת
_SECRET_FLAG = re.compile(r"-{1,2}[\w-]*(key|token|secret|pass|pwd|auth|bearer|cred|sig)[\w-]*", re.I)


def _looks_random(name: str) -> bool:
    """שם ארוך מאוד, או רצף ארוך של אותיות וספרות בלי מפריד: נראה כמו מפתח ולא כמו שם של תוכנה או קובץ."""
    stem = name.rsplit(".", 1)[0]
    if len(stem) >= 32:
        return True
    digits = sum(c.isdigit() for c in stem)
    letters = sum(c.isalpha() for c in stem)
    return len(stem) >= 16 and digits >= 4 and letters >= 4 and not re.search(r"[_.\-]", stem)


def _flat_tokens(tokens: list[str]) -> list[str]:
    """פקודה שלמה שהועברה כמחרוזת אחת במירכאות (sh -c "...") מפורקת שוב למילים. מה שנשאר עם רווח בתוכו נזרק."""
    toks = [str(t) for t in tokens if t]
    for _ in range(3):
        if not any(re.search(r"\s", t) for t in toks):
            break
        toks = [w for t in toks for w in (_split(t) if re.search(r"\s", t) else [t]) if w]
    return [t for t in toks if not re.search(r"\s", t)]


_CRON_FIELD = re.compile(r"^(?:[0-9*/,\-]+|[A-Za-z]{3}(?:[-,][A-Za-z]{3})*)$")
_CRON_KEYWORDS = {"@reboot", "@yearly", "@annually", "@monthly", "@weekly", "@daily", "@midnight", "@hourly"}


def cron_schedule(line: str):
    """(תזמון, פקודה) משורת crontab, או ("", "") אם זו לא שורת משימה.
    התזמון נשמר רק אם הוא באמת תזמון: חמישה שדות של cron או מילת מפתח כמו @daily.
    שורת משתנה סביבה (NAME=value) ושורה שהשדות שלה אינם תזמון לא נשמרות בכלל, כדי שטקסט של פקודה או ערך סודי לא יירשם כ"תזמון"."""
    line = line.strip()
    if not line or line.startswith("#") or re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*=", line):
        return "", ""
    parts = line.split(None, 1)
    if parts[0] in _CRON_KEYWORDS:
        return (parts[0], parts[1]) if len(parts) == 2 else ("", "")
    parts = line.split(None, 5)
    if len(parts) == 6 and all(_CRON_FIELD.match(x) for x in parts[:5]):
        return " ".join(parts[:5]), parts[5]
    return "", ""


def clean_schedule(text: str) -> str:
    """תזמון ישן ממסד קיים: נשאר רק אם הוא תזמון תקין, אחרת ריק."""
    text = (text or "").strip()
    if text in _CRON_KEYWORDS:
        return text
    f = text.split()
    return text if len(f) == 5 and all(_CRON_FIELD.match(x) for x in f) else ""



def command_label(tokens: list[str]) -> str:
    """מפקודה שומרים רק את שם התוכנה ואת שם קובץ הסקריפט שהיא מריצה. התווית נגזרת רק משני אלה, אף פעם לא
    מטקסט של ארגומנט: לא ערך של דגל, לא משתנה סביבה, לא כתובת, ולא מחרוזת שלמה שהועברה במירכאות."""
    toks = _flat_tokens(tokens)
    while toks and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", toks[0]):   # FOO=bar לפני הפקודה
        toks.pop(0)
    if not toks:
        return "command"

    def base(t: str) -> str:
        name = re.sub(r"[^\w.\-]", "", t.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1])[:40]
        return "" if _looks_random(name) else name

    prog = (base(toks[0]) if _PATH_TOKEN.fullmatch(toks[0]) else "") or "command"
    script = ""
    for prev, t in zip(toks, toks[1:]):
        if t.startswith("-") or "=" in t or "://" in t or not _PATH_TOKEN.fullmatch(t) or not _SCRIPT_EXT.search(t):
            continue
        if _SECRET_FLAG.fullmatch(prev):       # ערך של דגל כמו --api-key: לא שם של סקריפט
            continue
        script = base(t)
        break
    return f"{prog} {script}".strip()


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
                        {"kind": "systemd", "next": cols[0][:60] if cols else ""}))
    # crontab: נשמרים התזמון, שם התוכנה ושם הסקריפט. לא הפקודה עצמה
    used: dict[str, int] = {}
    for line in _run(["crontab", "-l"]).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        sched, cmd = cron_schedule(line)
        if sched:
            label = command_label(_split(cmd))
            slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", f"{label}-{sched}").strip("-")[:60] or "cron"
            used[slug] = used.get(slug, 0) + 1
            if used[slug] > 1:
                slug = f"{slug}-{used[slug]}"
            out.append(item("scheduled", f"cron:{slug}", label, f"cron {sched}", "cron", "",
                            ["אוטומציה"], {"kind": "cron", "schedule": sched}))
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
            prog = command_label([str(x) for x in (p.get("ProgramArguments") or [p.get("Program", "")])])
            out.append(item("scheduled", f"launchd:{label}", label, prog, "launchd", f, ["אוטומציה"],
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


def clean_url(url) -> str:
    """כתובת של מערכת: רק http/https, ובלי שם משתמש וסיסמה בתוך הכתובת."""
    url = str(url or "").strip()
    m = re.match(r"^(https?://)([^/?#]*@)?(.*)$", url, re.I | re.S)
    return (m.group(1) + m.group(3))[:500] if m else ""


def clean_port(port):
    try:
        port = int(port)
    except (TypeError, ValueError):
        return None
    return port if 0 < port < 65536 else None


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
                        [s.get("room", "כללי")] + (["דשבורד"] if clean_port(s.get("port")) else []),
                        {"url": clean_url(s.get("url")), "port": clean_port(s.get("port")), "icon": str(s.get("icon", ""))[:8],
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


SCHEMA_VERSION = 4   # 2: חיבורים בשם ובסוג בלבד, משימות בלי פקודה. 3: תווית של משימה רק משם התוכנה ומשם הסקריפט.
                     # 4: תזמון של crontab נשמר רק אם הוא תזמון תקין (גרסה 3 יכלה לשמור שורת סביבה כתזמון), ולכן מנקים שוב


def _owner_only(path: Path, mode: int):
    try:
        os.chmod(path, mode)
    except OSError:
        pass   # ווינדוס, או מערכת קבצים בלי הרשאות: התיקייה כבר בתוך פרופיל המשתמש


def _redact_old(con: sqlite3.Connection):
    """מסד נתונים מגרסה קודמת שמר כתובת או פקודה מלאה של חיבורים ומשימות, ובגרסה 2 תווית של משימה יכלה
    להכיל טקסט של ארגומנט. מנקים את מה שנשמר, פעם אחת בכל שדרוג: השם, המזהה והתיאור של משימות cron ו-launchd
    מוחלפים, והגילוי הבא רושם אותן מחדש לפי הכלל הנוכחי."""
    rows = con.execute("SELECT id, kind, source, meta FROM items WHERE kind IN ('connection','scheduled')").fetchall()
    for r in rows:
        try:
            meta = json.loads(r["meta"] or "{}")
        except ValueError:
            meta = {}
        if not isinstance(meta, dict):
            meta = {}
        if r["kind"] == "connection":
            t = re.sub(r"[^a-zA-Z0-9_-]", "", str(meta.get("transport") or ""))[:20]
            if r["source"] == "register":   # רישום ידני: הטקסט של המשתמש נשאר, שדות של כתובת ופקודה יורדים
                keep = {k: v for k, v in meta.items() if k not in ("target", "url", "command", "args", "env", "env_keys", "headers")}
                con.execute("UPDATE items SET meta=? WHERE id=?", (json.dumps(keep, ensure_ascii=False), r["id"]))
            else:
                con.execute("UPDATE items SET description=?, meta=? WHERE id=?",
                            (t, json.dumps({"transport": t} if t else {}, ensure_ascii=False), r["id"]))
        elif r["source"] in ("cron", "launchd", "systemd"):
            kind = meta.get("kind") or r["source"]
            if r["source"] == "cron":       # השם והמזהה נגזרו מהפקודה עצמה: מוחלפים, והגילוי הבא רושם מחדש
                con.execute("UPDATE items SET slug=?, name='cron', description=?, meta=?, active=0 WHERE id=?",
                            (f"cron:old-{r['id']}", "cron " + clean_schedule(str(meta.get("schedule") or "")),
                             json.dumps({"kind": "cron", "schedule": clean_schedule(str(meta.get("schedule") or ""))}), r["id"]))
            elif r["source"] == "launchd":
                iv = meta.get("interval")
                con.execute("UPDATE items SET description='', meta=? WHERE id=?",
                            (json.dumps({"kind": "launchd", "interval": iv if isinstance(iv, int) else None}), r["id"]))
            else:
                con.execute("UPDATE items SET meta=? WHERE id=?",
                            (json.dumps({"kind": kind, "next": str(meta.get("next") or "")[:60]}), r["id"]))
    con.commit()


def connect() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    _owner_only(DB.parent, 0o700)
    if not DB.exists():   # נוצר מראש עם הרשאות לבעלים בלבד, לפני שנכתב בו משהו
        os.close(os.open(DB, os.O_CREAT | os.O_WRONLY, 0o600))
    _owner_only(DB, 0o600)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA secure_delete=ON")
    con.executescript(SCHEMA)
    if con.execute("PRAGMA user_version").fetchone()[0] < SCHEMA_VERSION:
        _redact_old(con)
        con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        con.commit()
        con.execute("VACUUM")   # כותב את הקובץ מחדש, כדי שהערכים הישנים לא יישארו בדפים פנויים
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
