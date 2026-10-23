import ast
import builtins
import difflib
import re



_ERR_LINE = re.compile(r"^\s*([A-Za-z_]*(?:Error|Exception|Warning|Exit|Interrupt)|StopIteration)\b:?\s*(.*)$")
_PY_START = re.compile(r"^\s*(def |class |for |while |if |elif |else:|try:|except|import |from \S+ import |return\b|print\(|@\w|with |lambda|async |await )")


def find_error(text: str):
    lines = text.strip().splitlines()
    for line in reversed(lines):
        m = _ERR_LINE.match(line.strip().lstrip("❌ ").strip())
        if m:
            msg = m.group(2).strip()
            ln = re.search(r"\((?:строка|line) (\d+)\)", msg) or re.search(r"line (\d+)", text)
            return m.group(1), re.sub(r"\s*\((?:строка|line) \d+\)\s*$", "", msg), int(ln.group(1)) if ln else None
    m = re.search(r"Синтаксическая ошибка:\s*(.*?)\s*\(строка (\d+)\)", text)
    if m:
        return "SyntaxError", m.group(1), int(m.group(2))
    return None


def looks_like_traceback(text: str) -> bool:
    return "Traceback (most recent call last)" in text or bool(find_error(text) and len(text.strip().splitlines()) <= 6
                                                                and _ERR_LINE.match(text.strip().splitlines()[-1].strip().lstrip("❌ ").strip() or ""))


def looks_like_code(text: str) -> bool:
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return False
    if "```" in text:
        return True
    score = 0
    for l in lines:
        if _PY_START.match(l):
            score += 2
        elif re.search(r"[\w\]\)]\s*=\s*[^=]", l) and not l.strip().endswith("?"):
            score += 1
        elif l.startswith(("    ", "\t")):
            score += 1
        elif re.search(r"\w\(.*\)", l):
            score += 1
    if len(lines) == 1:
        if re.match(r"^\s*[A-Za-z_]\w*\s*[+\-*/]?=\s*[^=\s]", lines[0]) and not re.search(r"[а-яё]{3}", lines[0].lower()):
            return True
        return score >= 2 or bool(re.fullmatch(r"[\w\.\[\]\(\)\s,'\"+\-*/%<>=!:]+", lines[0]) and re.search(r"\w\(.*\)|[+\-*/%]{1,2}|==|\[.*\]", lines[0])
                                  and not re.search(r"[а-яё]{3}", lines[0].lower()))
    return score >= max(2, len(lines))


def extract_code(text: str) -> str:
    m = re.findall(r"```(?:python|py)?\n?(.*?)```", text, re.S)
    if m:
        return "\n".join(m).strip("\n")
    return text.strip("\n")


def is_pure_expression(text: str) -> bool:
    t = text.strip()
    if not t or len(t) > 200 or "\n" in t or re.search(r"[а-яё]{3}", t.lower()):
        return False
    try:
        tree = ast.parse(t, mode="eval")
    except SyntaxError:
        return False
    return not isinstance(tree.body, (ast.Name, ast.Constant)) or (isinstance(tree.body, ast.Constant) and not isinstance(tree.body.value, str)
                                                                 and len(t) > 1 and not t.isdigit())



