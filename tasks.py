"""Загрузчик задач. Сами задачи лежат в data/tasks/<категория>.json, их можно править руками.

Формат задачи (общие поля):
  id, title, kind (write | fill | bug | predict), difficulty 1..5, description, hints[], cheat[]  (шпаргалка, строки кода)
Типы проверки (type):
  stdout   : template[], expected_stdout
  function : template[], func_name, tests [[[аргументы], ожидаемое], ...]
  fastapi  : template[], endpoint, method, payload?, headers?, expected_status?, expected_json?
  quiz     : code[], options[], answer (индекс верного), explain
Многострочные поля (template, cheat, code) хранятся как список строк.
"""
import json
import os
import sys

CATEGORY_LABELS = {
    "python_basics": "Основы Python",
    "data_structures": "Структуры данных",
    "algorithms": "Мини-алгоритмы",
    "backend": "FastAPI",
}
CATEGORY_ORDER = list(CATEGORY_LABELS)


def _base() -> str:
    return sys._MEIPASS if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))


def _prepare(raw: dict) -> dict:
    t = dict(raw)
    for key in ("template", "cheat", "code"):
        if isinstance(t.get(key), list):
            t[key] = "\n".join(t[key]) + ("\n" if key == "template" else "")
    if "tests" in t:
        t["tests"] = [(tuple(args), expected) for args, expected in t["tests"]]
    return t


def _load(category: str) -> list:
    path = os.path.join(_base(), "data", "tasks", category + ".json")
    with open(path, "r", encoding="utf-8") as f:
        return [_prepare(item) for item in json.load(f)]


TASKS = {cat: _load(cat) for cat in CATEGORY_ORDER}
TOTAL_TASKS = sum(len(v) for v in TASKS.values())
