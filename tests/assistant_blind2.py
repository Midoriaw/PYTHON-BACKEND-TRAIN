"""Второй слепой набор (написан после правок по первому). Прогоняется один раз и показывает честное качество."""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from assistant.engine import Assistant  # noqa: E402

A = Assistant(os.path.join(ROOT, "data", "kb"), seed=5)
CASES = [
    ("как выводить значения переменных рядом с текстом", "fstring-basic print-basic"),
    ("в чем разница между целым и дробным числом", "numbers-int-float"),
    ("как превратить список слов в одну строку", "string-split-join"),
    ("как получить второй символ строки", "string-index-slice"),
    ("как перебрать буквы в слове", "for-loop"),
    ("как остановить цикл когда найден нужный элемент", "break-continue for-else"),
    ("как получить пары из двух списков", "zip-func"),
    ("как поменять порядок элементов на обратный", "list-reverse"),
    ("почему список изменился хотя я его не трогал", "list-copy list-mutable-default"),
    ("как слить два словаря в один", "dict-merge"),
    ("как сделать словарь из ключей и значений", "dict-create"),
    ("как посмотреть все значения словаря", "dict-iterate"),
    ("как создать множество из списка", "set-basics remove-duplicates"),
    ("чем отличается == от is", "is-vs-eq"),
    ("как написать несколько условий в if", "logic-ops if-else"),
    ("как ограничить число в диапазоне", "chained-compare"),
    ("как сделать функцию с параметром по умолчанию", "default-args"),
    ("как обернуть функцию в декоратор", "decorators-basic"),
    ("что делает yield", "generator-basic"),
    ("как работает наследование классов", "inheritance-basic"),
    ("как создать класс с полями", "class-basic dataclass-basic"),
    ("как поймать несколько типов ошибок", "try-except"),
    ("что делать с ошибкой list index out of range", "errors-indexerror"),
    ("ошибка keyerror при чтении словаря", "errors-keyerror dict-get"),
    ("ошибка indentationerror unexpected indent", "errors-indentation indentation"),
    ("как работает функция sorted с key", "sorted-key"),
    ("как найти числа в строке через re", "regex-basic"),
    ("что такое модуль collections", "counter-basic dict-setdefault stack-queue"),
    ("как переделать json в объект python", "json-basic"),
    ("как подключить fastapi к базе sqlalchemy", "db-session orm-basics"),
    ("как описать тело запроса в fastapi", "fastapi-body"),
    ("как сделать ограничения на поля pydantic", "pydantic-basic fastapi-validation"),
    ("как вернуть ошибку 400 из fastapi", "fastapi-httpexception http-status-codes"),
    ("как узнать почему вернулся 422", "fastapi-validation http-status-codes"),
    ("как настроить cors в fastapi", "cors-basic"),
    ("как запускать фоновые задачи после ответа", "fastapi-background"),
    ("что делает uvicorn", "fastapi-run"),
    ("как сделать join двух таблиц", "sql-join"),
    ("что такое индекс в базе данных", "primary-key-index"),
    ("чем delete отличается от drop", "sql-insert-update"),
    ("как написать dockerfile для python", "docker-basics"),
    ("как создать ветку в git", "git-basics"),
    ("как не хранить секреты в коде", "env-variables"),
    ("как пользоваться pytest", "testing-basic"),
    ("какая сложность у бинарного поиска", "algo-binary-search algo-complexity"),
    ("как найти простые числа до ста", "algo-prime"),
    ("как посчитать n-ое число фибоначчи", "algo-fibonacci"),
    ("что такое lambda и зачем она", "lambda-basic"),
    ("how to merge two dictionaries", "dict-merge"),
    ("what is a tuple", "tuple-basics"),
    ("how to check if a string is a number", "is-number-string"),
    ("how to use enumerate", "enumerate-func"),
    ("fastapi dependency injection", "fastapi-depends"),
    ("how to return json from endpoint", "fastapi-routes"),
    ("kak sozdat funkciyu v python", "def-basic"),
    ("как исползовать lamda", "lambda-basic"),
    ("как сдлать копию списка", "list-copy"),
]
ok1 = ok3 = 0
miss = []
for q, ids in CASES:
    want = set(ids.split())
    res = A.index.search(q, top=3)
    got = [c.id for c, _ in res.ranked]
    ok1 += bool(got) and got[0] in want
    ok3 += bool(set(got) & want)
    if not (got and got[0] in want):
        miss.append((q, sorted(want), got[:3], round(res.confidence, 2)))
n = len(CASES)
print(f"СЛЕПОЙ набор №2: {n} запросов, top1 = {ok1 / n:.0%}, top3 = {ok3 / n:.0%}")
for m in miss:
    print("  ", m)