ERRORS = {
    "SyntaxError": ("Синтаксическая ошибка", "Python не смог прочитать код: где-то нарушена грамматика языка.",
                    ["Проверь двоеточие в конце `if`, `for`, `while`, `def`, `class`, `else`, `try`.",
                     "Посчитай скобки и кавычки: каждая открытая должна закрыться.",
                     "Одно `=` это присваивание, а сравнение пишется `==`."],
                    "if x == 5:      # двоеточие обязательно\n    print('пять')"),
    "IndentationError": ("Ошибка отступов", "Отступы в Python это часть синтаксиса: они показывают, что к чему относится.",
                         ["Тело `if`, `for`, `def` сдвигай ровно на 4 пробела.",
                          "Не смешивай пробелы и табуляцию, настрой редактор на пробелы.",
                          "После строки с двоеточием обязательно должна идти строка с отступом (хотя бы `pass`)."],
                         "def f():\n    return 1   # 4 пробела"),
    "NameError": ("Имя не найдено", "Ты используешь имя (переменную или функцию), которого Python не знает в этом месте.",
                  ["Проверь опечатки: `total` и `totl` для Python разные имена.",
                   "Переменную нужно создать до использования: сначала `x = 5`, потом `print(x)`.",
                   "Строки пишутся в кавычках: `print('привет')`, без кавычек `привет` Python считает именем."],
                  "name = 'Аня'\nprint(name)    # сначала создали, потом использовали"),
    "UnboundLocalError": ("Переменная используется до присваивания", "Внутри функции ты присваиваешь переменную, поэтому Python считает её локальной, а читаешь её раньше, чем она получила значение.",
                          ["Присвой значение до первого использования.", "Нужно менять внешнюю переменную? Лучше передай её параметром и верни результат."],
                          "def add(total, n):\n    total = total + n\n    return total"),
    "TypeError": ("Неподходящий тип", "Операция или функция получила значение не того типа.",
                  ["Нельзя складывать число и строку: `'a' + 1`. Приведи типы: `str(1)` или `int('1')`.",
                   "Проверь число аргументов функции: сколько в `def`, столько и при вызове.",
                   "Скобки `()` вызывают функцию, `[]` берут элемент. Не перепутай."],
                  "age = 25\nprint('Мне ' + str(age))"),
    "ValueError": ("Подходящий тип, но неподходящее значение", "Функция получила значение правильного типа, но с ним ничего нельзя сделать.",
                   ["`int('abc')` упадёт: в строке нет числа. Проверь строку заранее: `s.isdigit()`.",
                    "Распаковка `a, b = [1, 2, 3]` требует ровно столько переменных, сколько элементов."],
                   "s = '42'\nif s.isdigit():\n    n = int(s)"),
    "IndexError": ("Индекс за пределами", "Ты обращаешься к элементу, которого нет: индекс больше или равен длине списка.",
                   ["Индексы идут с 0: в списке из 3 элементов допустимы 0, 1, 2.",
                    "Последний элемент это `lst[-1]`, а не `lst[len(lst)]`.",
                    "Пустой список: сначала проверь `if lst:`."],
                   "lst = [10, 20, 30]\nprint(lst[2])    # последний, индекс 2"),
    "KeyError": ("Нет такого ключа", "В словаре нет ключа, к которому ты обращаешься через `d[key]`.",
                 ["Используй `d.get(key)`: вернёт `None` вместо ошибки (или `d.get(key, 0)` с запасным значением).",
                  "Проверь ключ заранее: `if key in d:`.",
                  "Ключи чувствительны к регистру и типу: `'1'` и `1` разные ключи."],
                 "d = {'a': 1}\nprint(d.get('b', 0))   # 0"),
    "AttributeError": ("Нет такого атрибута или метода", "У этого объекта нет метода или поля с таким именем.",
                       ["Проверь опечатку в названии метода и регистр (`Append` и `append` разные).",
                        "У `None` ничего нет: если видишь `'NoneType' object has no attribute`, значит, предыдущая функция вернула `None` (часто забыт `return`).",
                        "Методы списка не работают на строке и наоборот."],
                       "nums = []\nnums.append(1)"),
    "ZeroDivisionError": ("Деление на ноль", "Делитель оказался равен нулю.",
                          ["Проверь делитель до деления: `if b != 0:`.", "Или перехвати ошибку через `try / except ZeroDivisionError`."],
                          "try:\n    r = a / b\nexcept ZeroDivisionError:\n    r = None"),
    "RecursionError": ("Слишком глубокая рекурсия", "Функция вызывает сама себя бесконечно: нет условия остановки (базового случая) или оно никогда не срабатывает.",
                       ["Добавь базовый случай: `if n == 0: return 1`.", "Убедись, что аргумент в рекурсивном вызове приближается к базовому случаю."],
                       "def fact(n):\n    if n <= 1:\n        return 1\n    return n * fact(n - 1)"),
    "ModuleNotFoundError": ("Модуль не найден", "Python не нашёл такой модуль.",
                            ["В тренажёре доступны только `math`, `random`, `json`, `re`, `datetime`, `collections`, `itertools`, `functools`, `string`, `enum`, `typing`, `fastapi`, `pydantic`.",
                             "Проверь написание имени модуля."], "import math\nprint(math.sqrt(16))"),
    "ImportError": ("Не удалось импортировать", "Модуль есть, но запрошенного имени в нём нет.",
                    ["Проверь, что имя написано правильно и существует в этом модуле."], "from math import sqrt"),
    "StopIteration": ("Итератор закончился", "Ты вызвал `next()`, но элементов больше нет.",
                      ["Используй `next(it, None)`: вернёт запасное значение вместо ошибки.", "Обычно проще перебирать циклом `for`."], "it = iter([1])\nnext(it)\nnext(it, None)"),
    "AssertionError": ("Проверка assert не прошла", "Условие в `assert` оказалось ложным.", ["Посмотри на условие в `assert` и значения, которые в нём участвуют."], "assert 2 + 2 == 4"),
    "OverflowError": ("Слишком большое число", "Результат не помещается в тип.", ["Для очень больших целых используй `int` (они безразмерные), а не `float`."], "print(2 ** 100)"),
    "NotImplementedError": ("Метод не реализован", "Это заглушка: тело ещё не написано.", ["Замени `raise NotImplementedError` на настоящий код."], "def f():\n    return 42"),
    "RuntimeError": ("Ошибка времени выполнения", "Общая ошибка во время работы программы.", ["Читай текст сообщения после двоеточия: там обычно написана причина."], ""),
    "FileNotFoundError": ("Файл не найден", "В тренажёре работа с файлами отключена.", ["Данные для задач задавай прямо в коде: строкой или списком."], "text = 'a\\nb'\nlines = text.split('\\n')"),
    "Exception": ("Общая ошибка", "Возникло исключение.", ["Читай текст сообщения после двоеточия."], ""),
}
ERRORS["TabError"] = ERRORS["IndentationError"]
ERRORS["UnicodeDecodeError"] = ("Ошибка кодировки", "Байты нельзя прочитать как текст в этой кодировке.", ["Укажи правильную кодировку, чаще всего `utf-8`."], "")

_BUILTIN_NAMES = set(dir(builtins))


def _names_in(code):
    names = set()
    if not code:
        return names
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return set(re.findall(r"[A-Za-z_]\w*", code))
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            names.add(n.id)
        elif isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            names.add(n.name)
        elif isinstance(n, ast.arg):
            names.add(n.arg)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                names.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, ast.ExceptHandler) and n.name:
            names.add(n.name)
    return names


def _close(word, options, n=1, cutoff=0.7):
    return difflib.get_close_matches(word, sorted(options), n=n, cutoff=cutoff)


