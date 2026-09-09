#!/usr/bin/env python3
"""server.py - "המשרד שלי": דשבורד-על ל-Claude Code של בעל עסק. Python בספרייה הסטנדרטית בלבד.

מה יש:
  /                     הדשבורד (index.html)
  GET  /api/state       כל הפריטים הפעילים (סקילים, סוכנים, חיבורים, משימות מתוזמנות, hooks, מערכות) + מונים
                        + ריצות אחרונות + תצפיות פתוחות + בדיקת חיים לדשבורדים עם פורט
  POST /api/refresh     גילוי מחדש (discover.py)
  POST /api/run         {"skill": "<slug>", "args": "..."}  -> מריץ claude -p "/skill args" ברקע, מחזיר id
  GET  /api/runs        20 הריצות האחרונות · GET /api/runs/<id> -> סטטוס + זנב הלוג
  POST /api/observe     {"source","severity","title","body"} -> תצפית (סוכנים ואוטומציות מדווחים לכאן)
  POST /api/observations/<id>/ack
  POST /api/register    רישום ידני (אותם שדות כמו register.py)

מאזין רק ל-127.0.0.1. משתני סביבה: OFFICE_PORT (17090), OFFICE_HOME, OFFICE_BUSINESS_DIR, CLAUDE_BIN (claude).
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import discover  # noqa: E402

PORT = int(os.environ.get("OFFICE_PORT", "17090"))
CLAUDE_BIN = os.environ.get("CLAUDE_BIN") or shutil.which("claude") or "claude"
RUNS_DIR = HERE / "data" / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)
INDEX = HERE / "index.html"
PROBE_TTL = 20
_probe_cache: dict[int, tuple[float, bool]] = {}
_lock = threading.Lock()


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def port_alive(port: int) -> bool:
    t = time.time()
    hit = _probe_cache.get(port)
    if hit and t - hit[0] < PROBE_TTL:
        return hit[1]
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            ok = True
    except OSError:
        ok = False
    _probe_cache[port] = (t, ok)
    return ok


def state() -> dict:
    con = discover.connect()
    try:
        items = []
        for r in con.execute("SELECT * FROM items WHERE active=1 ORDER BY kind, name"):
            d = dict(r)
            d["tags"] = json.loads(d.get("tags") or "[]")
            d["meta"] = json.loads(d.get("meta") or "{}")
            if d["kind"] == "system" and d["meta"].get("port"):
                d["alive"] = port_alive(int(d["meta"]["port"]))
            items.append(d)
        counts = {k: v for k, v in con.execute("SELECT kind, COUNT(*) FROM items WHERE active=1 GROUP BY kind")}
        runs = [dict(r) for r in con.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT 20")]
        obs = [dict(r) for r in con.execute("SELECT * FROM observations WHERE acknowledged=0 ORDER BY ts DESC LIMIT 50")]
        last = con.execute("SELECT ts FROM discoveries ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        con.close()
    return {"ts": now(), "items": items, "counts": counts, "runs": runs, "observations": obs,
            "last_discovery": last["ts"] if last else None, "business_dir": str(discover.BUSINESS),
            "home": str(discover.HOME)}


# ---------------------------------------------------------------- runs (skill launcher)
def start_run(skill: str, args: str) -> dict:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    log = RUNS_DIR / f"{run_id}.log"
    prompt = f"/{skill} {args}".strip()
    con = discover.connect()
    con.execute("INSERT INTO runs(id, skill, prompt, started_at, status, log_path) VALUES(?,?,?,?,?,?)",
                (run_id, skill, prompt, now(), "running", str(log)))
    con.commit()
    con.close()

    def worker():
        env = os.environ.copy()
        env["PATH"] = "/usr/local/bin:/opt/homebrew/bin:" + env.get("PATH", "/usr/bin:/bin")
        with open(log, "w", encoding="utf-8") as fh:
            fh.write(f"$ {prompt}\n\n")
            fh.flush()
            try:
                proc = subprocess.run([CLAUDE_BIN, "-p", prompt, "--permission-mode", "acceptEdits"],
                                      cwd=str(discover.BUSINESS), stdout=fh, stderr=subprocess.STDOUT,
                                      env=env, timeout=3600, text=True)
                code, status = proc.returncode, ("done" if proc.returncode == 0 else "failed")
            except subprocess.TimeoutExpired:
                code, status = -1, "timeout"
                fh.write("\n[timeout after 60 min]\n")
            except OSError as e:
                code, status = -2, "failed"
                fh.write(f"\n[cannot start claude: {e}]\n")
        c = discover.connect()
        c.execute("UPDATE runs SET finished_at=?, status=?, exit_code=? WHERE id=?", (now(), status, code, run_id))
        c.commit()
        c.close()

    threading.Thread(target=worker, daemon=True).start()
    return {"id": run_id, "prompt": prompt, "status": "running"}


def run_detail(run_id: str) -> dict | None:
    con = discover.connect()
    row = con.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    con.close()
    if not row:
        return None
    d = dict(row)
    try:
        text = Path(d["log_path"]).read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    d["log"] = text[-20000:]
    return d


# ---------------------------------------------------------------- http
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # שקט - רק שגיאות
        if args and str(args[1]).startswith(("4", "5")):
            super().log_message(fmt, *args)

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except ValueError:
            return {}

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            body = INDEX.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif u.path == "/api/state":
            self._json(state())
        elif u.path == "/api/runs":
            self._json(state()["runs"])
        elif u.path.startswith("/api/runs/"):
            d = run_detail(u.path.rsplit("/", 1)[-1])
            self._json(d if d else {"error": "not found"}, 200 if d else 404)
        elif u.path == "/api/health":
            self._json({"ok": True, "ts": now(), "port": PORT})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        body = self._body()
        if u.path == "/api/refresh":
            with _lock:
                counts = discover.discover()
            self._json({"ok": True, "counts": counts, "ts": now()})
        elif u.path == "/api/run":
            skill = (body.get("skill") or "").strip()
            if not skill:
                return self._json({"error": "skill required"}, 400)
            self._json(start_run(skill, (body.get("args") or "").strip()))
        elif u.path == "/api/observe":
            con = discover.connect()
            con.execute("INSERT INTO observations(ts, source, severity, title, body) VALUES(?,?,?,?,?)",
                        (now(), body.get("source", "?")[:80], body.get("severity", "info")[:20],
                         body.get("title", "")[:200], body.get("body", "")[:4000]))
            con.commit()
            con.close()
            self._json({"ok": True})
        elif u.path.startswith("/api/observations/") and u.path.endswith("/ack"):
            oid = u.path.split("/")[3]
            con = discover.connect()
            con.execute("UPDATE observations SET acknowledged=1 WHERE id=?", (oid,))
            con.commit()
            con.close()
            self._json({"ok": True})
        elif u.path == "/api/register":
            kind, slug, name = body.get("kind"), body.get("slug"), body.get("name")
            if kind not in ("system", "scheduled", "agent", "skill", "connection") or not slug or not name:
                return self._json({"error": "kind/slug/name required"}, 400)
            con = discover.connect()
            ts = now()
            con.execute(
                """INSERT INTO items(kind, slug, name, description, source, path, tags, meta, first_seen, last_seen, active)
                   VALUES(?,?,?,?,'register','',?,?,?,?,1)
                   ON CONFLICT(kind, slug) DO UPDATE SET name=excluded.name, description=excluded.description,
                     tags=excluded.tags, meta=excluded.meta, last_seen=excluded.last_seen, active=1, source='register'""",
                (kind, slug, name, body.get("description", ""), json.dumps(body.get("tags") or [], ensure_ascii=False),
                 json.dumps(body.get("meta") or {}, ensure_ascii=False), ts, ts))
            con.commit()
            con.close()
            self._json({"ok": True})
        else:
            self._json({"error": "not found"}, 404)


def main():
    if not (HERE / "data" / "registry.db").exists() or "--discover" in sys.argv:
        print("גילוי ראשון...")
        discover.discover()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"המשרד שלי רץ: http://127.0.0.1:{PORT}   (עסק: {discover.BUSINESS})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
