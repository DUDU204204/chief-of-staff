-- Chief of Staff — Registry DB
-- Single source of truth for systems, agents, credentials, dashboards, processes, observations
-- Auto-populated by discover.py; auto-refreshed by health_check.py

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ════════════════════════════════════════════════════════════════════
-- SYSTEMS — דשבורדים, שירותים, אינטגרציות, MCP servers
-- ════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS systems (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slug            TEXT NOT NULL UNIQUE,         -- 'banking', 'investments', 'accounting', 'mcp-drive'
    name            TEXT NOT NULL,                -- 'דשבורד בנקאות'
    category        TEXT NOT NULL,                -- 'dashboard'|'mcp'|'integration'|'tool'|'data'
    description     TEXT,
    url             TEXT,                         -- http://127.0.0.1:PORT או external URL
    port            INTEGER,
    code_path       TEXT,                         -- absolute path to code dir, optional
    daemon_label    TEXT,                         -- e.g. 'com.mybiz.something' (LaunchAgent)
    status          TEXT DEFAULT 'unknown',       -- 'green'|'yellow'|'red'|'unknown'
    status_note     TEXT,                         -- "API responded 200 in 12ms" / "port not listening"
    last_checked    TEXT,                         -- ISO ts
    room            TEXT DEFAULT 'lobby',         -- חדר במשרד הויזואלי
    icon            TEXT DEFAULT '🏢',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ════════════════════════════════════════════════════════════════════
-- AGENTS — sub-agents + skills discovered from ~/.claude/
-- ════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS agents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slug            TEXT NOT NULL UNIQUE,         -- 'cash-flow-agent', 'consulting-advisor'
    kind            TEXT NOT NULL,                -- 'agent'|'skill'
    name            TEXT NOT NULL,
    description     TEXT,
    file_path       TEXT,                         -- ~/.claude/agents/cash-flow-agent.md
    tools           TEXT,                         -- "Bash,Read,Grep,WebSearch,WebFetch"
    model           TEXT,                         -- 'sonnet'|'opus'|...
    plugin          TEXT,                         -- 'yahav-marketing' if part of a plugin
    last_used       TEXT,                         -- ISO ts (best-effort from logs)
    use_count       INTEGER DEFAULT 0,
    room            TEXT DEFAULT 'agents-floor',
    icon            TEXT DEFAULT '🤖',
    sprite          TEXT,                         -- path to character sprite
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ════════════════════════════════════════════════════════════════════
-- CREDENTIALS — API keys, tokens, OAuth (NEVER store the actual secret here)
-- We store *metadata* only: where it lives, what it powers, expiry, balance
-- ════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS credentials (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slug            TEXT NOT NULL UNIQUE,         -- 'anthropic-api', 'openai-api', 'gmail-oauth-main'
    provider        TEXT NOT NULL,                -- 'Anthropic', 'OpenAI', 'Google', 'Meta'
    purpose         TEXT,                         -- "Claude Code + agents"
    storage_kind    TEXT NOT NULL,                -- 'keychain'|'env_file'|'oauth_token_file'|'mcp_config'
    storage_ref     TEXT,                         -- "service=my-mcp account=username"
    dashboard_url   TEXT,                         -- "https://platform.claude.com/dashboard"
    balance_check_url   TEXT,                     -- API endpoint that returns balance/usage (if any)
    last_balance    TEXT,                         -- "$84.30 / $100 monthly"
    last_balance_at TEXT,                         -- ISO ts
    expires_at      TEXT,                         -- ISO date if known
    severity        TEXT DEFAULT 'ok',            -- 'ok'|'warning'|'critical'
    notes           TEXT,
    used_by_systems TEXT,                         -- comma-separated system slugs
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ════════════════════════════════════════════════════════════════════
-- DASHBOARDS — quick links / "rooms" with UIs to open
-- (subset of systems where category='dashboard'; this is a convenience view)
-- ════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS dashboards (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slug            TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    url             TEXT NOT NULL,                -- local or remote
    open_command    TEXT,                         -- 'open -a Banking' or 'open URL'
    description     TEXT,
    is_local        INTEGER DEFAULT 1,
    room            TEXT DEFAULT 'lobby',
    icon            TEXT DEFAULT '📊',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ════════════════════════════════════════════════════════════════════
-- PROCESSES — recurring workflows
-- ════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS processes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slug            TEXT NOT NULL UNIQUE,         -- 'monthly-report', 'weekly-summary'
    name            TEXT NOT NULL,
    description     TEXT,
    cadence         TEXT,                         -- 'daily 08:00', 'monthly 1st', 'manual'
    daemon_label    TEXT,                         -- LaunchAgent label if automated
    trigger_command TEXT,                         -- e.g. '/my-skill-name' (a Claude skill slug)
    last_run        TEXT,
    last_status     TEXT,                         -- 'success'|'failed'|'partial'|'unknown'
    last_log_path   TEXT,
    next_due        TEXT,                         -- expected next run
    room            TEXT DEFAULT 'processes',
    icon            TEXT DEFAULT '🔁',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ════════════════════════════════════════════════════════════════════
-- OBSERVATIONS — anything the Chief-of-Staff noticed
-- (token nearly out, dashboard down, cron failing, pattern detected, idea)
-- ════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS observations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT NOT NULL DEFAULT (datetime('now')),
    kind            TEXT NOT NULL,                -- 'health'|'insight'|'idea'|'alert'|'pattern'
    severity        TEXT NOT NULL DEFAULT 'info', -- 'info'|'warning'|'critical'
    subject_kind    TEXT,                         -- 'system'|'agent'|'credential'|'process'|null
    subject_slug    TEXT,                         -- FK-ish (free-form reference)
    title           TEXT NOT NULL,
    body            TEXT,
    recommended_action TEXT,                      -- "Run X" / "Buy more credits at Y"
    auto_fixable    INTEGER DEFAULT 0,            -- 1 if we know how to heal automatically
    fix_command     TEXT,                         -- shell command to apply the fix
    acknowledged    INTEGER DEFAULT 0,
    resolved        INTEGER DEFAULT 0,
    resolved_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_obs_severity_ack ON observations(severity, acknowledged);
CREATE INDEX IF NOT EXISTS idx_obs_ts ON observations(ts DESC);

-- ════════════════════════════════════════════════════════════════════
-- AGENT_MESSAGES — agent-to-agent communication log ("the war room")
-- Each row is one event: handoff, ask, escalate, report, standup, system
-- Used by the visual office to animate live activity and by the briefing
-- to surface recent agent collaboration.
-- ════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS agent_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT NOT NULL DEFAULT (datetime('now')),
    from_agent      TEXT NOT NULL,                -- agent slug (e.g. 'jarvis', 'consulting-advisor')
    to_agent        TEXT,                         -- null = broadcast/standup
    kind            TEXT NOT NULL DEFAULT 'handoff',  -- 'handoff'|'ask'|'escalate'|'report'|'standup'|'system'
    title           TEXT,                         -- one-line summary
    body            TEXT,                         -- longer payload (markdown allowed)
    subject_kind    TEXT,                         -- 'client'|'process'|'system'|null
    subject_slug    TEXT,                         -- slug of the subject (e.g. 'acme-corp')
    correlation_id  TEXT,                         -- threads related messages (e.g. one handoff + its report)
    completed       INTEGER DEFAULT 0,            -- 1 when the recipient marked it done
    completed_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_msg_ts ON agent_messages(ts DESC);
CREATE INDEX IF NOT EXISTS idx_msg_from ON agent_messages(from_agent);
CREATE INDEX IF NOT EXISTS idx_msg_to ON agent_messages(to_agent);
CREATE INDEX IF NOT EXISTS idx_msg_correlation ON agent_messages(correlation_id);

-- ════════════════════════════════════════════════════════════════════
-- AGENT_MEMORY — Chief-of-Staff's own long-term memory
-- ════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS agent_memory (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fact            TEXT NOT NULL,
    source          TEXT,                         -- 'dudu'|'agent'|'discovery'
    tag             TEXT,                         -- 'preference'|'fact'|'goal'|'wishlist'
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    active          INTEGER DEFAULT 1
);

-- ════════════════════════════════════════════════════════════════════
-- CHAT_MESSAGES — conversation history with the chief of staff
-- ════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS chat_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT NOT NULL DEFAULT (datetime('now')),
    role            TEXT NOT NULL,                -- 'user'|'assistant'|'system'
    content         TEXT NOT NULL
);

-- ════════════════════════════════════════════════════════════════════
-- TOOL_CALLS — audit of actions the chief of staff took
-- ════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS tool_calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT NOT NULL DEFAULT (datetime('now')),
    tool            TEXT NOT NULL,
    args            TEXT,
    result          TEXT,
    success         INTEGER DEFAULT 1
);

-- ════════════════════════════════════════════════════════════════════
-- ROOMS — definition of the visual office layout
-- ════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS rooms (
    slug            TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    x               INTEGER NOT NULL,             -- grid position
    y               INTEGER NOT NULL,
    width           INTEGER DEFAULT 4,
    height          INTEGER DEFAULT 3,
    color           TEXT DEFAULT '#2a2a3e',
    icon            TEXT,
    sort_order      INTEGER DEFAULT 0
);

-- Seed default rooms
INSERT OR IGNORE INTO rooms (slug, name, description, x, y, width, height, color, icon, sort_order) VALUES
    ('lobby',         'הלובי',           'נקודת הכניסה - מצב כללי וקיצורים',     0, 0, 6, 4, '#1e3a5f', '🚪', 1),
    ('finance',       'חדר פיננסים',     'בנקאות, השקעות, הנהלת חשבונות',      6, 0, 5, 4, '#1f4d3a', '💰', 2),
    ('clients',       'חדר לקוחות',      'דשבורד/CRM של הלקוחות שלך',          11, 0, 5, 4, '#4a2d5a', '🤝', 3),
    ('agents-floor',  'חדר הסוכנים',     'כל הסוכנים והסקילים',                 0, 4, 8, 4, '#3a3a1f', '🤖', 4),
    ('processes',     'חדר אוטומציות',   'cron + LaunchAgents + תהליכים חוזרים', 8, 4, 4, 4, '#5a2d2d', '⚙️', 5),
    ('integrations',  'חדר חיבורים',     'MCP, APIs, מפתחות',                   12, 4, 4, 4, '#2d4a5a', '🔌', 6),
    ('insights',      'חדר התובנות',     'observations + alerts + ideas',       0, 8, 16, 3, '#5a4a1f', '💡', 7);