_SYNTAX_HINTS = [
    (r"expected ':'", "Не хватает двоеточия `:` в конце строки с `if`, `for`, `while`, `def`, `class`, `else`, `try` или `except`."),
    (r"invalid syntax\. Perhaps you forgot a comma", "Похоже, пропущена запятая, или скобки/кавычки закрыты не там. Посмотри на строку и на строку перед ней."),
    (r"Maybe you meant '==' instead of '='|cannot assign to", "В условии сравнение пишется двумя знаками равно `==`. Одно `=` это присваивание."),
    (r"unterminated string literal|unterminated triple", "Не закрыта кавычка: у строки должна быть и открывающая, и закрывающая кавычка одного вида."),
    (r"'\(' was never closed|'\[' was never closed|'\{' was never closed", "Открыта скобка, но не закрыта. Посчитай скобки в этой строке и в соседних."),
    (r"unmatched '\)'|unmatched '\]'|unmatched '\}'", "Лишняя закрывающая скобка: у неё нет пары."),
    (r"expected an indented block", "После строки с двоеточием должен идти код с отступом (4 пробела). Если пока пусто, поставь `pass`."),
    (r"unindent does not match|unexpected indent", "Отступы не совпадают: в одном блоке должно быть одинаковое число пробелов, лишний отступ без причины тоже ошибка."),
    (r"invalid decimal literal|invalid non-printable", "В числе или имени затесался лишний символ. Имена не могут начинаться с цифры и содержать пробелы."),
    (r"Missing parentheses in call to 'print'", "В Python 3 `print` это функция: пиши `print('текст')` со скобками."),
    (r"f-string", "Проблема в f-строке: выражение внутри `{}` должно быть корректным, а кавычки внутри не должны совпадать с внешними."),
    (r"invalid syntax", "Python не понял эту строку. Часто виноваты пропущенная скобка, запятая или двоеточие в этой или предыдущей строке, или лишнее слово."),
]


def explain_error(text: str, code: str = "") -> str:
    found = find_error(text)
    if not found:
        return ""
    etype, msg, line = found
    title, why, fixes, example = ERRORS.get(etype, ERRORS["Exception"])
    out = [f"**{etype}: {title}**" + (f" (строка {line})" if line else ""), why]
    lines = (code or "").splitlines()
    if line and 0 < line <= len(lines):
        out.append(f"Строка {line}: `{lines[line - 1].strip()}`")
    specific = []

    if etype in ("SyntaxError", "IndentationError", "TabError"):
        for pat, hint in _SYNTAX_HINTS:
            if re.search(pat, msg):
                specific.append(hint)
                break
    elif etype == "NameError":
        m = re.search(r"name '(\w+)' is not defined", msg)
        if m:
            name = m.group(1)
            near = _close(name, _names_in(code) | _BUILTIN_NAMES)
            specific.append(f"Имя `{name}` нигде не определено." + (f" Может, ты имел в виду `{near[0]}`?" if near else ""))
            if name in ("true", "false", "null"):
                specific.append("В Python логические значения пишутся с большой буквы: `True`, `False`, а пустое значение это `None`.")
            if name[:1].isupper() and name.lower() in _names_in(code):
                specific.append("Регистр важен: имена `Name` и `name` для Python разные.")
    elif etype == "TypeError":
        m = re.search(r"unsupported operand type\(s\) for ([^:]+): '(\w+)' and '(\w+)'", msg) or \
            re.search(r"can only concatenate (\w+) \(not \"(\w+)\"\) to (\w+)", msg)
        if "can only concatenate" in msg and m:
            specific.append("Нельзя соединять строку и число через `+`. Преврати число в строку: `str(n)`, либо используй f-строку: `f'{n}'`.")
        elif "unsupported operand" in msg and m:
            specific.append(f"Операцию `{m.group(1).strip()}` нельзя применить к типам `{m.group(2)}` и `{m.group(3)}`. Если это число в виде строки, преврати его через `int()`.")
        elif "not subscriptable" in msg:
            if "NoneType" in msg:
                specific.append("Ты пытаешься взять `[...]` у `None`: функция, которая должна вернуть список или строку, вернула `None`. Проверь, есть ли в ней `return`.")
            else:
                specific.append("У этого типа нельзя брать элемент через `[...]`. Скорее всего, это число или функция: проверь, что в переменной именно то, что ты думаешь.")
        elif "not callable" in msg:
            specific.append("Ты ставишь `()` после значения, которое не функция. Частая причина: переменная названа как функция (`sum = 5`, потом `sum(...)`). Переименуй переменную.")
        elif re.search(r"takes (\d+) positional arguments? but (\d+) (?:was|were) given", msg):
            a, b = re.search(r"takes (\d+) positional arguments? but (\d+)", msg).groups()
            specific.append(f"Функция принимает {a} арг., а ты передал {b}. Сравни число параметров в `def` и в вызове (для методов класса первым идёт `self`).")
        elif "missing" in msg and "required positional argument" in msg:
            specific.append("При вызове не хватает обязательных аргументов. Передай все параметры из `def` или задай им значения по умолчанию.")
        elif "not iterable" in msg:
            specific.append("По этому значению нельзя пройти циклом. Число, например, не итерируется: для повторов используй `range(n)`.")
        elif "does not support item assignment" in msg:
            specific.append("Строки и кортежи неизменяемы: `s[0] = 'x'` не сработает. Собери новую строку, например `'x' + s[1:]`.")
        elif "NoneType" in msg:
            specific.append("Где-то получилось `None`. Чаще всего функция печатала результат через `print`, но ничего не вернула через `return`.")
        elif "'int' object is not iterable" in msg:
            specific.append("`for i in 5` не работает: нужно `for i in range(5)`.")
    elif etype == "AttributeError":
        m = re.search(r"'(\w+)' object has no attribute '(\w+)'", msg)
        if m:
            tname, attr = m.groups()
            pool = {"list": dir(list), "str": dir(str), "dict": dir(dict), "int": dir(int), "set": dir(set), "tuple": dir(tuple), "float": dir(float)}.get(tname, [])
            near = _close(attr, [p for p in pool if not p.startswith("_")], cutoff=0.6)
            if tname == "NoneType":
                specific.append(f"Переменная содержит `None`, а у `None` нет `.{attr}`. Похоже, функция не вернула значение (нет `return`) или метод изменил список на месте и вернул `None` (так делают `sort()`, `append()`, `reverse()`).")
            else:
                hint = f"У типа `{tname}` нет метода `.{attr}`."
                if near:
                    hint += f" Возможно, нужен `.{near[0]}`."
                elif tname == "list" and attr in ("push", "add"):
                    hint += " Для списка добавление это `.append(x)`."
                specific.append(hint)
    elif etype == "IndexError":
        if "out of range" in msg:
            specific.append("Индекс больше, чем есть элементов. Для списка длины `n` допустимы индексы от `0` до `n-1`. Если перебираешь в цикле, проверь границы `range(...)`.")
    elif etype == "KeyError":
        specific.append(f"Ключа {msg or ''} нет в словаре. Безопаснее брать значение через `.get(ключ)`.")
    elif etype == "ValueError":
        if "invalid literal for int()" in msg:
            specific.append("Строка не похожа на целое число (`int('3.5')` и `int('abc')` падают). Для дроби сначала `float('3.5')`, затем `int(...)` при необходимости.")
        elif "not enough values to unpack" in msg or "too many values to unpack" in msg:
            specific.append("Число переменных слева не равно числу значений справа в распаковке.")
        elif "math domain error" in msg:
            specific.append("Функция из `math` получила недопустимое значение, например `sqrt` отрицательного числа или `log` нуля.")
    elif etype in ("ModuleNotFoundError", "ImportError"):
        m = re.search(r"No module named '([\w\.]+)'", msg)
        if m:
            specific.append(f"Модуль `{m.group(1)}` недоступен в тренажёре.")

    if specific:
        out += specific
    else:
        out.append("**Что проверить:**\n" + "\n".join(f"- {f}" for f in fixes))
    if example and not specific:
        out.append("```python\n" + example + "\n```")
    return "\n\n".join(out)


