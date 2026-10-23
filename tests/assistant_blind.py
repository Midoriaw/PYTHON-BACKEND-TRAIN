import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from assistant import nlp
from assistant.engine import Assistant

A = Assistant(os.path.join(ROOT, "data", "kb"), seed=4)
CASES = [
    ("не понимаю зачем в функции нужен return", "return-vs-print def-basic"),
    ("как узнать самый большой элемент в списке чисел", "abs-min-max-sum list-sum-avg algo-max-manual"),
    ("можно ли в списке хранить разные типы", "list-basics"),
    ("как получить последние три элемента", "list-slice"),
    ("хочу вывести текст без перехода на новую строку", "print-sep-end"),
    ("как в python возвести двойку в десятую степень", "power-op"),
    ("посчитать среднее арифметическое чисел", "list-sum-avg"),
    ("как найти позицию элемента в списке", "list-search"),
    ("зачем нужны скобки у кортежа с одним элементом", "tuple-basics"),
    ("как создать пустой словарь и пустое множество", "set-basics dict-basics cmp-dict-set"),
    ("какой тип у числа с точкой", "numbers-int-float types-basic"),
    ("как сравнить две строки без учёта регистра", "string-methods string-basics"),
    ("можно ли вложить цикл в цикл", "nested-loops"),
    ("как остановить бесконечный цикл", "while-loop break-continue"),
    ("что делает оператор not", "logic-ops"),
    ("как проверить что список пустой", "truthy-falsy"),
    ("как работает тернарный оператор", "ternary-expr"),
    ("что такое docstring", "comments"),
    ("как узнать тип переменной", "type-func"),
    ("как красиво оформить код чтобы он читался", "pep8 naming"),
    ("зачем нужен self в методах", "class-basic"),
    ("как вывести объект класса красиво", "dunder-str"),
    ("что такое генераторное выражение", "generator-expr generator-basic"),
    ("как сделать свойство только для чтения", "property-basic"),
    ("как сделать декоратор который логирует вызовы", "decorators-basic"),
    ("ошибка unsupported operand type int and str", "errors-typeerror"),
    ("как прочитать traceback", "errors-read-traceback"),
    ("что делать если программа зависла", "while-loop errors-recursion"),
    ("как поймать только деление на ноль", "errors-zerodivision try-except"),
    ("кортеж или список что быстрее", "list-vs-tuple"),
    ("чем множество отличается от списка", "set-basics cmp-dict-set list-vs-tuple"),
    ("сколько раз встречается каждый элемент в списке", "counter-basic dict-count-words list-count-len"),
    ("как сгруппировать слова по первой букве", "dict-setdefault"),
    ("как создать копию словаря", "list-copy cmp-copy-deepcopy"),
    ("как вставить элемент в начало списка", "list-insert"),
    ("как написать тест для функции", "testing-basic"),
    ("как установить библиотеку для python", "venv-pip"),
    ("как написать get запрос в fastapi", "fastapi-routes"),
    ("как получить параметр из адреса", "fastapi-path-params fastapi-query-params"),
    ("что такое валидация данных", "fastapi-validation pydantic-basic"),
    ("как сделать общую логику для нескольких эндпоинтов", "fastapi-depends"),
    ("чем async def отличается от обычной функции", "fastapi-async cmp-sync-async asyncio-basic"),
    ("как посмотреть документацию своего api", "fastapi-docs"),
    ("как проверить эндпоинт без запуска сервера", "fastapi-testing"),
    ("что такое rest", "rest-api"),
    ("зачем нужен заголовок authorization", "http-headers auth-basics"),
    ("как выбрать несколько колонок из таблицы", "sql-select"),
    ("как посчитать количество строк в группе", "sql-group-by"),
    ("что такое внешний ключ", "sql-join primary-key-index"),
    ("где хранить пароли от базы", "env-variables"),
    ("зачем нужен gitignore", "git-basics"),
    ("how to find the length of a list", "len-func"),
    ("what is the difference between a set and a dict", "cmp-dict-set set-basics"),
    ("how do i write an if else statement", "if-else"),
    ("how to catch an error in python", "try-except"),
    ("what is an f string", "fstring-basic"),
    ("how to import a module", "import-basic"),
    ("what does return do", "return-vs-print def-basic"),
    ("как сделать spisok iz chisel", "list-basics list-comprehension"),
    ("chto takoe klass", "class-basic"),
    ("как пользоватся словорем", "dict-basics dict-get"),
    ("как удалить символ из строки", "string-methods string-immutable"),
    ("чему равно 10 // 3", "cmp-div floordiv-mod"),
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
print(f"СЛЕПОЙ набор: {n} запросов, top1 = {ok1 / n:.0%}, top3 = {ok3 / n:.0%}")
for m in miss:
    print("  ", m)
