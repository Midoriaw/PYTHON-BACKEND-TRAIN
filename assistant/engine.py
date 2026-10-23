import collections
import datetime
import os
import random
import re

from . import codehelp, kb, lexicon, nlp, persona

HI, MID = 0.60, 0.38
MAX_LEN = 2000

_EN_WORDS = set("how what why when where which is are can do does to a an the of in on for with and or not list dict string "
                "loop function class error example explain show sort add remove get find difference between vs please help".split())
_FOLLOW_START = ("а ", "и ", "ну а ", "а если ", "а для ", "а как ", "а в ", "а что ", "а у ", "and ", "what about ", "how about ")
_ACTION_STEMS = {nlp.stem(w) for w in
                 "добавить удалить найти сортировать перебрать проверить копировать объединить разбить заменить преобразовать длина развернуть получить вывести".split()}
_COMPARE = {nlp.stem(w) for w in "отличие отличается разница различие versus vs сравнить сравнение против difference".split()}


def _md_plain(s: str, n: int = 100) -> str:
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = re.sub(r"\*\*([^*]*)\*\*", r"\1", s)
    s = re.sub(r"\s+", " ", s).strip()
    m = re.match(r"(.{20,%d}?[.!?])(\s|$)" % n, s)
    if m:
        return m.group(1)
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _strip_md(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\*\*([^*]*)\*\*", r"\1", re.sub(r"`([^`]*)`", r"\1", s))).strip()


def is_english(text: str) -> bool:
    words = re.findall(r"[A-Za-z]+", text)
    if len(words) < 2 or re.search(r"[А-Яа-яЁё]", text):
        return False
    low = [w.lower() for w in words]
    return sum(1 for w in low if w in _EN_WORDS) >= 2 and not codehelp.looks_like_code(text)


class Assistant:
    def __init__(self, kb_dir: str, unknown_log: str = None, seed=None):
        self.cards = kb.load_dir(kb_dir)
        self.index = kb.Index(self.cards)
        self.rng = random.Random(seed)
        self.unknown_log = unknown_log
        self.last = None
        self.last_text = ""
        self.hist = collections.deque(maxlen=20)
        self.recent_idle = collections.deque(maxlen=14)
        self.tips = [c for c in self.cards if c.kind == "tip"]
        self.turns = 0
        self.errors = []


    def reply(self, text, ctx=None) -> dict:
        ctx = ctx or {}
        try:
            text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(text or ""))[:MAX_LEN]
            out = self._reply(text, ctx)
        except Exception as e:
            self.errors.append(repr(e))
            out = self._say(ctx, "Что-то у меня внутри сбойнуло, но я цела. Спроси ещё раз, пожалуйста, другими словами.", "confused")
        self.turns += 1
        self.hist.append((text, out.get("card")))
        out.setdefault("chips", [])
        out["bubble"] = out.get("bubble") or _md_plain(out.get("reply", ""))
        return out

    def event(self, kind: str, ctx=None) -> dict:
        ctx = ctx or {}
        p = ctx.get("persona")
        fails = int(ctx.get("fails") or 0)
        if kind == "success":
            streak = int(ctx.get("streak") or 0)
            msg = persona.line(p, "streak", self.rng) if streak >= 3 else persona.line(p, "praise", self.rng)
            done, total = ctx.get("progress", {}).get("completed"), ctx.get("progress", {}).get("total")
            if done and total and done == total:
                msg = "Всё решено! Ты прошёл весь курс. Теперь можно повторять и придумывать свои задачи."
            return {"bubble": msg, "reply": msg}
        if kind == "fail":
            msg = persona.line(p, "stuck" if fails >= 3 else "retry", self.rng)
            chips = [{"label": "Разобрать ошибку", "send": "что не так с моим кодом"}]
            if fails >= 3:
                chips.append({"label": "💡 Подсказка", "send": "@action:hint"})
            return {"bubble": msg, "reply": msg, "chips": chips if fails >= 2 else []}
        return {"bubble": "", "reply": ""}

    def idle(self, ctx=None) -> dict:
        ctx = ctx or {}
        p = ctx.get("persona")
        roll = self.rng.random()
        opts = []
        due = int(ctx.get("review_due") or 0)
        if due and self.rng.random() < 0.35:
            word = "задача" if due % 10 == 1 and due % 100 != 11 else "задачи" if due % 10 in (2, 3, 4) and not 11 <= due % 100 <= 14 else "задач"
            opts.append((f"На сегодня {due} {word} на повторение. Загляни в блок «Повторение» слева.", "review"))
        elif roll < 0.40 and self.tips:
            c = self.rng.choice(self.tips)
            opts.append(("💡 " + _strip_md(c.paras[0]), c.id))
        elif roll < 0.55:
            pr = ctx.get("progress") or {}
            if pr.get("total"):
                left = pr["total"] - pr.get("completed", 0)
                if left > 0:
                    opts.append((f"Осталось {left} из {pr['total']}. Идёшь хорошо.", "progress"))
        elif roll < 0.62:
            h = datetime.datetime.now().hour
            when = "Доброе утро" if 5 <= h < 12 else "Добрый день" if 12 <= h < 18 else "Добрый вечер" if 18 <= h < 23 else "Не рановато ли для кода? Ладно, давай"
            opts.append((when + ". Чем займёмся?", "time"))
        if not opts:
            opts.append((persona.line(p, "idle", self.rng), "idle"))
        for _ in range(6):
            text, key = opts[0]
            if text not in self.recent_idle:
                break
            opts = [(persona.line(p, "idle", self.rng), "idle")]
        self.recent_idle.append(opts[0][0])
        return {"bubble": opts[0][0], "reply": "", "chips": []}

    def welcome(self, ctx=None) -> dict:
        ctx = ctx or {}
        msg = persona.line(ctx.get("persona"), "hello", self.rng)
        chips = [{"label": "Что ты умеешь?", "send": "что ты умеешь"}, {"label": "Объясни задачу", "send": "объясни задачу"}]
        return {"reply": msg + " Спрашивай про синтаксис, ошибки или текущую задачу. Я понимаю и русский, и английский, и опечатки.", "bubble": msg, "chips": chips}


    def _say(self, ctx, text, kind=None, chips=None, **extra):
        out = {"reply": text, "chips": chips or [], "confidence": 1.0, **extra}
        return out

    def _reply(self, text, ctx) -> dict:
        t = text.strip()
        p = ctx.get("persona")
        if not t:
            return self._say(ctx, persona.line(p, "nudge", self.rng))


        if t.startswith("@card:"):
            c = self.index.by_id.get(t[6:].strip())
            return self._answer(c, "short", ctx) if c else self._say(ctx, "Такой карточки нет.")
        if t.startswith("@mode:"):
            return self._modify(t[6:].strip(), ctx)
        if t.startswith("@action:"):
            return self._command(t[8:].strip(), ctx, t)


        if codehelp.looks_like_traceback(t):
            return self._error_reply(t, ctx)


        code = None
        if "```" in t:
            code = codehelp.extract_code(t)
        elif codehelp.looks_like_code(t):
            code = t
        if code:
            return self._code_reply(t, code, ctx)

        inline = codehelp.extract_inline_code(t)
        if inline:
            try:
                compile(inline, "<chat>", "eval")
                return self._code_reply("что выведет", inline, ctx)
            except SyntaxError:
                pass


        toks = nlp.tokens(t)
        low = nlp.clean(t)
        mods = self._modifiers(toks)
        res = self.index.search(t, boost=self._follow_boost(low, toks), top=6)
        self.last_text = t


        meaningful = [s for s in res.qstems if s not in self._mod_stems()]
        if mods and not meaningful and self.last:
            return self._modify(mods[0], ctx)
        if not meaningful and self.last and len(toks) <= 3 and any(w in ("еще", "ещё", "дальше", "далее", "more", "next", "почему", "why") for w in toks):
            return self._modify("more", ctx)

        if not res.ranked:
            return self._unknown(t, res, ctx)
        top, score = res.ranked[0]
        if top.kind == "intent" and res.confidence >= MID:
            return self._command(top.id.replace("cmd-", "", 1), ctx, t)
        if top.kind == "chat" and res.confidence >= MID:
            return self._chat(top, ctx)


        mode = mods[0] if mods and mods[0] in ("example", "full", "simple") else "short"
        eng = is_english(t)

        alts = [c for c, sc in res.ranked[1:4] if c.kind not in ("intent", "chat") and sc >= score * 0.72][:2]
        if res.confidence >= HI:
            return self._answer(top, mode, ctx, english=eng, fixed=res.fixed, alts=alts)
        if res.confidence >= MID:
            alts = [c for c, _ in res.ranked[1:4] if c.kind not in ("intent", "chat")]
            margin = score - res.ranked[1][1] if len(res.ranked) > 1 else 1
            if margin > 0.12:
                out = self._answer(top, mode, ctx, english=eng, fixed=res.fixed, alts=alts)
                out["reply"] = f"Кажется, ты спрашиваешь про **{top.title}**.\n\n" + out["reply"]
                return out
            chips = [{"label": c.title, "send": f"@card:{c.id}"} for c in [top] + alts[:2]]
            return self._say(ctx, "Уточни, пожалуйста, ты имеешь в виду что-то из этого?", chips=chips, confidence=res.confidence, card=None)
        return self._unknown(t, res, ctx)


    def _mod_stems(self):
        return {nlp.stem(w) for w in (lexicon.WANT_EXAMPLE | lexicon.WANT_DETAILS | lexicon.WANT_SIMPLE)} | {"еще", "ещ", "дальш", "more"}

    def _modifiers(self, toks):
        out = []
        for w in toks:
            if w in lexicon.WANT_EXAMPLE or w.startswith("пример") or w in ("example", "examples", "snippet", "код"):
                out.append("example")
            elif w in lexicon.WANT_DETAILS or w.startswith("подробн") or w.startswith("детал"):
                out.append("full")
            elif w in lexicon.WANT_SIMPLE or w.startswith("прощ") or w.startswith("кратк") or w.startswith("коротк"):
                out.append("simple")
            elif w in ("еще", "дальше", "далее", "more"):
                out.append("more")
        return out

    def _follow_boost(self, low, toks):
        if self.last and (low.startswith(_FOLLOW_START) or len(toks) <= 3):
            tags = {nlp.stem(t) for t in self.last.tags} & _ACTION_STEMS
            return tags or None
        return None

    def _modify(self, mode, ctx):
        c = self.last
        if not c:
            return self._say(ctx, "Сначала задай вопрос, а потом я смогу показать пример или рассказать подробнее.",
                             chips=[{"label": "Что ты умеешь?", "send": "что ты умеешь"}])
        if mode == "more":
            rel = [self.index.by_id[r] for r in c.related if r in self.index.by_id]
            if rel:
                return self._answer(rel[0], "short", ctx)
            mode = "full"
        return self._answer(c, mode, ctx, remember=False)

    def _answer(self, card, mode, ctx, english=False, fixed="", remember=True, alts=None) -> dict:
        p = ctx.get("persona")
        if card is None:
            return self._unknown("", None, ctx)
        if remember:
            self.last = card
        beginner = int((ctx.get("progress") or {}).get("completed") or 0) < 8
        parts = []
        if card.kind == "chat":
            return self._chat(card, ctx)

        use_en = english and card.en
        if mode == "short" and fixed in ("layout", "typo"):
            pass
        if self.rng.random() < 0.35 and mode == "short":
            op = persona.line(p, "open", self.rng)
            if op:
                parts.append(op)
        parts.append(f"**{card.title}**")
        paras = [card.en] if use_en else card.paras
        if not paras:
            paras = ["(пока без описания)"]
        if mode in ("short", "simple"):
            parts.append(paras[0])
        elif mode == "example":
            parts.append(paras[0])
        else:
            parts += paras
        if english and not card.en:
            parts.append("_(Пока я отвечаю на английские вопросы по-русски, но синтаксис в примерах тот же.)_")

        ex = card.examples
        if ex:
            if mode == "full":
                shown = ex[:3]
            elif mode == "simple" and len(ex[0]) > 4:
                shown = []
            else:
                shown = ex[:1]
            for blk in shown:
                parts.append("```python\n" + "\n".join(blk) + "\n```")

        if mode == "full":
            parts += [f"⚠️ {x}" for x in card.pitfalls]
            parts += [f"💡 {x}" for x in card.tips]
        elif mode in ("short", "example") and beginner and card.pitfalls:
            parts.append(f"⚠️ {card.pitfalls[0]}")
        if mode == "short" and not beginner and card.tips and self.rng.random() < 0.4:
            parts.append(f"💡 {card.tips[0]}")
        if mode == "short" and self.rng.random() < 0.18:
            parts.append(persona.line(p, "close", self.rng))

        chips = []
        if len(ex) > 0 and mode == "short":
            chips.append({"label": "Ещё пример" if len(ex) > 1 else "Пример", "send": "@mode:example"})
        if mode != "full" and (len(card.paras) > 1 or card.pitfalls or card.tips or len(ex) > 1):
            chips.append({"label": "Подробнее", "send": "@mode:full"})
        for r in card.related[:2]:
            rc = self.index.by_id.get(r)
            if rc:
                chips.append({"label": rc.title, "send": f"@card:{rc.id}"})
        chips = chips[:3]
        have = {c["send"] for c in chips}
        for a in (alts or []):
            if f"@card:{a.id}" not in have:
                chips.append({"label": "Не то? " + a.title, "send": f"@card:{a.id}"})
        return {"reply": "\n\n".join(x for x in parts if x), "chips": chips[:5], "confidence": 1.0, "card": card.id,
                "bubble": _md_plain(paras[0])}

    def _chat(self, card, ctx):
        p = ctx.get("persona")
        pid = {"goth": "goth", "girl": "girl", "schoolgirl": "school"}.get(p, "")
        mine, generic = [], []
        for v in card.paras:
            m = re.match(r"\[(\w+)\]\s*(.*)", v)
            if m:
                if m.group(1) == pid:
                    mine.append(m.group(2))
            else:
                generic.append(v)
        pool = mine or generic or ["…"]
        text = self.rng.choice(pool)
        text = text.replace("{name}", persona.get(p)["label"])
        chips = [{"label": self.index.by_id[r].title, "send": f"@card:{r}"} for r in card.related[:3] if r in self.index.by_id]
        for blk in card.examples[:1]:
            pass
        return {"reply": text, "chips": chips, "confidence": 1.0, "card": card.id, "kind": "chat"}

    def _unknown(self, t, res, ctx):
        p = ctx.get("persona")
        if self.unknown_log and t:
            try:
                with open(self.unknown_log, "a", encoding="utf-8") as f:
                    f.write(t.replace("\n", " ")[:300] + "\n")
            except OSError:
                pass
        chips = []
        if res and res.ranked:
            chips = [{"label": c.title, "send": f"@card:{c.id}"} for c, _ in res.ranked[:3] if c.kind not in ("intent", "chat")]
        txt = persona.line(p, "confused", self.rng)
        if chips:
            txt += "\n\nБлижайшие темы:"
        else:
            chips = [{"label": "Что ты умеешь?", "send": "что ты умеешь"}]
        return {"reply": txt, "chips": chips, "confidence": 0.0, "card": None}


    def _task(self, ctx):
        return ctx.get("task") or {}

    def _error_reply(self, text, ctx):
        code = ctx.get("code", "")
        r = codehelp.explain_error(text, code) or codehelp.explain_sandbox_message(text, code)
        if not r:
            return self._say(ctx, "Это похоже на сообщение об ошибке, но я не смогла его разобрать. Скопируй последнюю строку целиком, например `NameError: name 'x' is not defined`.")
        return {"reply": r, "chips": [{"label": "Проверь мой код", "send": "что не так с моим кодом"}, {"label": "💡 Подсказка", "send": "@action:hint"}],
                "confidence": 1.0, "card": None, "kind": "error"}

    def _code_reply(self, text, code, ctx):
        from sandbox import run_snippet
        task = self._task(ctx)
        words = set(nlp.tokens(re.sub(r"```.*?```", " ", text, flags=re.S))) if "```" in text else set(nlp.tokens(text.replace(code, " ")))
        wants_explain = bool(words & {"объясни", "объяснить", "делает", "работает", "расскажи", "explain", "разбери", "понять"}) or any(w.startswith("объясн") for w in words)
        wants_bug = any(w.startswith(x) for w in words for x in ("ошиб", "баг", "прове", "работа", "почему", "исправ", "fix", "bug", "wrong")) and not wants_explain
        wants_out = any(w.startswith(x) for w in words for x in ("выведет", "вывод", "результат", "получится", "output"))
        parts = []
        if codehelp.is_pure_expression(code.strip()) or (wants_out and "\n" not in code.strip()):
            r = run_snippet(code, 3)
            tag = "Результат" if r["status"] == "success" else "Ошибка"
            parts.append(f"**{tag}:**\n```\n{r['output'].rstrip()}\n```")
            if r["status"] != "success":
                parts.append(codehelp.explain_error(r["output"], code) or "")
            return {"reply": "\n\n".join(x for x in parts if x), "chips": [], "confidence": 1.0, "card": None, "kind": "run"}

        findings = codehelp.lint(code, task.get("func_name") if task.get("type") == "function" else None, task.get("kind"))
        if wants_bug or not wants_explain:
            real = [f for f in findings if f.level in ("error", "warn")]
            if findings and (real or wants_bug):
                parts.append("**Что я вижу в коде:**\n" + codehelp.format_findings(findings))
        if wants_explain or not parts:
            parts.append("**Что делает код:**\n" + codehelp.explain_code(code))
        if wants_out or (wants_explain and not any(f.level == "error" for f in findings)):
            r = run_snippet(code, 3)
            if r["status"] == "success":
                parts.append("**Если запустить, выведется:**\n```\n" + r["output"].rstrip() + "\n```")
            elif not any(f.level == "error" for f in findings):
                parts.append("**При запуске получается ошибка:**\n" + (codehelp.explain_error(r["output"], code) or r["output"]))
        if not findings and wants_bug:
            parts.append("Явных проблем статический анализ не нашёл. Запусти код и посмотри на вывод, а если там ошибка, пришли её мне.")
        return {"reply": "\n\n".join(parts), "chips": [{"label": "Объясни по шагам", "send": "объясни мой код"}] if not wants_explain else [],
                "confidence": 1.0, "card": None, "kind": "code"}


    def _command(self, name, ctx, raw=""):
        p = ctx.get("persona")
        task = self._task(ctx)
        code, out_text, status = ctx.get("code", ""), ctx.get("output", ""), ctx.get("status")

        if name in ("hint", "next", "run"):
            msg = {"hint": "Открываю следующую подсказку.", "next": "Идём к следующей задаче.", "run": "Запускаю проверку."}[name]
            if name == "hint" and task.get("type") == "quiz":
                msg = "Это вопрос без кода. Читай программу сверху вниз и записывай на бумаге, чему равна каждая переменная после каждой строки."
                return self._say(ctx, msg)
            return {"reply": msg, "action": name, "chips": [], "confidence": 1.0, "card": None}

        if name == "give-answer":
            pre = {"goth": "Готовый ответ не дам, сам потом не запомнишь.", "girl": "Решение не покажу, но помогу дойти до него вместе!",
                   "schoolgirl": "Списывать нельзя, но я помогу разобраться."}.get(p, "Готовое решение не покажу, но помогу дойти до него.")
            return {"reply": pre + " Начнём с подсказки.", "action": "hint", "chips": [{"label": "Объясни задачу", "send": "@action:explain-task"}], "confidence": 1.0, "card": None}

        if name == "explain-task":
            return self._explain_task(ctx)

        if name in ("check-code", "what-error"):
            return self._check_current(ctx)

        if name == "explain-code":
            if not code.strip():
                return self._say(ctx, "В редакторе пока пусто. Напиши код или вставь его сюда, и я объясню по шагам.")
            return {"reply": "**Что делает твой код:**\n" + codehelp.explain_code(code), "chips": [], "confidence": 1.0, "card": None, "kind": "code"}

        if name == "progress":
            pr = ctx.get("progress") or {}
            if pr.get("total"):
                done, tot = pr.get("completed", 0), pr["total"]
                pct = round(done / tot * 100)
                tail = "Курс пройден!" if done == tot else ("Только начало, всё впереди." if pct < 15 else "Хороший темп." if pct < 60 else "Финишная прямая.")
                return self._say(ctx, f"Решено **{done} из {tot}** ({pct}%). {tail}")
            return self._say(ctx, "Статистику пока не вижу, но слева внизу есть полоса прогресса.")

        if name == "reset":
            return self._say(ctx, "Вернуть заготовку можно кнопкой «Сбросить» над редактором. Твой код тогда заменится стартовым шаблоном.")

        if name == "capabilities":
            txt = ("Вот что я умею:\n\n"
                   "- **Отвечать на вопросы** про Python, структуры данных, ООП, ошибки, FastAPI, HTTP и SQL. Опечатки, неверная раскладка и транслит не проблема.\n"
                   "- **Разбирать ошибки:** вставь текст ошибки или нажми «Проверь мой код».\n"
                   "- **Объяснять код** по шагам: вставь его в чат.\n"
                   "- **Считать выражения** прямо в чате, например `2**10` или `'abc'[::-1]`.\n"
                   "- **Помогать с задачей:** подсказки, план решения, разбор расхождений с ожидаемым.\n"
                   "- Просто поболтать, если нужен перерыв.")
            chips = [{"label": "Объясни задачу", "send": "@action:explain-task"}, {"label": "Проверь мой код", "send": "что не так с моим кодом"},
                     {"label": "Чем list отличается от tuple?", "send": "чем list отличается от tuple"}]
            return {"reply": txt, "chips": chips, "confidence": 1.0, "card": None}

        if name == "stuck":
            tip = persona.line(p, "stuck", self.rng)
            chips = [{"label": "Объясни задачу", "send": "@action:explain-task"}, {"label": "💡 Подсказка", "send": "@action:hint"}]
            return {"reply": tip + "\n\nМожно начать с подсказки или с разбора условия.", "chips": chips, "confidence": 1.0, "card": None}


        c = self.index.by_id.get("cmd-" + name)
        if c:
            return self._chat(c, ctx)
        return self._say(ctx, persona.line(p, "confused", self.rng))

    def _explain_task(self, ctx):
        task = self._task(ctx)
        if not task or not task.get("title"):
            return self._say(ctx, "Сначала выбери задачу слева, и я помогу разобрать условие.")
        typ, kind = task.get("type"), task.get("kind")
        parts = [f"**Задача: {task['title']}**", task.get("description", "")]
        if typ == "function":
            fn = task.get("func_name", "функция")
            parts.append(f"**План:**\n1. Объяви `def {fn}(...)`: параметры и их порядок смотри в условии.\n2. Реши на бумаге один пример из условия.\n3. Запиши это шагами и верни результат через `return` (не `print`).")
        elif typ == "stdout":
            parts.append("**План:**\n1. Выясни, что именно должно появиться на экране, до символа.\n2. Выведи это через `print(...)`.\n3. Если строк несколько, помни, что каждый `print` печатает на новой строке.")
        elif typ == "fastapi":
            parts.append("**План:**\n1. Выбери декоратор: `@app.get`, `@app.post`, `@app.put` и адрес.\n2. Опиши параметры функции (из пути, запроса или тела).\n3. Верни `dict`, FastAPI превратит его в JSON.")
        elif typ == "quiz":
            parts.append("**План:** читай код сверху вниз, после каждой строки записывай значения переменных. Потом сравни итог с вариантами.")
        if kind == "fill":
            parts.append("Это задача с пропусками: найди все `___` и подумай, что именно там должно стоять по смыслу комментария.")
        if kind == "bug":
            parts.append("Это поиск ошибки: запусти код, посмотри, чем результат отличается от ожидаемого, и найди строку, которая его даёт.")
        ex = task.get("examples")
        if ex:
            parts.append("**Примеры того, что проверят:**\n" + "\n".join(f"- {e}" for e in ex[:3]))
        chips = [{"label": "💡 Подсказка", "send": "@action:hint"}]
        return {"reply": "\n\n".join(x for x in parts if x), "chips": chips, "confidence": 1.0, "card": None, "kind": "task"}

    def _check_current(self, ctx):
        code, out_text, status = ctx.get("code", ""), ctx.get("output", ""), ctx.get("status")
        task = self._task(ctx)
        parts = []
        if out_text and status in ("fail", "error"):
            r = codehelp.explain_error(out_text, code) or codehelp.explain_sandbox_message(out_text, code, task)
            if r:
                parts.append(r)
        if code.strip():
            findings = codehelp.lint(code, task.get("func_name") if task.get("type") == "function" else None, task.get("kind"))
            real = [f for f in findings if f.level in ("error", "warn")]
            if real or (findings and not parts):
                parts.append("**Замечания к коду:**\n" + codehelp.format_findings(findings))
        if not parts:
            if status == "success":
                parts.append("Задача уже решена, замечаний нет. Можно переходить дальше.")
            elif not code.strip():
                parts.append("В редакторе пока пусто. Напиши решение и запусти проверку.")
            else:
                parts.append("Явных проблем в коде я не вижу. Запусти проверку: если будет ошибка или несовпадение, я разберу его.")
        return {"reply": "\n\n".join(parts), "chips": [{"label": "💡 Подсказка", "send": "@action:hint"}, {"label": "Объясни задачу", "send": "@action:explain-task"}],
                "confidence": 1.0, "card": None, "kind": "check"}
