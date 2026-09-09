<div dir="rtl">

# המשרד שלי

> דשבורד-על ל-Claude Code: מסך אחד שמגלה לבד את כל הסקילים, הסוכנים, החיבורים והמשימות המתוזמנות שלך,
> מפעיל סקילים בלחיצה, ומקבל דיווחים מהאוטומציות שלך.

נבנה במקור ע"י [דודו נחום](https://nahum.io) כחלק מסביבת העבודה שלו עם Claude Code, ושוחרר כאן נקי
מכל מידע אישי. Python בספרייה הסטנדרטית בלבד - **בלי pip, בלי ספריות, בלי קריאות לאינטרנט.**

---

## מה זה עושה

**גילוי אוטומטי** של כל מה שיש לך:

| מה | מאיפה |
|---|---|
| סקילים | `~/.claude/skills/*/SKILL.md`, `.claude/skills/` של הפרויקט, וסקילים של תוספים (plugins) |
| סוכנים | `~/.claude/agents/*.md` ו-`.claude/agents/` של הפרויקט |
| חיבורי MCP | `~/.claude.json`, `~/.claude/settings.json`, `.mcp.json` - **שמות בלבד, אף פעם לא מפתחות** |
| משימות מתוזמנות | Routines מקומיים של האפליקציה, systemd timers, crontab, LaunchAgents (מק) |
| hooks | `settings.json` - אירוע, כמה, ועל מה |
| מערכות שלך | `systems.json` - CRM, הנהלת חשבונות, מנהל מודעות, דשבורדים מקומיים |

**דשבורד** - תפריט צד עם מונים, חיפוש, סינון לפי תגית, וכרטיס לכל פריט. RTL, עברית.

**הפעלה** - כפתור על כל סקיל שמריץ אותו ברקע (`claude -p`) ומראה את הלוג בזמן אמת.

**תובנות** - כתובת אחת (`POST /api/observe`) שכל אוטומציה או סוכן שלך מדווחים אליה. בבוקר אתה
פותח ורואה מה קרה בלילה.

**רישום אוטומטי** - hook שרושם כל סקיל או סוכן חדש ברגע שהוא נוצר. חוק הזהב בלי לזכור אותו.

---

## התקנה

```bash
git clone https://github.com/DUDU204204/chief-of-staff.git my-office
cd my-office
./setup.sh          # ווינדוס: setup.bat
python3 server.py   # ואז בדפדפן: http://127.0.0.1:17090
```

דרישות: Python 3.10+, ו-Claude Code מותקן (בשביל הגילוי וההפעלה).

**הפורט תפוס?** `OFFICE_PORT=17091 python3 server.py`

---

## שימוש יומיומי

```bash
python3 discover.py        # גילוי מחדש (או כפתור "רענן" בדשבורד)
python3 register.py --list # מה רשום, כולל מה שנרשם ידנית
```

**רישום מערכת שאין לה גילוי אוטומטי** - או דרך כפתור "רישום" בדשבורד, או:

```bash
python3 register.py --kind system --slug crm --name "ה-CRM שלי" \
  --url https://app.example-crm.com --room לקוחות --icon 📇

python3 register.py --kind scheduled --slug zapier-leads --name "לידים מהטופס לגיליון" \
  --description "כל ליד מהאתר לגיליון" --tags אוטומציה,לקוחות
```

**המערכות שלך** - להעתיק את `systems.json.example` ל-`systems.json` ולערוך. רק שמות וכתובות:
**אף פעם לא סיסמאות או מפתחות.** דשבורד מקומי עם `port` מקבל נורית ירוקה כשהוא חי.

---

## רישום אוטומטי (hook)

כדי שכל סקיל או סוכן חדש יופיע במשרד בלי שתזכור - מוסיפים ל-`~/.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {"type": "command", "command": "/absolute/path/to/my-office/office_hook.sh", "args": []}
        ]
      }
    ]
  }
}
```

נתיב מלא, לא `~`. נכנס לתוקף בשיחה הבאה.

---

## דיווח מאוטומציות

השורה שכל סקריפט שלך מוסיף בסופו:

```bash
curl -s -X POST http://127.0.0.1:17090/api/observe -H 'Content-Type: application/json' \
  -d '{"source":"morning-report","severity":"info","title":"הדוח נשלח","body":"14 פניות, 2 חדשות"}'
```

`severity`: `info` / `warn` / `error`. המשרד למטה? ה-`curl` נכשל בשקט והאוטומציה ממשיכה.

---

## פרטיות ואבטחה

- השרת מאזין **רק ל-`127.0.0.1`** - לא לרשת, לא לאינטרנט.
- **אף מפתח, טוקן או סיסמה לא נשמרים.** חיבורי MCP נרשמים בשם ובסוג בלבד; משתני סביבה - רק
  שמות המפתחות, אף פעם לא הערכים.
- אין קריאות יוצאות. הדבר היחיד שנטען מבחוץ הוא פונט מ-Google Fonts ב-`index.html`; מי שלא רוצה
  גם את זה - מוחק את שורת ה-`<link>` והדפדפן יפול ל-`system-ui`.
- הרצת סקיל מהדשבורד רצה ב-`--permission-mode acceptEdits` (כותב קבצים, לא מריץ פקודות מסוכנות
  בלי אישור). זו בחירה, לא מקריות.
- הכל נשמר ב-`data/registry.db` המקומי שלך.

---

## מבנה

```
my-office/
├── server.py            # השרת + API (stdlib בלבד)
├── index.html           # הדשבורד, קובץ אחד
├── discover.py          # הגילוי האוטומטי
├── register.py          # רישום ידני
├── office_hook.sh       # hook לרישום אוטומטי
├── systems.json.example # תבנית למערכות שלך
└── data/registry.db     # נוצר אוטומטית
```

## API

| מסלול | מה |
|---|---|
| `GET /api/state` | הכל: פריטים, מונים, ריצות, תצפיות, בדיקת חיים למערכות |
| `POST /api/refresh` | גילוי מחדש |
| `POST /api/run` | `{"skill","args"}` - מריץ סקיל ברקע |
| `GET /api/runs` · `GET /api/runs/<id>` | ריצות + לוג |
| `POST /api/observe` | דיווח מאוטומציה |
| `POST /api/observations/<id>/ack` | סימון "טופל" |
| `POST /api/register` | רישום ידני |
| `GET /api/health` | בדיקת חיים |

---

## מה זה לא

- **לא** מריץ סוכנים בעצמו - הוא מראה מה יש לך ומפעיל סקילים.
- **לא** מתחבר ל-Gmail/Drive/יומן - אלה חיבורי MCP שמגדירים ב-Claude Code עצמו (הוא רק רואה שהם קיימים).
- **לא** מחליף את הצ'אט. הוא עונה על "מה בכלל יש לי?".

## רישיון

MIT. תעשה איתו מה שאתה רוצה.

</div>
