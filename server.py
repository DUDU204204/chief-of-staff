#!/usr/bin/env python3
"""Chief of Staff — HTTP API + Visual Office static server.

Serves:
  GET  /                              → office.html (visual office)
  GET  /static/*                      → static assets
  GET  /api/systems                   → list systems
  GET  /api/agents                    → list agents
  GET  /api/credentials               → list credentials
  GET  /api/dashboards                → list dashboards
  GET  /api/processes                 → list processes
  GET  /api/observations              → list observations (open by default)
  GET  /api/rooms                     → room layout
  GET  /api/memory                    → agent memory
  GET  /api/state                     → ONE snapshot for the office to render
  POST /api/observations/{id}/ack     → acknowledge observation
  POST /api/observations/{id}/resolve → resolve observation
  POST /api/refresh                   → re-run discover.py
  POST /api/open                      → run open_command for a dashboard
  GET  /api/chat                      → recent chat history
  POST /api/chat                      → send a message (logged; agent runs separately)
  GET  /api/agents/messages           → recent agent-to-agent activity (war room)
  POST /api/agents/message            → log a new handoff/ask/report
"""
from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import db  # noqa: E402

import os
PORT = int(os.environ.get("COS_PORT", "17090"))
OFFICE_HTML = ROOT / "office.html"
STATIC_DIR = ROOT / "static"


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def port_listening(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    try:
        ok = s.connect_ex(("127.0.0.1", port)) == 0
        return ok
    finally:
        s.close()


def update_live_statuses() -> None:
    """Cheap health check — refresh status for each system with a port."""
    rows = db.query_all(
        "SELECT id, slug, port, url FROM systems WHERE port IS NOT NULL"
    )
    for r in rows:
        if r["port"] and port_listening(r["port"]):
            status, note = "green", f"port {r['port']} alive"
        else:
            status, note = "yellow", f"port {r['port']} not listening"
        with db.cursor() as (cur, _conn):
            cur.execute(
                "UPDATE systems SET status=?, status_note=?, last_checked=? WHERE id=?",
                (status, note, iso_now(), r["id"]),
            )
    # Mark integrations (no port) as green if we know about them - they're externally hosted
    with db.cursor() as (cur, _conn):
        cur.execute(
            "UPDATE systems SET status='green', status_note='external service', "
            "last_checked=? WHERE port IS NULL AND category='integration' "
            "AND status='unknown'",
            (iso_now(),),
        )
        cur.execute(
            "UPDATE systems SET status='green', last_checked=? WHERE category='mcp' "
            "AND status='unknown'",
            (iso_now(),),
        )


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def _send(self, code: int, body, content_type: str = "application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,DELETE,OPTIONS")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def do_OPTIONS(self):
        self._send(204, b"")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path == "/index.html":
            if OFFICE_HTML.exists():
                self._send(200, OFFICE_HTML.read_bytes(), "text/html; charset=utf-8")
            else:
                self._send(404, "office.html missing", "text/plain")
            return
        if path.startswith("/static/"):
            rel = path[len("/static/"):]
            full = (STATIC_DIR / rel).resolve()
            if STATIC_DIR.resolve() not in full.parents and full != STATIC_DIR.resolve():
                self._send(403, "forbidden", "text/plain")
                return
            if not full.exists() or not full.is_file():
                self._send(404, "not found", "text/plain")
                return
            ext = full.suffix.lower()
            ctype = {
                ".html": "text/html; charset=utf-8",
                ".js": "application/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".svg": "image/svg+xml",
                ".json": "application/json",
            }.get(ext, "application/octet-stream")
            self._send(200, full.read_bytes(), ctype)
            return

        if path == "/api/state":
            update_live_statuses()
            self._send(200, self._build_state())
            return
        if path == "/api/systems":
            self._send(200, db.query_all("SELECT * FROM systems ORDER BY room, slug"))
            return
        if path == "/api/agents":
            self._send(200, db.query_all("SELECT * FROM agents ORDER BY kind, slug"))
            return
        if path == "/api/credentials":
            self._send(200, db.query_all("SELECT * FROM credentials ORDER BY severity DESC, provider"))
            return
        if path == "/api/dashboards":
            self._send(200, db.query_all("SELECT * FROM dashboards ORDER BY room, slug"))
            return
        if path == "/api/processes":
            self._send(200, db.query_all("SELECT * FROM processes ORDER BY cadence, slug"))
            return
        if path == "/api/observations":
            qs = parse_qs(urlparse(self.path).query)
            include_resolved = qs.get("resolved", ["0"])[0] == "1"
            limit = int(qs.get("limit", ["50"])[0])
            sql = (
                "SELECT * FROM observations "
                + ("" if include_resolved else "WHERE resolved=0 ")
                + "ORDER BY ts DESC LIMIT ?"
            )
            self._send(200, db.query_all(sql, (limit,)))
            return
        if path == "/api/rooms":
            self._send(200, db.query_all("SELECT * FROM rooms ORDER BY sort_order"))
            return
        if path == "/api/memory":
            self._send(200, db.query_all(
                "SELECT * FROM agent_memory WHERE active=1 ORDER BY id DESC"
            ))
            return
        if path == "/api/chat":
            qs = parse_qs(urlparse(self.path).query)
            limit = int(qs.get("limit", ["20"])[0])
            self._send(200, db.query_all(
                "SELECT * FROM chat_messages ORDER BY ts DESC LIMIT ?", (limit,)
            ))
            return
        if path == "/api/agents/messages":
            qs = parse_qs(urlparse(self.path).query)
            limit = int(qs.get("limit", ["30"])[0])
            since = qs.get("since", [None])[0]
            if since:
                rows = db.query_all(
                    "SELECT * FROM agent_messages WHERE ts > ? ORDER BY ts DESC LIMIT ?",
                    (since, limit),
                )
            else:
                rows = db.recent_agent_messages(limit=limit)
            self._send(200, rows)
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path

        m = re.match(r"^/api/observations/(\d+)/(ack|resolve)$", path)
        if m:
            obs_id = int(m.group(1))
            action = m.group(2)
            field = "acknowledged" if action == "ack" else "resolved"
            with db.cursor() as (cur, _conn):
                if action == "resolve":
                    cur.execute(
                        "UPDATE observations SET resolved=1, acknowledged=1, "
                        "resolved_at=? WHERE id=?",
                        (iso_now(), obs_id),
                    )
                else:
                    cur.execute(
                        f"UPDATE observations SET {field}=1 WHERE id=?", (obs_id,)
                    )
            self._send(200, {"ok": True, "id": obs_id, "action": action})
            return

        m = re.match(r"^/api/observations/(\d+)/heal$", path)
        if m:
            obs_id = int(m.group(1))
            rows = db.query_all(
                "SELECT fix_command, auto_fixable, title FROM observations WHERE id=?",
                (obs_id,),
            )
            if not rows:
                self._send(404, {"ok": False, "error": "observation not found"})
                return
            r = rows[0]
            if not r["auto_fixable"] or not r["fix_command"]:
                self._send(400, {"ok": False, "error": "not auto-fixable"})
                return
            try:
                result = subprocess.run(
                    r["fix_command"], shell=True, capture_output=True,
                    text=True, timeout=30,
                )
                ok = result.returncode == 0
                with db.cursor() as (cur, _conn):
                    cur.execute(
                        "INSERT INTO tool_calls (tool, args, result, success) "
                        "VALUES (?, ?, ?, ?)",
                        ("heal", r["fix_command"],
                         (result.stdout + result.stderr)[:500], 1 if ok else 0),
                    )
                    if ok:
                        cur.execute(
                            "UPDATE observations SET resolved=1, acknowledged=1, "
                            "resolved_at=? WHERE id=?",
                            (iso_now(), obs_id),
                        )
                self._send(200, {
                    "ok": ok, "id": obs_id,
                    "stdout": result.stdout[:500],
                    "stderr": result.stderr[:500],
                })
            except Exception as e:
                self._send(500, {"ok": False, "error": str(e)})
            return

        if path == "/api/insights/run":
            try:
                # Import here to avoid loading on every request
                import importlib
                mod = importlib.import_module("insights")
                importlib.reload(mod)
                out = mod.run()
                self._send(200, out)
            except Exception as e:
                self._send(500, {"ok": False, "error": str(e)})
            return

        if path == "/api/refresh":
            try:
                result = subprocess.run(
                    [sys.executable, str(ROOT / "discover.py")],
                    capture_output=True, text=True, timeout=60,
                )
                self._send(200, {
                    "ok": result.returncode == 0,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                })
            except Exception as e:
                self._send(500, {"ok": False, "error": str(e)})
            return

        if path == "/api/open":
            body = self._read_json()
            slug = body.get("slug")
            if not slug:
                self._send(400, {"error": "slug required"})
                return
            row = db.query_all(
                "SELECT open_command FROM dashboards WHERE slug=?", (slug,)
            )
            if not row:
                self._send(404, {"error": "dashboard not found"})
                return
            cmd = row[0]["open_command"]
            try:
                subprocess.Popen(cmd, shell=True)
                self._send(200, {"ok": True, "ran": cmd})
            except Exception as e:
                self._send(500, {"ok": False, "error": str(e)})
            return

        if path == "/api/agents/message":
            body = self._read_json()
            from_agent = body.get("from_agent")
            if not from_agent:
                self._send(400, {"error": "from_agent required"})
                return
            msg_id = db.log_agent_message(
                from_agent=from_agent,
                to_agent=body.get("to_agent"),
                kind=body.get("kind") or "handoff",
                title=body.get("title"),
                body=body.get("body"),
                subject_kind=body.get("subject_kind"),
                subject_slug=body.get("subject_slug"),
                correlation_id=body.get("correlation_id"),
            )
            self._send(200, {"ok": True, "id": msg_id})
            return

        if path == "/api/chat":
            body = self._read_json()
            msg = (body.get("message") or "").strip()
            if not msg:
                self._send(400, {"error": "message required"})
                return
            with db.cursor() as (cur, _conn):
                cur.execute(
                    "INSERT INTO chat_messages (role, content) VALUES ('user', ?)",
                    (msg,),
                )
                msg_id = cur.lastrowid

            # Call claude CLI with the chief-of-staff agent
            try:
                claude_bin = "/usr/local/bin/claude"
                settings_path = str(ROOT / "settings" / "cos-permissions.json")
                proc = subprocess.run(
                    [
                        claude_bin, "--print",
                        "--agent", "chief-of-staff",
                        "--settings", settings_path,
                        msg,
                    ],
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                    timeout=180,
                    env={
                        "PATH": "/usr/local/bin:/usr/bin:/bin",
                        "HOME": str(Path.home()),
                    },
                )
                reply = (proc.stdout or "").strip()
                if not reply:
                    reply = "(תגובה ריקה. stderr: " + (proc.stderr or "")[:200] + ")"
                with db.cursor() as (cur, _conn):
                    cur.execute(
                        "INSERT INTO chat_messages (role, content) VALUES ('assistant', ?)",
                        (reply,),
                    )
                self._send(200, {"ok": True, "id": msg_id, "reply": reply})
            except subprocess.TimeoutExpired:
                err = "תגובה מ-Claude לקחה יותר מ-3 דקות. נסה שוב."
                with db.cursor() as (cur, _conn):
                    cur.execute(
                        "INSERT INTO chat_messages (role, content) VALUES ('assistant', ?)",
                        (f"⚠️ {err}",),
                    )
                self._send(200, {"ok": False, "id": msg_id, "error": err})
            except Exception as e:
                err = f"שגיאה: {e}"
                with db.cursor() as (cur, _conn):
                    cur.execute(
                        "INSERT INTO chat_messages (role, content) VALUES ('assistant', ?)",
                        (f"⚠️ {err}",),
                    )
                self._send(500, {"ok": False, "id": msg_id, "error": str(e)})
            return

        self._send(404, {"error": "not found"})

    def _build_state(self) -> dict:
        return {
            "ts": iso_now(),
            "rooms": db.query_all("SELECT * FROM rooms ORDER BY sort_order"),
            "systems": db.query_all("SELECT * FROM systems ORDER BY room, slug"),
            "agents": db.query_all(
                "SELECT slug, kind, name, description, room, icon, plugin "
                "FROM agents ORDER BY room, kind, slug"
            ),
            "dashboards": db.query_all("SELECT * FROM dashboards ORDER BY room"),
            "processes": db.query_all("SELECT * FROM processes ORDER BY room"),
            "credentials": db.query_all(
                "SELECT slug, provider, purpose, severity, last_balance, "
                "last_balance_at, dashboard_url FROM credentials ORDER BY severity DESC"
            ),
            "observations": db.query_all(
                "SELECT * FROM observations WHERE resolved=0 ORDER BY ts DESC LIMIT 30"
            ),
            "agent_messages": db.recent_agent_messages(limit=20),
            "memory_count": db.query_all(
                "SELECT COUNT(*) as n FROM agent_memory WHERE active=1"
            )[0]["n"],
            "counts": {
                "systems": db.query_all("SELECT COUNT(*) as n FROM systems")[0]["n"],
                "agents": db.query_all(
                    "SELECT COUNT(*) as n FROM agents WHERE kind='agent'"
                )[0]["n"],
                "skills": db.query_all(
                    "SELECT COUNT(*) as n FROM agents WHERE kind='skill'"
                )[0]["n"],
                "credentials": db.query_all(
                    "SELECT COUNT(*) as n FROM credentials"
                )[0]["n"],
                "processes": db.query_all(
                    "SELECT COUNT(*) as n FROM processes"
                )[0]["n"],
                "open_observations": db.query_all(
                    "SELECT COUNT(*) as n FROM observations WHERE resolved=0"
                )[0]["n"],
            },
        }


def main():
    print(f"🎩 Chief of Staff server on http://127.0.0.1:{PORT}")
    print(f"   DB: {db.DB_PATH}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
