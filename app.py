import datetime
import multiprocessing
import os
import sqlite3
import sys
import time

import webview

from assistant.engine import Assistant
from tasks import CATEGORY_LABELS, TASKS, TOTAL_TASKS

APP_NAME = "PythonBackendTrainer"

if getattr(sys, 'frozen', False):

    os.chdir(os.path.dirname(sys.executable))


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _data_dir() -> str:

    if not _is_frozen():
        return os.path.dirname(os.path.abspath(__file__))

    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")

    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def _res(*parts) -> str:
    """Путь к ресурсу: рядом со скриптом или внутри PyInstaller-бандла."""
    base = sys._MEIPASS if _is_frozen() else os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parts)


def _exe_dir() -> str:
    return os.path.dirname(sys.executable) if _is_frozen() else os.path.dirname(os.path.abspath(__file__))


def build_html() -> str:
    """Собирает один inline-HTML из ui/ и vendor/ (так pywebview не зависит от путей)."""
    def rd(*p):
        with open(_res(*p), "r", encoding="utf-8") as f:
            return f.read()

    html = rd("ui", "index.html")
    for token, path in (
        ("%%VENDOR_CSS%%", ("vendor", "codemirror.css")),
        ("%%APP_CSS%%", ("ui", "app.css")),
        ("%%VENDOR_JS%%", ("vendor", "codemirror.js")),
        ("%%APP_JS%%", ("ui", "app.js")),
    ):
        html = html.replace(token, rd(*path))
    return html