def explain_sandbox_message(text: str, code: str = "", task=None) -> str:
    t = text.strip()
    if "Превышено время" in t:
        return ("**Код выполняется слишком долго.** Почти всегда это бесконечный цикл.\n\n"
                "- В `while` условие должно когда-нибудь стать ложным: меняется ли переменная внутри цикла?\n"
                "- Нет ли `while True` без `break`?\n- Не вызывает ли функция сама себя без остановки?")
    m = re.search(r"Импорт (?:из )?модуля '([\w\.]+)' запрещён", t)
    if m:
        return (f"**Модуль `{m.group(1)}` в тренажёре недоступен.** Это сделано ради безопасности. Разрешены: `math`, `random`, `json`, `re`, "
                "`datetime`, `collections`, `itertools`, `functools`, `string`, `enum`, `typing`, `fastapi`, `pydantic`.")
    m = re.search(r"Использование '(\w+)' запрещено", t)
    if m:
        return f"**`{m.group(1)}` в тренажёре отключено.** Для задач оно не нужно: значения можно задавать прямо в коде."
    m = re.search(r"Функция '(\w+)' не найдена", t)
    if m:
        defined = [n.name for n in ast.walk(_safe_parse(code)) if isinstance(n, ast.FunctionDef)] if code else []
        extra = f" В твоём коде есть: {', '.join('`'+d+'`' for d in defined)}." if defined else " В коде нет ни одной `def`."
        return f"**Функция должна называться ровно `{m.group(1)}`.**{extra} Имя и регистр должны совпадать."
    if "Не найдена переменная app" in t:
        return "**Нужна переменная `app`.** Создай её так: `app = FastAPI()` (и импортируй `from fastapi import FastAPI`)."
    mm = re.search(r"вернула (.+?), ожидалось (.+)$", t, re.S)
    if mm:
        return diagnose_mismatch(mm.group(1).strip(), mm.group(2).strip())
    mm = re.search(r"Программа вывела:\n(.*?)\nОжидалось:\n(.*)$", t, re.S)
    if mm:
        return diagnose_mismatch(mm.group(1).strip(), mm.group(2).strip(), printed=True)
    mm = re.search(r"Ожидался статус (\d+), получен (\d+)", t)
    if mm:
        a, b = mm.groups()
        hint = {"404": "Такого адреса нет: проверь путь в декораторе и опечатки.", "405": "Метод не тот: сравни `@app.get`/`@app.post` с тем, что в задаче.",
                "422": "FastAPI отклонил данные: проверь типы параметров и модель Pydantic.", "500": "Внутренняя ошибка в твоей функции: посмотри, нет ли в ней исключения."}.get(b, "")
        return f"**Статус не тот: ждали {a}, получили {b}.** {hint}".strip()
    if t.startswith("❌ API вернул"):
        return "**API вернул не тот JSON.** Сравни ключи и значения в твоём `return` с ожидаемым ответом: имена ключей, регистр, типы (число или строка)."
    return ""


def _safe_parse(code):
    try:
        return ast.parse(code)
    except SyntaxError:
        return ast.parse("")


