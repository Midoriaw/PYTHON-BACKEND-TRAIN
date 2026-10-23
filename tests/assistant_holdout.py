"""Свежий набор запросов, НЕ использовавшийся при настройке поиска: показывает реальное качество на незнакомых формулировках."""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from assistant import nlp  # noqa: E402
from assistant.engine import Assistant  # noqa: E402

A = Assistant(os.path.join(ROOT, "data", "kb"), seed=3)
CASES = [
    ("а как в питоне положить новое значение в конец массива", "list-append"),
    ("хочу выкинуть последний элемент списка", "list-remove"),
    ("как расположить числа от меньшего к большему", "list-sort"),
    ("как узнать сколько символов в тексте", "len-func"),
    ("можно ли поменять букву в строке", "string-immutable"),
    ("как из строки получить список слов", "string-split-join"),
    ("как склеить слова в предложение", "string-split-join"),
    ("как сделать так чтобы переменная была в верхнем регистре", "string-methods"),
    ("для чего нужны фигурные скобки в print(f'')", "fstring-basic"),
    ("как округлять до сотых", "round-func fstring-format-spec"),
    ("почему 0.1+0.2 не ровно 0.3", "float-precision"),
    ("как проверить что число делится на 3 без остатка", "floordiv-mod"),
    ("зачем нужен continue", "break-continue"),
    ("как пройти по списку и узнать номер каждого элемента", "enumerate-func"),
    ("как перебрать ключи и значения", "dict-iterate"),
    ("как посчитать сколько раз буква встречается в слове", "string-find-count counter-basic dict-count-words"),
    ("как проверить есть ли ключ в словаре", "dict-get in-operator"),
    ("что будет если обратиться к несуществующему индексу", "errors-indexerror"),
    ("почему пишет name is not defined", "errors-nameerror"),
    ("почему функция возвращает None", "return-vs-print errors-attributeerror none-type"),
    ("как написать функцию которая принимает любое количество аргументов", "args-kwargs"),
    ("что такое анонимная функция", "lambda-basic"),
    ("как сделать функцию которая вызывает сама себя", "recursion-basic"),
    ("как создать свой тип данных", "class-basic dataclass-basic"),
    ("как вызвать метод родителя", "inheritance-basic"),
    ("как выбросить собственную ошибку", "raise-basic"),
    ("как превратить словарь в строку json", "json-basic"),
    ("как найти все числа в тексте регулярным выражением", "regex-basic"),
    ("как перебрать все комбинации из списка", "itertools-basic"),
    ("как пометить параметр необязательным в fastapi", "fastapi-query-params"),
    ("как защитить эндпоинт токеном", "auth-basics fastapi-depends"),
    ("почему браузер блокирует запрос к моему api", "cors-basic"),
    ("как отдать клиенту код 201", "fastapi-status-code http-status-codes"),
    ("как не отдавать пароль в ответе", "fastapi-response-model"),
    ("как подключить базу данных к fastapi", "db-session orm-basics"),
    ("как разделить приложение на несколько файлов", "fastapi-router"),
    ("как загрузить файл на сервер", "fastapi-form-file"),
    ("что такое джойн", "sql-join"),
    ("как удалить все записи из таблицы", "sql-insert-update"),
    ("как не допустить sql инъекции", "sql-injection"),
    ("как закоммитить изменения", "git-basics"),
    ("как упаковать приложение в контейнер", "docker-basics"),
    ("как узнать какая сейчас дата", "datetime-basic"),
    ("как выбрать случайный элемент", "random-module"),
    ("где взять корень из числа", "power-op math-module"),
    ("как быстро проверить принадлежность элемента", "in-operator tip-in-set"),
    ("чем отличается копия списка от ссылки", "list-copy"),
    ("как создать матрицу", "list-matrix"),
    ("как удалить дубли но сохранить порядок", "remove-duplicates"),
    ("как поменять местами значения двух переменных", "multiple-assign"),
    ("write a function that returns a value", "def-basic return-vs-print"),
    ("how do i loop over a dictionary", "dict-iterate"),
    ("how to check if key exists in dict", "dict-get in-operator"),
    ("what is the difference between append and extend", "list-extend list-append"),
    ("explain list slicing", "list-slice string-index-slice"),
    ("how to convert string to int", "convert-types"),
    ("how does a for loop work", "for-loop"),
    ("what is pydantic model", "pydantic-basic fastapi-body"),
    ("how to start uvicorn server", "fastapi-run"),
    ("разница между put и patch", "cmp-put-patch http-methods"),
    ("как cделать цыкл по спсику", "for-loop"),
    ("кaк добaвить в списoк", "list-append"),
    (nlp.layout_to_lat("как проверить что строка число"), "is-number-string"),
    ("kak sdelat tsikl", "for-loop while-loop"),
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
print(f"свежий набор: {n} запросов, top1 = {ok1 / n:.0%}, top3 = {ok3 / n:.0%}")
for m in miss:
    print("  ", m)
