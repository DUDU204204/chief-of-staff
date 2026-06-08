#!/usr/bin/env python3
"""Auto-discovery — scan everything that exists on this machine and seed the registry.

Sources scanned:
- ~/.claude/agents/         → agents table
- ~/.claude/skills/         → agents table (kind=skill)
- ~/.claude/plugins/        → agents table (kind=skill, with plugin name)
- ~/Library/LaunchAgents/   → processes table (macOS only, opt-in by prefix)
- ~/.claude.json            → systems table (kind=mcp)
- systems.json (this dir)   → systems table (user-registered dashboards/services)

Idempotent — safe to re-run.
"""
from __future__ import annotations

import json
import os
import platform
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import db  # noqa: E402

HOME = Path.home()
CLAUDE_DIR = HOME / ".claude"
SKILLS_DIR = CLAUDE_DIR / "skills"
AGENTS_DIR = CLAUDE_DIR / "agents"
PLUGINS_DIR = CLAUDE_DIR / "plugins"
LAUNCH_AGENTS_DIR = HOME / "Library" / "LaunchAgents"
CLAUDE_CONFIG = HOME / ".claude.json"
USER_SYSTEMS_FILE = ROOT / "systems.json"

# LaunchAgent prefixes to discover. Customize via env var:
#   COS_LAUNCHAGENT_PREFIXES="com.myname,com.mybiz"
# Default: scan all `com.*` plists owned by the user.
LAUNCHAGENT_PREFIXES = [
    p.strip()
    for p in os.environ.get("COS_LAUNCHAGENT_PREFIXES", "com.").split(",")
    if p.strip()
]


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────
def parse_frontmatter(md: str) -> dict:
    if not md.startswith("---"):
        return {}
    end = md.find("\n---", 3)
    if end == -1:
        return {}
    block = md[3:end].strip()
    out: dict[str, str] = {}
    for line in block.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


# ──────────────────────────────────────────────────────────────────────
# Agents (subagents in ~/.claude/agents/)
# ──────────────────────────────────────────────────────────────────────
def discover_agents() -> int:
    n = 0
    if not AGENTS_DIR.exists():
        return 0
    for f in AGENTS_DIR.glob("*.md"):
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue
        meta = parse_frontmatter(content)
        slug = meta.get("name") or f.stem
        db.upsert("agents", "slug", {
            "slug": slug,
            "kind": "agent",
            "name": slug,
            "description": meta.get("description", "")[:500],
            "file_path": str(f),
            "tools": meta.get("tools", ""),
            "model": meta.get("model", ""),
            "plugin": None,
            "room": "agents-floor",
            "icon": "🤖",
        })
        n += 1
    return n


# ──────────────────────────────────────────────────────────────────────
# Skills (~/.claude/skills + plugin skills)
# ──────────────────────────────────────────────────────────────────────
def discover_skills() -> int:
    n = 0
    # User skills
    if SKILLS_DIR.exists():
        for path in SKILLS_DIR.iterdir():
            if not path.is_dir():
                continue
            skill_md = path / "SKILL.md"
            if not skill_md.exists():
                continue
            try:
                meta = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
            except Exception:
                continue
            slug = meta.get("name") or path.name
            db.upsert("agents", "slug", {
                "slug": slug,
                "kind": "skill",
                "name": slug,
                "description": meta.get("description", "")[:500],
                "file_path": str(skill_md),
                "tools": meta.get("tools", ""),
                "model": meta.get("model", ""),
                "plugin": None,
                "room": "skills-user",
                "icon": "🧰",
            })
            n += 1

    # Plugin skills
    if PLUGINS_DIR.exists():
        try:
            plugin_skill_files = list(PLUGINS_DIR.rglob("SKILL.md"))
        except PermissionError:
            print(f"   ⚠️  PermissionError on {PLUGINS_DIR} — skipping plugin skills")
            plugin_skill_files = []
        for plugin_skill in plugin_skill_files:
            try:
                meta = parse_frontmatter(plugin_skill.read_text(encoding="utf-8"))
            except Exception:
                continue
            slug = meta.get("name")
            if not slug:
                continue
            parts = plugin_skill.parts
            plugin = None
            for i, p in enumerate(parts):
                if p == "skills" and i > 0:
                    plugin = parts[i - 1]
                    break
            full_slug = f"{plugin}:{slug}" if plugin else slug
            db.upsert("agents", "slug", {
                "slug": full_slug,
                "kind": "skill",
                "name": slug,
                "description": meta.get("description", "")[:500],
                "file_path": str(plugin_skill),
                "tools": meta.get("tools", ""),
                "model": meta.get("model", ""),
                "plugin": plugin,
                "room": "plugin-skills",
                "icon": "🧩",
            })
            n += 1
    return n