def diagnose_mismatch(got_repr: str, exp_repr: str, printed: bool = False) -> str:
    head = "**Результат не совпал с ожидаемым.**"
    try:
        got, exp = ast.literal_eval(got_repr), ast.literal_eval(exp_repr)
    except Exception:
        return head + f"\n\nПолучено: `{got_repr}`, ожидалось: `{exp_repr}`. Сравни их посимвольно."
    tips = []
    if got is None:
        tips.append("Функция вернула `None`: в ней нет `return`, или ты вывел результат через `print`, но не вернул его. В задачах с функциями результат нужно именно **вернуть**.")
    elif type(got) is not type(exp) and not (isinstance(got, (int, float)) and isinstance(exp, (int, float)) and not isinstance(got, bool)):
        tips.append(f"Типы разные: получен `{type(got).__name__}`, ожидается `{type(exp).__name__}`. Проверь приведение типов (`str()`, `int()`, `list()`).")
    if isinstance(got, str) and isinstance(exp, str):
        if got.lower() == exp.lower():
            tips.append("Отличается только регистр букв. Посмотри на `.upper()`, `.lower()`, `.capitalize()` и на сами строки.")
        elif got.strip() == exp.strip():
            tips.append("Лишние или недостающие пробелы / переводы строк по краям. Проверь `print(..., end=...)` и `.strip()`.")
        elif got.replace(" ", "") == exp.replace(" ", ""):
            tips.append("Отличаются только пробелы внутри строки.")
        elif exp.startswith(got):
            tips.append("Ответ обрывается раньше: не хватает конца строки.")
        elif got.startswith(exp):
            tips.append("В ответе есть лишнее в конце.")
    elif isinstance(got, (int, float)) and isinstance(exp, (int, float)) and not isinstance(got, bool) and not isinstance(exp, bool):
        d = got - exp
        if abs(d) == 1:
            tips.append("Ошибка ровно на единицу: классический *off-by-one*. Проверь границы: `range(n)` против `range(1, n + 1)`, `<` против `<=`, индекс `-1`.")
        elif isinstance(got, int) and isinstance(exp, int) and 0 <= got < exp:
            tips.append("Результат меньше ожидаемого: похоже, в подсчёт не попал первый или последний элемент. Проверь границы: `range(n)` идёт от 0 до n-1 и **не включает** n.")
        elif isinstance(got, int) and isinstance(exp, int) and got > exp > 0:
            tips.append("Результат больше ожидаемого: возможно, считается лишний элемент или условие пропускает то, что нужно отсеять.")
        elif exp != 0 and got == -exp:
            tips.append("Знак получился противоположным: проверь порядок вычитания.")
        elif isinstance(got, float) != isinstance(exp, float):
            tips.append("Число правильное, но тип другой: деление `/` даёт `float`, а целое деление `//` даёт `int`.")
    elif isinstance(got, (list, tuple)) and isinstance(exp, (list, tuple)):
        if sorted(map(repr, got)) == sorted(map(repr, exp)):
            tips.append("Элементы те же, но порядок другой. Проверь сортировку или порядок добавления.")
        elif len(got) == len(exp) + 1:
            tips.append("В результате на один элемент больше: проверь границы цикла и условие.")
        elif len(got) + 1 == len(exp):
            tips.append("Не хватает одного элемента: возможно, граница цикла отсекает последний или условие слишком строгое.")
        elif len(got) < len(exp):
            tips.append("Элементов меньше, чем нужно: условие фильтра, наверное, слишком строгое.")
        else:
            tips.append("Элементов больше, чем нужно: условие фильтра слишком мягкое или есть дубли.")
    elif isinstance(got, dict) and isinstance(exp, dict):
        missing = set(exp) - set(got)
        extra = set(got) - set(exp)
        if missing:
            tips.append("Не хватает ключей: " + ", ".join(f"`{k}`" for k in sorted(map(str, missing))) + ".")
        if extra:
            tips.append("Лишние ключи: " + ", ".join(f"`{k}`" for k in sorted(map(str, extra))) + ".")
        if not missing and not extra:
            diff = [k for k in exp if got.get(k) != exp[k]]
            tips.append("Ключи те же, но отличаются значения у: " + ", ".join(f"`{k}`" for k in map(str, diff)) + ".")
    elif isinstance(got, bool) and isinstance(exp, bool):
        tips.append("Условие работает наоборот: проверь знак сравнения и граничные значения (`>` против `>=`).")
    return head + f"\n\nПолучено: `{got_repr}`\nОжидалось: `{exp_repr}`" + ("\n\n" + "\n".join(f"- {t}" for t in tips) if tips else "")



SHADOWABLE = {"list", "dict", "set", "str", "int", "float", "sum", "max", "min", "len", "sorted", "type", "id", "input", "print",
              "range", "tuple", "map", "filter", "all", "any", "abs", "round", "zip", "bool", "next", "iter", "format"}


class Finding:
    def __init__(self, line, level, text):
        self.line, self.level, self.text = line, level, text

    def __repr__(self):
        return f"Finding({self.line}, {self.level!r}, {self.text!r})"


