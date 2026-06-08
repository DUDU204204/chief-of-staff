# Chief of Staff

> דשבורד "המשרד שלי" ל-Claude Code — אינדקס חי של כל הסוכנים, הסקילים, ה-MCPים, וה-LaunchAgents במכונה שלך, בגישה ויזואלית של "משרד" עם חדרים.

נבנה במקור ע"י [דודו נחום](https://nahum.io) כחלק מסביבת העבודה האישית שלו עם Claude Code. הגרסה הזו נקייה מכל מידע אישי ומיועדת לכל בעל עסק שרוצה לקבל overview ויזואלי של ה-Claude Code שלו.

---

## מה זה עושה

- **אוטו-גילוי** של כל מה שיש לך:
  - סוכנים (`~/.claude/agents/*.md`)
  - סקילים (`~/.claude/skills/*` + plugin skills)
  - שרתי MCP (מתוך `~/.claude.json`)
  - LaunchAgents (macOS, לפי prefix לבחירתך)
  - מערכות שאתה רושם ידנית ב-`systems.json`
- **דשבורד ויזואלי** שמציג הכל בחדרים — finance, marketing, agents-floor, וכו'
- **בדיקות סטטוס** — בודק אם הפורטים של הדשבורדים שלך חיים
- **תצוגת "war room"** של תקשורת בין סוכנים (אם יש לך אוטומציות שכותבות ל-DB)

---

## דרישות

- Python 3.10+
- Claude Code מותקן (עבור ה-auto-discovery של agents/skills/MCP)
- macOS / Linux / Windows

---

## התקנה

### macOS / Linux
```bash
git clone https://github.com/DUDU204204/chief-of-staff.git
cd chief-of-staff
./setup.sh
python3 server.py
```

### Windows
```cmd
git clone https://github.com/DUDU204204/chief-of-staff.git
cd chief-of-staff
setup.bat
python server.py
```

(אם Windows אומר ש-`python` לא מזוהה — תוודא שב-PATH יש את התקנת Python 3.10+. לרוב פתרון מהיר: התקן מ-python.org עם "Add to PATH" מסומן.)

ה-`setup` מאתחל DB, מריץ discovery, ואומר לך מה לעשות הלאה.

---

## הפעלה

פתח בדפדפן: **http://127.0.0.1:17090**

### הבדלים בין מערכות הפעלה

| תכונה | macOS | Linux | Windows |
|---|---|---|---|
| Auto-discovery של agents/skills | ✅ | ✅ | ✅ |
| Auto-discovery של MCP servers | ✅ | ✅ | ✅ |
| Auto-discovery של LaunchAgents | ✅ | — | — |
| רישום ידני של systems ב-`systems.json` | ✅ | ✅ | ✅ |
| הדשבורד עצמו | ✅ | ✅ | ✅ |

על Windows ו-Linux, פשוט יוצג 0 processes (אין LaunchAgent equivalent דיסקאברי בנתיב הזה). אם אתה משתמש ב-Task Scheduler או cron — אפשר להוסיף אותם ידנית ל-`systems.json`.

---

## הגדרה אישית

### 1. רישום הדשבורדים שלך
```bash
cp systems.json.example systems.json
# ערוך את systems.json — הוסף CRM, אנליטיקס, דשבורדים מקומיים, וכל מה שאתה רוצה לראות במשרד
python3 discover.py
```

### 2. LaunchAgent prefixes (macOS)
ברירת המחדל: סורק כל `com.*.plist` שלך.
כדי לצמצם:
```bash
export COS_LAUNCHAGENT_PREFIXES="com.mybiz,com.myname"
python3 discover.py
```

### 3. הרשאות לסוכן Claude
אם אתה רוצה לתת לסוכן ה-Claude שלך הרשאות לערוך את הקבצים כאן בלי prompts בכל פעם:
- העתק את `settings/cos-permissions.json` לתוך `~/.claude/settings.json`
- החלף `{COS_PATH}` בנתיב המוחלט של התיקייה הזו

---

## מבנה

```
chief-of-staff/
├── server.py              # FastAPI-like server (stdlib only)
├── office.html            # ה-UI הראשי (1.4K שורות, single-file)
├── mission-control.html   # mission control view
├── discover.py            # auto-discovery sweep
├── schema.sql             # DB schema
├── lib/db.py              # SQLite helpers
├── settings/              # template settings
├── static/                # assets + command palette
├── systems.json.example   # template לרישום מערכות
└── setup.sh               # first-run setup
```

---

## ארכיטקטורה

- **SQLite** (`data/registry.db`) — single source of truth. נוצר אוטומטית ע"י `setup.sh`.
- **HTTP server** ב-stdlib — אין dependencies חיצוניים.
- **Auto-discovery idempotent** — אפשר להריץ `python3 discover.py` שוב ושוב, יעדכן רק delta.
- **No outbound network calls by default** — הכל מקומי. (אם אתה מוסיף systems עם URLs חיצוניים, הדשבורד רק קורא URL — לא קורא לאינטרנט).

---

## מה זה לא

- **לא** מחליף ChatGPT/Claude Desktop.
- **לא** מריץ סוכנים בעצמו — רק נותן overview של מה שכבר בנית ב-Claude Code.
- **לא** מתחבר אוטומטית ל-Gmail/Drive/Calendar — אלה חיבורי MCP שאתה מגדיר ב-Claude עצמו.

---

## הקרדיט

הגישה של "office מטאפורי עם חדרים" + המודל של `systems / agents / processes / observations / agent_messages` פותחה במקור ע"י [דודו נחום](https://nahum.io) לשימוש האישי שלו, ושוחררה כאן כתבנית פתוחה לבעלי עסקים אחרים שרוצים לבנות סביבה דומה.

---

## רישיון

MIT. תעשה איתו מה שאתה רוצה. אם אתה בונה משהו מגניב על הבסיס הזה — נשמח לשמוע.