DB_PATH = os.path.join(_data_dir(), "trainer.db")


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                task_id TEXT NOT NULL,
                status TEXT NOT NULL,
                duration_ms INTEGER,
                date TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS progress (
                category TEXT NOT NULL,
                task_id TEXT NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0,
                code TEXT,
                updated_at TEXT,
                PRIMARY KEY (category, task_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS srs (
                category TEXT NOT NULL,
                task_id TEXT NOT NULL,
                step INTEGER NOT NULL DEFAULT 0,
                due TEXT NOT NULL,
                PRIMARY KEY (category, task_id)
            )
        """)
        _migrate_progress(conn)
        conn.execute("UPDATE OR IGNORE srs SET category = category")   # no-op: таблица создана


def _valid_pairs():
    return {(c, t["id"]) for c, items in TASKS.items() for t in items}


def _migrate_progress(conn):
    """Задачи переезжали между категориями: переносим старый прогресс и попытки на новое место."""
    home = {t["id"]: c for c, items in TASKS.items() for t in items}
    for table in ("progress", "attempts", "srs"):
        for cat, tid in conn.execute(f"SELECT DISTINCT category, task_id FROM {table}").fetchall():
            new = home.get(tid)
            if new and new != cat:
                conn.execute(
                    f"UPDATE OR IGNORE {table} SET category = ? WHERE category = ? AND task_id = ?", (new, cat, tid)
                )


def _task_by_index(category, index):
    items = TASKS.get(category)
    if not items or not (0 <= index < len(items)):
        return None
    return items[index]


class API:
    def __init__(self):
        self.current = None
        init_db()

    def _db(self):
        return sqlite3.connect(DB_PATH)

    def _log_attempt(self, category, task_id, status, duration_ms):
        with self._db() as conn:
            conn.execute(
                "INSERT INTO attempts (category, task_id, status, duration_ms, date) VALUES (?, ?, ?, ?, ?)",
                (category, task_id, status, duration_ms, datetime.date.today().isoformat()),
            )

    SRS_LADDER = [1, 3, 7, 14, 30]       # через сколько дней повторять: 1, 3, 7, 14, 30

    def _srs_due_date(self, days):
        return (datetime.date.today() + datetime.timedelta(days=days)).isoformat()

    def _srs_after_review(self, cat, tid, clean):
        """Результат повторения: чисто решил, то интервал растёт, ошибался, то начинаем лесенку заново."""
        with self._db() as conn:
            row = conn.execute("SELECT step FROM srs WHERE category = ? AND task_id = ?", (cat, tid)).fetchone()
            step = row[0] if row else 0
            step = min(step + 1, len(self.SRS_LADDER) - 1) if clean else 0
            days = self.SRS_LADDER[step]
            conn.execute(
                "INSERT OR REPLACE INTO srs (category, task_id, step, due) VALUES (?, ?, ?, ?)",
                (cat, tid, step, self._srs_due_date(days)),
            )
        return days

    def _mark_progress(self, category, task_id, completed, code):
        with self._db() as conn:
            before = conn.execute(
                "SELECT completed FROM progress WHERE category = ? AND task_id = ?", (category, task_id)
            ).fetchone()
            if completed and not (before and before[0]):          # первое решение: ставим в график повторений
                conn.execute(
                    "INSERT OR IGNORE INTO srs (category, task_id, step, due) VALUES (?, ?, 0, ?)",
                    (category, task_id, self._srs_due_date(self.SRS_LADDER[0])),
                )
            conn.execute(
                """INSERT INTO progress (category, task_id, completed, code, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(category, task_id) DO UPDATE SET
                       completed = MAX(progress.completed, excluded.completed),
                       code = excluded.code,
                       updated_at = excluded.updated_at""",
                (category, task_id, 1 if completed else 0, code, datetime.datetime.now().isoformat()),
            )

    def get_categories(self):
        return [{"key": k, "label": CATEGORY_LABELS.get(k, k), "count": len(v)} for k, v in TASKS.items()]

    def get_tasks_by_category(self, cat):
        items = TASKS.get(cat, [])
        with self._db() as conn:
            rows = conn.execute(
                "SELECT task_id, completed FROM progress WHERE category = ?", (cat,)
            ).fetchall()
        completed_ids = {r[0] for r in rows if r[1]}

        return [
            {
                "index": i,
                "id": t["id"],
                "title": t["title"],
                "difficulty": t.get("difficulty", 1),
                "type": t["type"],
                "kind": t.get("kind", "write"),
                "completed": t["id"] in completed_ids,
            }
            for i, t in enumerate(items)
        ]

    def get_overall_progress(self):
        valid = _valid_pairs()
        with self._db() as conn:
            rows = conn.execute("SELECT category, task_id FROM progress WHERE completed = 1").fetchall()
        return {"completed": sum(1 for r in rows if (r[0], r[1]) in valid), "total": TOTAL_TASKS}

    def set_current_task(self, cat, index, review=False):
        task = _task_by_index(cat, index)
        if not task:
            return {"error": "Задача не найдена"}
        self.current = (cat, index, task)
        self.review = bool(review)
        self.review_failed = False

        with self._db() as conn:
            row = conn.execute(
                "SELECT code, completed FROM progress WHERE category = ? AND task_id = ?",
                (cat, task["id"]),
            ).fetchone()
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('last_category', ?)", (cat,)
            )
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('last_index', ?)", (str(index),)
            )

        saved_code = row[0] if row and row[0] else None
        completed = bool(row[1]) if row else False

        hidden = ("tests", "expected_stdout", "expected_json", "checks", "answer", "explain")
        public = {k: v for k, v in task.items() if k not in hidden}
        if task["type"] == "quiz":
            public["code"] = task["code"]
        elif review:
            public["code"] = task.get("template", "")           # повторение: с чистого листа, из памяти
        else:
            public["code"] = saved_code or task.get("template", "")
        public["review"] = bool(review)
        public["completed"] = completed
        public["hint_count"] = len(task.get("hints", []))
        return public

    def get_last_position(self):
        with self._db() as conn:
            rows = dict(conn.execute("SELECT key, value FROM settings").fetchall())
        cat = rows.get("last_category")
        idx = rows.get("last_index")
        if cat and idx is not None and cat in TASKS:
            try:
                idx = int(idx)
                if 0 <= idx < len(TASKS[cat]):
                    return {"category": cat, "index": idx}
            except ValueError:
                pass
        return None

    def save_draft(self, code):
        """Автосохранение кода без запуска проверки (debounce на фронте)."""
        if not self.current:
            return {"ok": False}
        cat, _, task = self.current
        with self._db() as conn:
            conn.execute(
                """INSERT INTO progress (category, task_id, completed, code, updated_at)
                   VALUES (?, ?, COALESCE((SELECT completed FROM progress WHERE category=? AND task_id=?), 0), ?, ?)
                   ON CONFLICT(category, task_id) DO UPDATE SET code = excluded.code, updated_at = excluded.updated_at""",
                (cat, task["id"], cat, task["id"], code, datetime.datetime.now().isoformat()),
            )
        return {"ok": True}

    def reset_code(self):
        if not self.current:
            return {"code": ""}
        _, _, task = self.current
        return {"code": task.get("template", "")}

    def check_code(self, code):
        if not self.current:
            return {"status": "error", "output": "Сначала выбери задачу слева."}

        cat, index, task = self.current

        if task.get("kind") == "fill" and "___" in code:
            self.save_draft(code)
            return {
                "status": "error",
                "output": "✏️ В коде остались пропуски ___. Замени каждый на нужный фрагмент и запусти снова.",
            }

        from sandbox import run_check

        start = time.monotonic()
        result = run_check(code, task, timeout=6.0)
        duration_ms = int((time.monotonic() - start) * 1000)

        status = result.get("status", "error")
        self._log_attempt(cat, task["id"], status, duration_ms)

        if getattr(self, "review", False):
            if status == "success":
                result["srs_days"] = self._srs_after_review(cat, task["id"], clean=not self.review_failed)
                self.review = False
            else:
                self.review_failed = True
        if status == "success":
            self._mark_progress(cat, task["id"], True, code)
        elif status in ("fail",):
            self._mark_progress(cat, task["id"], False, code)
        else:
            self.save_draft(code)

        result["duration_ms"] = duration_ms
        return result

    def check_answer(self, index):
        """Проверка задач типа quiz («Что выведет?»): без запуска кода."""
        if not self.current:
            return {"status": "error", "output": "Сначала выбери задачу слева."}
        cat, _, task = self.current
        if task["type"] != "quiz":
            return {"status": "error", "output": "Эта задача проверяется запуском кода."}
        ok = index == task["answer"]
        self._log_attempt(cat, task["id"], "success" if ok else "fail", 0)
        if ok:
            res = {"status": "success", "output": "✅ Верно!\n" + task.get("explain", ""), "duration_ms": 0}
            if getattr(self, "review", False):
                res["srs_days"] = self._srs_after_review(cat, task["id"], clean=not self.review_failed)
                self.review = False
            self._mark_progress(cat, task["id"], True, str(index))
            return res
        self.review_failed = True
        return {
            "status": "fail",
            "output": "❌ Не совсем. Пройди код сверху вниз, строка за строкой, и попробуй ещё раз.",
            "duration_ms": 0,
        }

    def get_next_task(self):
        """Следующая незавершённая задача — для кнопки 'Далее' после успеха."""
        if not self.current:
            return None
        cat, index, _ = self.current

        with self._db() as conn:
            done_rows = conn.execute("SELECT category, task_id FROM progress WHERE completed = 1").fetchall()
        done = {(c, t) for c, t in done_rows}

        cats = list(TASKS.keys())

        def find_from(cat_i, task_i):
            for ci in range(cat_i, len(cats)):
                c = cats[ci]
                items = TASKS[c]
                start_i = task_i if ci == cat_i else 0
                for ti in range(start_i, len(items)):
                    if (c, items[ti]["id"]) not in done:
                        return {"category": c, "index": ti}
            return None

        cat_i = cats.index(cat)
        nxt = find_from(cat_i, index + 1)
        if nxt:
            return nxt
        return find_from(0, 0)

    def _due_items(self):
        today = datetime.date.today().isoformat()
        with self._db() as conn:
            rows = conn.execute("SELECT category, task_id, due FROM srs WHERE due <= ? ORDER BY due, category", (today,)).fetchall()
        out = []
        for cat, tid, due in rows:
            for i, t in enumerate(TASKS.get(cat, [])):
                if t["id"] == tid:
                    out.append({"category": cat, "index": i, "title": t["title"], "due": due})
        return out

    def get_review_status(self):
        items = self._due_items()
        with self._db() as conn:
            nxt = conn.execute("SELECT MIN(due) FROM srs WHERE due > ?", (datetime.date.today().isoformat(),)).fetchone()[0]
        return {"due": len(items), "items": items[:12], "next_due": nxt}

    def start_review(self):
        items = self._due_items()
        return items[0] if items else None

    def get_stats(self):
        with self._db() as conn:
            total_attempts = conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
            success = conn.execute("SELECT COUNT(*) FROM attempts WHERE status = 'success'").fetchone()[0]
            by_day = conn.execute(
                """SELECT date, COUNT(*) FROM attempts
                   WHERE date >= date('now', '-13 day')
                   GROUP BY date ORDER BY date"""
            ).fetchall()
            done_rows = conn.execute("SELECT category, task_id FROM progress WHERE completed = 1").fetchall()

        valid = _valid_pairs()
        completed = sum(1 for r in done_rows if (r[0], r[1]) in valid)
        success_rate = round(success / total_attempts * 100) if total_attempts else 0

        return {
            "total_attempts": total_attempts,
            "success_count": success,
            "success_rate": success_rate,
            "completed": completed,
            "total_tasks": TOTAL_TASKS,
            "by_day": [{"date": d, "count": c} for d, c in by_day],
            "streak_days": self._streak_days(),
            "by_category": self._by_category(),
            "review_due": len(self._due_items()),
        }

    def _streak_days(self):
        with self._db() as conn:
            days = {r[0] for r in conn.execute("SELECT DISTINCT date FROM attempts WHERE status = 'success'").fetchall()}
        d, n = datetime.date.today(), 0
        if d.isoformat() not in days:
            d -= datetime.timedelta(days=1)       # сегодня ещё можно успеть
        while d.isoformat() in days:
            n += 1
            d -= datetime.timedelta(days=1)
        return n

    def _by_category(self):
        with self._db() as conn:
            rows = conn.execute("SELECT category, task_id FROM progress WHERE completed = 1").fetchall()
        done = {}
        for cat, tid in rows:
            if (cat, tid) in _valid_pairs():
                done[cat] = done.get(cat, 0) + 1
        return [{"label": CATEGORY_LABELS.get(k, k), "done": done.get(k, 0), "total": len(v)} for k, v in TASKS.items()]


    # ---------- настройки интерфейса / маскот / помощник ----------
    _CFG_KEYS = {"theme", "char", "mascot_size", "mascot_on", "side_on", "asst_on"}

    def get_settings(self):
        with self._db() as conn:
            rows = dict(conn.execute("SELECT key, value FROM settings").fetchall())
        return {k[3:]: v for k, v in rows.items() if k.startswith("ui_") and k[3:] in self._CFG_KEYS}

    def set_setting(self, key, value):
        if key not in self._CFG_KEYS:
            return {"ok": False}
        with self._db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("ui_" + key, str(value)[:20])
            )
        return {"ok": True}

    # Чиби: каждый SVG уже содержит свою анимацию, мы лишь отдаём файл как есть.
    # Новый персонаж = просто положить name.svg в assets/chibi (или в <папка данных>/chibi).
    @staticmethod
    def _chibi_dirs():
        return [
            os.path.join(_data_dir(), "chibi"),
            os.path.join(_exe_dir(), "assets", "chibi"),
            _res("assets", "chibi"),
        ]

    def list_characters(self):
        seen = {}
        for d in self._chibi_dirs():
            try:
                names = sorted(os.listdir(d))
            except OSError:
                continue
            for fn in names:
                stem, ext = os.path.splitext(fn)
                if ext.lower() == ".svg" and stem not in seen:
                    seen[stem] = stem.replace("_", " ").replace("-", " ").title()
        return [{"id": k, "label": v} for k, v in seen.items()]

    def get_character(self, char_id):
        import re
        if not isinstance(char_id, str) or not re.fullmatch(r"[\w\-]+", char_id):
            return None
        for d in self._chibi_dirs():
            path = os.path.join(d, char_id + ".svg")
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except OSError:
                continue
        return None

    # ---------- помощница (полностью офлайн) ----------
    def _assistant(self):
        if getattr(self, "_asst", None) is None:
            self._asst = Assistant(_res("data", "kb"), unknown_log=os.path.join(_data_dir(), "unanswered.txt"))
        return self._asst

    def _assistant_ctx(self, ctx):
        """Дополняем контекст из интерфейса тем, что знает только сервер: текущая задача и прогресс."""
        ctx = dict(ctx or {})
        ctx["progress"] = self.get_overall_progress()
        ctx["review_due"] = len(self._due_items())
        if self.current:
            cat, index, task = self.current
            info = {"category": cat, "index": index, "id": task["id"], "title": task["title"], "kind": task.get("kind"),
                    "type": task["type"], "description": task.get("description", ""), "func_name": task.get("func_name")}
            if task["type"] == "function":
                info["examples"] = [f"{task['func_name']}({', '.join(map(repr, args))}) должна вернуть {exp!r}" for args, exp in task["tests"][:2]]
            ctx["task"] = info
        return ctx

    def ask_assistant(self, text, ctx=None):
        try:
            return self._assistant().reply(text, self._assistant_ctx(ctx))
        except Exception:
            return {"reply": "Я немного сбилась, но уже тут. Спроси ещё раз, пожалуйста.", "chips": [], "bubble": ""}

    def assistant_event(self, kind, ctx=None):
        try:
            return self._assistant().event(kind, self._assistant_ctx(ctx))
        except Exception:
            return {"bubble": "", "reply": ""}

    def assistant_idle(self, ctx=None):
        try:
            return self._assistant().idle(self._assistant_ctx(ctx))
        except Exception:
            return {"bubble": ""}

    def assistant_welcome(self, ctx=None):
        try:
            return self._assistant().welcome(self._assistant_ctx(ctx))
        except Exception:
            return {"reply": "Привет! Спрашивай про Python.", "bubble": "Привет!", "chips": []}


def main():
    webview.create_window(
        "Python Backend Trainer",
        html=build_html(),
        js_api=API(),
        width=1440,
        height=900,
        min_size=(1100, 680),
    )
    webview.start()


def selftest():
    """`python app.py --selftest` (или `SuperTrainer.exe --selftest`): проверка без окна. Ресурсы, база знаний, песочница."""
    import json

    report, ok = {}, True
    try:
        report["html_kb"] = len(build_html()) // 1024
        report["tasks"] = TOTAL_TASKS
        api = API()
        chars = [c["id"] for c in api.list_characters()]
        report["characters"] = chars
        svg = api.get_character(chars[0]) if chars else None
        report["svg_kb"] = len(svg) // 1024 if svg else 0
        a = api.ask_assistant("как добавить элемент в список", {"persona": "goth"})
        report["assistant_card"] = a.get("card")
        from sandbox import run_check, run_snippet

        report["snippet"] = run_snippet("2 ** 10", 6)["output"]
        t = TASKS["backend"][0]
        code = "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/ping')\ndef ping():\n    return {'status': 'ok'}"
        report["fastapi_check"] = run_check(code, t, 10)["status"]
        ok = (report["svg_kb"] > 100 and report["assistant_card"] == "list-append" and report["snippet"].strip() == "1024"
              and report["fastapi_check"] == "success" and len(chars) >= 1)
    except Exception:
        import traceback

        report["error"] = traceback.format_exc()
        ok = False
    print(json.dumps(report, ensure_ascii=False))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        if "--selftest" in sys.argv:
            selftest()
        else:
            main()
    except Exception:
        import traceback

        with open(os.path.join(_data_dir(), "crash.log"), "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
        raise
