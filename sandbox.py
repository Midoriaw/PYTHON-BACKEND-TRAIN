import ast
import io
import contextlib
import multiprocessing
import traceback



ALLOWED_MODULES = {
    "fastapi", "pydantic", "typing", "math", "datetime", "re", "json",
    "collections", "itertools", "functools", "random", "string", "enum",
}

FORBIDDEN_NAMES = {
    "__import__", "__builtins__", "__globals__", "__getattribute__",
    "__subclasses__", "__bases__", "__base__", "__mro__", "__class__",
    "__dict__", "__loader__", "__spec__", "__code__", "__closure__",
    "eval", "exec", "compile", "open", "input", "vars", "locals", "globals",
    "getattr", "setattr", "delattr", "breakpoint", "memoryview",
}


class SandboxError(Exception):
    """Код нарушает правила безопасности песочницы."""
    pass


class _SafetyVisitor(ast.NodeVisitor):
    """Проходит по AST и ищет запрещённые конструкции."""

    def visit_Import(self, node):
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root not in ALLOWED_MODULES:
                raise SandboxError(f"Импорт модуля '{alias.name}' запрещён в тренажёре.")
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        root = (node.module or "").split(".")[0]
        if root not in ALLOWED_MODULES:
            raise SandboxError(f"Импорт из модуля '{node.module}' запрещён в тренажёре.")
        self.generic_visit(node)

    def visit_Name(self, node):
        if node.id in FORBIDDEN_NAMES:
            raise SandboxError(f"Использование '{node.id}' запрещено в тренажёре.")
        self.generic_visit(node)

    def visit_Attribute(self, node):
        if node.attr in FORBIDDEN_NAMES or (node.attr.startswith("__") and node.attr.endswith("__")):
            raise SandboxError(f"Обращение к атрибуту '{node.attr}' запрещено в тренажёре.")
        self.generic_visit(node)


def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    """Разрешает импорт только модулей из ALLOWED_MODULES.
    AST-проверка (_SafetyVisitor) уже отсеивает запрещённые импорты на этапе
    парсинга, эта функция — второй рубеж защиты на этапе исполнения."""
    root = name.split(".")[0]
    if root not in ALLOWED_MODULES:
        raise SandboxError(f"Импорт модуля '{name}' запрещён в тренажёре.")
    import builtins as _b
    return _b.__import__(name, globals, locals, fromlist, level)


def _safe_builtins():
    """Урезанный набор builtins — без файлов, импорта, eval/exec."""
    import builtins as _b
    allowed = [
        "abs", "all", "any", "bool", "chr", "dict", "divmod", "enumerate",
        "filter", "float", "format", "frozenset", "hash", "hex", "int",
        "isinstance", "issubclass", "iter", "len", "list", "map", "max",
        "min", "next", "oct", "ord", "pow", "print", "range", "repr",
        "reversed", "round", "set", "slice", "sorted", "str", "sum", "tuple",
        "type", "zip", "True", "False", "None",
        "Exception", "BaseException", "ValueError", "TypeError", "KeyError",
        "IndexError", "ZeroDivisionError", "StopIteration", "AttributeError",
        "RuntimeError", "NotImplementedError", "ArithmeticError", "OverflowError",
        "AssertionError", "StopAsyncIteration",
    ]
    result = {name: getattr(_b, name) for name in allowed if hasattr(_b, name)}
    result["__import__"] = _safe_import
    result["__build_class__"] = _b.__build_class__
    return result