def lint(code: str, func_name: str = None, kind: str = None) -> list:
    out = []
    if not code or not code.strip():
        return [Finding(0, "info", "Код пока пустой.")]
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        hint = next((h for p, h in _SYNTAX_HINTS if re.search(p, e.msg or "")), "Python не понял эту строку.")
        return [Finding(e.lineno or 0, "error", f"Синтаксис: {e.msg}. {hint}")]

    if "___" in code:
        out.append(Finding(0, "warn", "В коде остались пропуски `___`: замени их на настоящий код."))
    meaningful = [n for n in tree.body if not (isinstance(n, ast.Pass) or (isinstance(n, ast.Expr) and isinstance(getattr(n, "value", None), ast.Constant)))]
    if not meaningful:
        out.append(Finding(0, "info", "Пока тут только заготовка. Напиши решение вместо `pass` и комментариев."))

    funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    if func_name and funcs and not any(f.name == func_name for f in funcs):
        names = ", ".join(f"`{f.name}`" for f in funcs)
        out.append(Finding(funcs[0].lineno, "error", f"Тренажёр ищет функцию `{func_name}`, а у тебя {names}. Имя должно совпадать точно."))
    elif func_name and not funcs and meaningful:
        out.append(Finding(0, "error", f"Нужна функция `{func_name}`, а в коде нет ни одной `def`."))

    bound = _names_in(code)
    for f in funcs:
        returns = [n for n in ast.walk(f) if isinstance(n, ast.Return) and n.value is not None]
        prints = [n for n in ast.walk(f) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "print"]
        body_real = [n for n in f.body if not isinstance(n, (ast.Pass,)) and not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
        if not returns and body_real and (func_name is None or f.name == func_name) and kind != "predict":
            if prints:
                out.append(Finding(f.lineno, "warn", f"В `{f.name}` результат печатается через `print`, но нигде не возвращается. Тренажёр проверяет значение, которое функция **возвращает**: используй `return`."))
            else:
                out.append(Finding(f.lineno, "warn", f"В `{f.name}` нет `return`, поэтому она вернёт `None`."))
        for d in f.args.defaults + f.args.kw_defaults:
            if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                out.append(Finding(d.lineno, "warn", "Изменяемое значение по умолчанию (`[]`, `{}`) создаётся один раз и общее для всех вызовов. Используй `None` и создавай список внутри функции."))
        for loop in [n for n in ast.walk(f) if isinstance(n, (ast.For, ast.While))]:
            if loop.body and isinstance(loop.body[-1], ast.Return) and not any(isinstance(x, ast.If) for x in loop.body):
                out.append(Finding(loop.lineno, "warn", "`return` в конце тела цикла завершит функцию уже после первого шага. Если нужно вернуть итог, ставь `return` после цикла."))

    seen_shadow = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) and n.id in SHADOWABLE and n.id not in seen_shadow:
            seen_shadow.add(n.id)
            out.append(Finding(n.lineno, "warn", f"Имя `{n.id}` уже занято встроенной функцией. После такого присваивания `{n.id}(...)` перестанет работать. Назови переменную иначе."))
        elif isinstance(n, ast.Compare):
            for op, c in zip(n.ops, n.comparators):
                if isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(c, ast.Constant) and c.value is None:
                    out.append(Finding(n.lineno, "style", "С `None` сравнивают через `is None` / `is not None`, а не `==`."))
                elif isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(c, ast.Constant) and isinstance(c.value, bool):
                    out.append(Finding(n.lineno, "style", "Не нужно сравнивать с `True`/`False`: пиши `if x:` или `if not x:`."))
                elif isinstance(op, (ast.Is, ast.IsNot)) and isinstance(c, ast.Constant) and c.value is not None and not isinstance(c.value, bool):
                    out.append(Finding(n.lineno, "warn", "`is` проверяет тождество объекта, а не равенство. Для чисел и строк используй `==`."))
        elif isinstance(n, ast.ExceptHandler) and n.type is None:
            out.append(Finding(n.lineno, "style", "Голый `except:` ловит вообще всё, даже опечатки. Указывай тип: `except ValueError:`."))
        elif isinstance(n, ast.While):
            has_exit = any(isinstance(x, (ast.Break, ast.Return)) for x in ast.walk(n))
            if isinstance(n.test, ast.Constant) and n.test.value is True and not has_exit:
                out.append(Finding(n.lineno, "error", "`while True` без `break` и `return` никогда не закончится."))
            elif not has_exit:
                cond_names = {x.id for x in ast.walk(n.test) if isinstance(x, ast.Name)}
                body_stores = {x.id for b in n.body for x in ast.walk(b) if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store)}
                if cond_names and not (cond_names & body_stores):
                    out.append(Finding(n.lineno, "error", f"В условии `while` участвуют {', '.join('`'+c+'`' for c in sorted(cond_names))}, но в теле цикла они не меняются. Цикл может не закончиться."))
        elif isinstance(n, ast.For):
            if isinstance(n.iter, ast.Name):
                for b in ast.walk(ast.Module(body=n.body, type_ignores=[])):
                    if isinstance(b, ast.Call) and isinstance(b.func, ast.Attribute) and isinstance(b.func.value, ast.Name) \
                            and b.func.value.id == n.iter.id and b.func.attr in ("remove", "append", "pop", "insert"):
                        out.append(Finding(n.lineno, "warn", f"Ты меняешь `{n.iter.id}` (`.{b.func.attr}`) прямо во время перебора: элементы будут пропускаться. Перебирай копию `{n.iter.id}[:]` или собирай результат в новый список."))
                        break
            if isinstance(n.iter, ast.Call) and isinstance(n.iter.func, ast.Name) and n.iter.func.id == "range" and n.iter.args \
                    and isinstance(n.iter.args[0], ast.Call) and isinstance(n.iter.args[0].func, ast.Name) and n.iter.args[0].func.id == "len":
                out.append(Finding(n.lineno, "style", "Вместо `range(len(x))` часто проще `for item in x:` или `for i, item in enumerate(x):`."))
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "input":
            out.append(Finding(n.lineno, "warn", "`input()` в тренажёре отключён: данные нужно задавать прямо в коде."))


    undefined = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in bound and n.id not in _BUILTIN_NAMES:
            undefined.setdefault(n.id, n.lineno)
    for name, ln in undefined.items():
        near = _close(name, bound | _BUILTIN_NAMES)
        out.append(Finding(ln, "error", f"Имя `{name}` нигде не определено" + (f", может, `{near[0]}`?" if near else ".") + " Это вызовет NameError."))

    order = {"error": 0, "warn": 1, "info": 2, "style": 3}
    out.sort(key=lambda f: (order[f.level], f.line))
    return out