# ──────────────────────────────────────────────────────────────────────
# LaunchAgents (macOS only)
# ──────────────────────────────────────────────────────────────────────
def discover_launch_agents() -> int:
    if platform.system() != "Darwin":
        return 0
    if not LAUNCH_AGENTS_DIR.exists():
        return 0

    import plistlib

    n = 0
    for plist in LAUNCH_AGENTS_DIR.glob("*.plist"):
        if not any(plist.name.startswith(p) for p in LAUNCHAGENT_PREFIXES):
            continue
        try:
            with open(plist, "rb") as f:
                data = plistlib.load(f)
        except Exception:
            continue
        label = data.get("Label") or plist.stem
        program = data.get("ProgramArguments", [])
        cmd = " ".join(program) if isinstance(program, list) else str(program)

        cadence = "manual"
        if data.get("StartInterval"):
            secs = data["StartInterval"]
            cadence = f"every {secs // 60}m" if secs < 3600 else f"every {secs // 3600}h"
        elif "StartCalendarInterval" in data:
            sci = data["StartCalendarInterval"]
            if isinstance(sci, dict):
                hour = sci.get("Hour", "?")
                minute = sci.get("Minute", 0)
                cadence = f"daily {hour:02d}:{minute:02d}" if isinstance(hour, int) else f"daily {hour}:{minute}"
        elif data.get("KeepAlive"):
            cadence = "always-on"

        log_path = data.get("StandardOutPath") or data.get("StandardErrorPath")

        # Strip the prefix for a cleaner slug
        slug = label
        for pfx in LAUNCHAGENT_PREFIXES:
            if slug.startswith(pfx):
                slug = slug[len(pfx):].lstrip(".")
                break

        db.upsert("processes", "slug", {
            "slug": f"launchagent:{slug}",
            "name": slug,
            "description": f"LaunchAgent: {cmd[:200]}",
            "cadence": cadence,
            "daemon_label": label,
            "trigger_command": cmd[:500],
            "last_log_path": log_path,
            "room": "processes",
            "icon": "⚙️",
        })
        n += 1
    return n


# ──────────────────────────────────────────────────────────────────────
# MCP servers (from ~/.claude.json)
# ──────────────────────────────────────────────────────────────────────
def discover_mcp() -> int:
    if not CLAUDE_CONFIG.exists():
        return 0
    try:
        cfg = json.loads(CLAUDE_CONFIG.read_text())
    except Exception:
        return 0
    n = 0
    servers_seen: set[str] = set()

    def harvest(src):
        nonlocal n
        if not isinstance(src, dict):
            return
        for name, conf in src.items():
            if name in servers_seen:
                continue
            servers_seen.add(name)
            if not isinstance(conf, dict):
                continue
            cmd = conf.get("command", "")
            args = conf.get("args", [])
            cmd_str = f"{cmd} {' '.join(str(a) for a in args)}".strip()[:300]
            db.upsert("systems", "slug", {
                "slug": f"mcp:{name}",
                "name": name,
                "category": "mcp",
                "description": f"MCP server: {cmd_str}",
                "url": None,
                "port": None,
                "code_path": None,
                "daemon_label": None,
                "status": "unknown",
                "status_note": None,
                "last_checked": None,
                "room": "integrations",
                "icon": "🔌",
            })
            n += 1

    harvest(cfg.get("mcpServers"))
    for proj in cfg.get("projects", {}).values():
        if isinstance(proj, dict):
            harvest(proj.get("mcpServers"))
    return n


# ──────────────────────────────────────────────────────────────────────
# User-registered systems (from systems.json in this directory)
# ──────────────────────────────────────────────────────────────────────
def discover_user_systems() -> int:
    """Read user-defined dashboards/services from systems.json.

    Format:
    {
      "systems": [
        {
          "slug": "my-crm",
          "name": "CRM שלי",
          "category": "dashboard",
          "description": "Pipedrive / HubSpot / etc",
          "url": "http://localhost:3000",
          "port": 3000,
          "room": "operations",
          "icon": "📇"
        }
      ]
    }
    """
    if not USER_SYSTEMS_FILE.exists():
        return 0
    try:
        cfg = json.loads(USER_SYSTEMS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"   ⚠️  Failed to parse {USER_SYSTEMS_FILE}: {e}")
        return 0
    n = 0
    for s in cfg.get("systems", []):
        if not s.get("slug"):
            continue
        db.upsert("systems", "slug", {
            "slug": s["slug"],
            "name": s.get("name", s["slug"]),
            "category": s.get("category", "dashboard"),
            "description": s.get("description", ""),
            "url": s.get("url"),
            "port": s.get("port"),
            "code_path": s.get("code_path"),
            "daemon_label": s.get("daemon_label"),
            "status": "unknown",
            "status_note": None,
            "last_checked": None,
            "room": s.get("room", "lobby"),
            "icon": s.get("icon", "🏢"),
        })
        n += 1
    return n


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────
def main() -> None:
    db.init_schema()
    print("🔍 Discovering...")
    print(f"   agents:         {discover_agents()}")
    print(f"   skills:         {discover_skills()}")
    print(f"   MCP servers:    {discover_mcp()}")
    print(f"   user systems:   {discover_user_systems()}")
    print(f"   LaunchAgents:   {discover_launch_agents()}")
    print("✅ Done.")


if __name__ == "__main__":
    main()