def check_syntax_and_safety(code: str):
    """Быстрая проверка на синтаксис/запрещённые конструкции без выполнения.
    Возвращает None если всё ок, иначе строку с описанием ошибки."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"Синтаксическая ошибка: {e.msg} (строка {e.lineno})"
    try:
        _SafetyVisitor().visit(tree)
    except SandboxError as e:
        return str(e)
    return None


def _run_function_task(env, task):
    func = env.get(task["func_name"])
    if not callable(func):
        return {"status": "fail", "output": f"❌ Функция '{task['func_name']}' не найдена. Проверь название."}

    for args, expected in task["tests"]:
        try:
            result = func(*args)
        except Exception:
            short = _fmt_exc()
            return {"status": "fail", "output": f"❌ Ошибка при вызове с аргументами {args}:\n{short}"}
        if result != expected:
            return {
                "status": "fail",
                "output": f"❌ {task['func_name']}{args} вернула {result!r}, ожидалось {expected!r}",
            }
    return {"status": "success", "output": "✅ Все тесты пройдены! Отличная работа."}


def _normalize_stdout(s: str) -> str:
    """Убирает различия, которые не должны влиять на результат:
    регистр букв и лишние пробелы по краям каждой строки."""
    lines = s.split("\n")
    return "\n".join(line.strip() for line in lines).casefold()


def _run_stdout_task(code, env, task):
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(code, "<user_code>", "exec"), env)
    except Exception:
        short = _fmt_exc()
        return {"status": "error", "output": f"❌ Ошибка выполнения:\n{short}"}

    actual = buf.getvalue().rstrip("\n")
    expected = task["expected_stdout"]
    accepted = [expected, *task.get("expected_stdout_alternatives", [])]

    norm_actual = _normalize_stdout(actual)
    if not any(norm_actual == _normalize_stdout(candidate) for candidate in accepted):
        return {
            "status": "fail",
            "output": f"❌ Программа вывела:\n{actual!r}\nОжидалось:\n{expected!r}",
        }
    return {"status": "success", "output": "✅ Вывод совпадает! Отличная работа."}


def _fastapi_one_check(client, c, label):
    """Один запрос к приложению. Возвращает словарь с ошибкой или None, если всё верно."""
    method = c.get("method", "GET").lower()
    payload = c.get("payload")
    headers = c.get("headers")
    try:
        call = getattr(client, method)
        if payload is not None:
            resp = call(c["endpoint"], json=payload, headers=headers)
        else:
            resp = call(c["endpoint"], headers=headers)
    except Exception:
        short = _fmt_exc()
        return {"status": "error", "output": f"❌ {label}Ошибка при обращении к эндпоинту:\n{short}"}

    expected_status = c.get("expected_status")
    if expected_status is not None and resp.status_code != expected_status:
        return {
            "status": "fail",
            "output": f"❌ {label}Ожидался статус {expected_status}, получен {resp.status_code}\nТело ответа: {resp.text[:300]}",
        }

    expected_json = c.get("expected_json")
    if expected_json is not None:
        try:
            body = resp.json()
        except Exception:
            return {"status": "fail", "output": f"❌ {label}Ответ не является JSON: {resp.text[:300]}"}
        if body != expected_json:
            return {"status": "fail", "output": f"❌ {label}API вернул: {body}\nОжидалось: {expected_json}"}
    return None


def _run_fastapi_task(env, task):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = env.get("app")
    if not isinstance(app, FastAPI):
        return {"status": "fail", "output": "❌ Не найдена переменная app = FastAPI()."}

    client = TestClient(app)
    # Задача может содержать список checks: несколько запросов подряд (защита от ответов «под один тест»)
    checks = task.get("checks") or [task]
    for c in checks:
        label = f"Запрос {c.get('method', 'GET')} {c['endpoint']}\n" if len(checks) > 1 else ""
        problem = _fastapi_one_check(client, c, label)
        if problem:
            return problem

    return {"status": "success", "output": "✅ Эндпоинт работает правильно!"}


def _fmt_exc():
    """Последняя строка traceback + номер строки в коде ученика (если есть)."""
    import sys
    last = traceback.format_exc().strip().splitlines()[-1]
    for fr in reversed(traceback.extract_tb(sys.exc_info()[2])):
        if fr.filename == "<user_code>":
            return f"{last} (строка {fr.lineno})"
    return last


def _run_snippet(code, env):
    """Режим REPL для чата: выполняет код, печатает вывод; значение последнего выражения показывает через repr."""
    buf = io.StringIO()
    tree = ast.parse(code)
    last = None
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last = ast.Expression(tree.body.pop().value)
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(tree, "<user_code>", "exec"), env)
            if last is not None:
                val = eval(compile(last, "<user_code>", "eval"), env)
                if val is not None:
                    print(repr(val))
    except Exception:
        out = buf.getvalue()[:1500]
        return {"status": "error", "output": (out + "\n" if out else "") + _fmt_exc()}
    return {"status": "success", "output": buf.getvalue()[:3000] or "(код выполнен, ничего не выведено)"}


def _worker(code, task, conn):
    try:
        safety_issue = check_syntax_and_safety(code)
        if safety_issue:
            conn.send({"status": "error", "output": f"❌ {safety_issue}"})
            return

        env = {"__builtins__": _safe_builtins(), "__name__": "__main__"}

        if task["type"] == "snippet":
            result = _run_snippet(code, env)
        elif task["type"] == "stdout":
            result = _run_stdout_task(code, env, task)
        else:
            try:
                exec(compile(code, "<user_code>", "exec"), env)
            except Exception:
                short = _fmt_exc()
                conn.send({"status": "error", "output": f"❌ Ошибка выполнения:\n{short}"})
                return

            if task["type"] == "function":
                result = _run_function_task(env, task)
            elif task["type"] == "fastapi":
                result = _run_fastapi_task(env, task)
            else:
                result = {"status": "error", "output": f"Неизвестный тип задачи: {task['type']}"}

        conn.send(result)
    except Exception:
        conn.send({"status": "error", "output": f"❌ Внутренняя ошибка:\n{traceback.format_exc().strip().splitlines()[-1]}"})
    finally:
        conn.close()


def run_check(code: str, task: dict, timeout: float = 5.0) -> dict:
    """Выполняет код студента в изолированном процессе с таймаутом.
    Возвращает {"status": "success"|"fail"|"error", "output": str}."""

    if not code or not code.strip():
        return {"status": "error", "output": "✏️ Сначала напиши код в редакторе."}

    parent_conn, child_conn = multiprocessing.Pipe()
    proc = multiprocessing.Process(target=_worker, args=(code, task, child_conn), daemon=True)
    proc.start()
    child_conn.close()

    proc.join(timeout)
    if proc.is_alive():
        proc.terminate()
        proc.join(1)
        return {
            "status": "error",
            "output": f"⏱ Превышено время выполнения ({timeout:.0f} сек). Проверь код на бесконечный цикл.",
        }

    if parent_conn.poll():
        return parent_conn.recv()

    return {"status": "error", "output": "❌ Процесс проверки завершился аварийно (возможно, сработала защита ОС)."}


def run_snippet(code: str, timeout: float = 3.0) -> dict:
    """Безопасно выполняет короткий фрагмент из чата (те же ограничения, что у задач)."""
    return run_check(code, {"type": "snippet"}, timeout)