def format_findings(findings, limit=6) -> str:
    icons = {"error": "🔴", "warn": "🟡", "info": "ℹ️", "style": "💡"}
    lines = []
    for f in findings[:limit]:
        where = f"строка {f.line}: " if f.line else ""
        lines.append(f"- {icons[f.level]} {where}{f.text}")
    if len(findings) > limit:
        lines.append(f"- …и ещё {len(findings) - limit}")
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------ объяснение кода

_BINOPS = {ast.Add: "сумма", ast.Sub: "разность", ast.Mult: "произведение", ast.Div: "деление", ast.FloorDiv: "целое деление",
           ast.Mod: "остаток от деления", ast.Pow: "возведение в степень"}
_CMPOPS = {ast.Eq: "равно", ast.NotEq: "не равно", ast.Lt: "меньше", ast.LtE: "меньше или равно", ast.Gt: "больше",
           ast.GtE: "больше или равно", ast.In: "содержится в", ast.NotIn: "не содержится в", ast.Is: "это тот же объект, что", ast.IsNot: "не тот же объект, что"}
_FUNCS = {"print": "выводит на экран", "len": "считает длину", "range": "создаёт последовательность чисел", "sum": "считает сумму",
          "max": "ищет максимум", "min": "ищет минимум", "sorted": "возвращает отсортированную копию", "str": "превращает в строку",
          "int": "превращает в целое число", "float": "превращает в дробное число", "list": "создаёт список", "dict": "создаёт словарь",
          "set": "создаёт множество", "round": "округляет", "abs": "берёт модуль", "enumerate": "выдаёт пары (номер, элемент)",
          "zip": "склеивает последовательности попарно", "reversed": "идёт в обратном порядке", "type": "узнаёт тип", "bool": "приводит к True/False"}
_METHODS = {"append": "добавляет в конец", "extend": "добавляет сразу несколько элементов", "pop": "достаёт и удаляет элемент", "remove": "удаляет первое совпадение",
            "sort": "сортирует на месте", "reverse": "разворачивает на месте", "upper": "переводит в верхний регистр", "lower": "переводит в нижний регистр",
            "strip": "убирает пробелы по краям", "split": "разбивает на части", "join": "склеивает части в строку", "replace": "заменяет часть строки",
            "get": "берёт значение по ключу (безопасно)", "keys": "даёт ключи", "values": "даёт значения", "items": "даёт пары ключ-значение",
            "startswith": "проверяет начало строки", "endswith": "проверяет конец строки", "format": "подставляет значения в шаблон",
            "find": "ищет позицию подстроки", "count": "считает вхождения", "add": "добавляет в множество", "insert": "вставляет на позицию",
            "index": "ищет позицию элемента", "copy": "делает копию", "update": "обновляет значениями из другого словаря"}


def u(node) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return "…"


def describe_expr(n) -> str:
    if isinstance(n, ast.Constant):
        return f"значение `{u(n)}`"
    if isinstance(n, ast.Name):
        return f"значение переменной `{n.id}`"
    if isinstance(n, ast.BinOp):
        return f"{_BINOPS.get(type(n.op), 'результат операции')} `{u(n)}`"
    if isinstance(n, ast.Compare):
        return f"проверка «{u(n)}» (даст `True` или `False`)"
    if isinstance(n, ast.BoolOp):
        return f"логическое {'«и»' if isinstance(n.op, ast.And) else '«или»'}: `{u(n)}`"
    if isinstance(n, ast.JoinedStr):
        return f"f-строка: в `{{}}` подставляются значения → `{u(n)}`"
    if isinstance(n, ast.ListComp):
        return f"списковое включение: новый список из `{u(n.elt)}` для каждого `{u(n.generators[0].target)}` из `{u(n.generators[0].iter)}`" + (" с условием" if n.generators[0].ifs else "")
    if isinstance(n, ast.Lambda):
        return f"маленькая функция без имени (`lambda`) от `{u(n.args)}`"
    if isinstance(n, ast.Subscript):
        return f"{'срез' if isinstance(n.slice, ast.Slice) else 'элемент по индексу/ключу'} `{u(n)}`"
    if isinstance(n, ast.Call):
        if isinstance(n.func, ast.Name):
            d = _FUNCS.get(n.func.id)
            return f"вызов `{n.func.id}`" + (f": {d}" if d else "") + f" → `{u(n)}`"
        if isinstance(n.func, ast.Attribute):
            d = _METHODS.get(n.func.attr)
            return f"метод `.{n.func.attr}()`" + (f": {d}" if d else "") + f" → `{u(n)}`"
    if isinstance(n, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
        kind = {"List": "список", "Tuple": "кортеж", "Set": "множество", "Dict": "словарь"}[type(n).__name__]
        return f"{kind} `{u(n)}`"
    return f"выражение `{u(n)}`"


def _range_values(call):
    try:
        args = [ast.literal_eval(a) for a in call.args]
        vals = list(range(*args))
        if len(vals) <= 8:
            return ", ".join(map(str, vals)) if vals else "ничего (пустой диапазон)"
        return ", ".join(map(str, vals[:4])) + f", …, {vals[-1]} (всего {len(vals)})"
    except Exception:
        return None


def explain_code(code: str, limit: int = 28) -> str:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"Я не смогла разобрать код: {e.msg} (строка {e.lineno}). Сначала поправь синтаксис."
    lines = []

    def walk(body, depth):
        pad = "  " * depth
        for n in body:
            if len(lines) >= limit:
                return
            ln = f"{pad}**{n.lineno}.** "
            if isinstance(n, ast.Assign):
                tgt = ", ".join(u(t) for t in n.targets)
                lines.append(f"{ln}Записываем в `{tgt}`: {describe_expr(n.value)}.")
            elif isinstance(n, ast.AugAssign):
                lines.append(f"{ln}Меняем `{u(n.target)}`: {_BINOPS.get(type(n.op), 'операция')} с `{u(n.value)}` (`{u(n)}`).")
            elif isinstance(n, ast.AnnAssign):
                lines.append(f"{ln}Объявляем `{u(n.target)}` с типом `{u(n.annotation)}`.")
            elif isinstance(n, ast.Expr):
                lines.append(f"{ln}Выполняем: {describe_expr(n.value)}.")
            elif isinstance(n, ast.For):
                extra = ""
                if isinstance(n.iter, ast.Call) and isinstance(n.iter.func, ast.Name) and n.iter.func.id == "range":
                    rv = _range_values(n.iter)
                    extra = f" (значения: {rv})" if rv else ""
                lines.append(f"{ln}Цикл `for`: `{u(n.target)}` по очереди берёт значения из `{u(n.iter)}`{extra}. Для каждого повторяем блок ниже.")
                walk(n.body, depth + 1)
            elif isinstance(n, ast.While):
                lines.append(f"{ln}Цикл `while`: пока `{u(n.test)}` истинно, повторяем блок ниже.")
                walk(n.body, depth + 1)
            elif isinstance(n, ast.If):
                lines.append(f"{ln}Если `{u(n.test)}`:")
                walk(n.body, depth + 1)
                orelse = n.orelse
                while len(orelse) == 1 and isinstance(orelse[0], ast.If):
                    lines.append(f"{pad}**{orelse[0].lineno}.** Иначе, если `{u(orelse[0].test)}`:")
                    walk(orelse[0].body, depth + 1)
                    orelse = orelse[0].orelse
                if orelse:
                    lines.append(f"{pad}Иначе:")
                    walk(orelse, depth + 1)
            elif isinstance(n, ast.FunctionDef):
                params = ", ".join(a.arg for a in n.args.args) or "без параметров"
                lines.append(f"{ln}Объявляем функцию `{n.name}` ({params}). Код внутри выполнится только при вызове.")
                walk(n.body, depth + 1)
            elif isinstance(n, ast.Return):
                lines.append(f"{ln}Возвращаем из функции " + (describe_expr(n.value) + "." if n.value is not None else "`None`."))
            elif isinstance(n, ast.Try):
                lines.append(f"{ln}Пробуем выполнить блок ниже.")
                walk(n.body, depth + 1)
                for h in n.handlers:
                    lines.append(f"{pad}**{h.lineno}.** Если случится `{u(h.type) if h.type else 'любая ошибка'}`:")
                    walk(h.body, depth + 1)
                if n.finalbody:
                    lines.append(f"{pad}В любом случае в конце:")
                    walk(n.finalbody, depth + 1)
            elif isinstance(n, ast.ClassDef):
                lines.append(f"{ln}Объявляем класс `{n.name}`, это шаблон для объектов.")
                walk(n.body, depth + 1)
            elif isinstance(n, (ast.Import, ast.ImportFrom)):
                lines.append(f"{ln}Подключаем: `{u(n)}`.")
            elif isinstance(n, ast.Raise):
                lines.append(f"{ln}Намеренно вызываем ошибку: `{u(n)}`.")
            elif isinstance(n, ast.Assert):
                lines.append(f"{ln}Проверяем, что `{u(n.test)}` истинно, иначе ошибка.")
            elif isinstance(n, ast.Break):
                lines.append(f"{ln}`break`: выходим из цикла.")
            elif isinstance(n, ast.Continue):
                lines.append(f"{ln}`continue`: переходим к следующему шагу цикла.")
            elif isinstance(n, ast.Pass):
                lines.append(f"{ln}`pass`: ничего не делаем (заглушка).")
            elif isinstance(n, ast.With):
                lines.append(f"{ln}Блок `with`: ресурс корректно закроется сам.")
                walk(n.body, depth + 1)
            else:
                lines.append(f"{ln}`{u(n).splitlines()[0]}`")

    walk(tree.body, 0)
    if len(lines) >= limit:
        lines.append("… (дальше код продолжается, покажи мне кусок поменьше)")
    return "\n".join(lines)


_INLINE_CALL = re.compile(r"((?:print|len|sorted|sum|max|min|range|list|str|int|float|type|round|abs|set|dict|tuple|bool|reversed|enumerate|zip)\s*\(.*\))")
_INLINE_ARITH = re.compile(r"(?<![\w.])([\d.(][\d.\s()+\-*/%]*[+\-*/%][\d.\s()+\-*/%]*\d\)?)")
_RUN_WORDS = ("выведет", "вывод", "результат", "получится", "будет", "равно", "равен", "посчитай", "вычисли", "output", "result", "evaluate", "чему")


def extract_inline_code(text: str):

    m = re.search(r"`([^`\n]+)`", text)
    if m:
        return m.group(1).strip()
    low = text.lower()
    if not any(w in low for w in _RUN_WORDS):
        return None
    m = _INLINE_CALL.search(text)
    if m:
        return m.group(1).strip().rstrip("?!.")
    m = _INLINE_ARITH.search(text)
    if m:
        return m.group(1).strip()
    return None
