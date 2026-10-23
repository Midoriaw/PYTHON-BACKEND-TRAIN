"""Оценка качества помощницы. Запуск из корня проекта:  python tests/assistant_eval.py [-v]
Печатает точность по группам запросов и список промахов. Годится как регрессионный тест: добавляй сюда новые запросы."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from assistant import kb, nlp  # noqa: E402
from assistant.engine import Assistant, HI, MID  # noqa: E402

A = Assistant(os.path.join(ROOT, "data", "kb"), seed=1)
IDX = A.index

# (запрос, допустимые id)
NORMAL = [
    ("как добавить элемент в список", "list-append"), ("как удалить элемент из списка", "list-remove"),
    ("как отсортировать список", "list-sort"), ("как перевернуть строку", "string-reverse"),
    ("как узнать длину списка", "len-func"), ("что такое словарь в питоне", "dict-basics"),
    ("как получить значение из словаря по ключу", "dict-get"), ("как убрать дубликаты из списка", "remove-duplicates"),
    ("как посчитать сколько раз встречается слово", "dict-count-words counter-basic"), ("как перебрать словарь", "dict-iterate"),
    ("что такое цикл for", "for-loop"), ("как работает range", "range-func"), ("как сделать бесконечный цикл", "while-loop"),
    ("как выйти из цикла", "break-continue"), ("как проверить число на чётность", "floordiv-mod"),
    ("как вывести число с двумя знаками после запятой", "fstring-format-spec round-func"), ("как округлить число", "round-func"),
    ("как преобразовать строку в число", "convert-types"), ("что такое f-строка", "fstring-basic"),
    ("как разбить строку на слова", "string-split-join"), ("как объединить два списка", "list-extend"),
    ("чем отличается список от кортежа", "list-vs-tuple"), ("что такое множество", "set-basics"),
    ("общие элементы двух списков", "set-operations"), ("что такое функция", "def-basic"),
    ("чем отличается return от print", "return-vs-print"), ("что такое lambda", "lambda-basic"),
    ("что такое *args", "args-kwargs"), ("что такое класс", "class-basic"), ("что такое self", "class-basic"),
    ("как работает наследование", "inheritance-basic"), ("как обработать ошибку", "try-except"),
    ("что значит KeyError", "errors-keyerror"), ("list index out of range", "errors-indexerror"),
    ("что такое генератор", "generator-basic"), ("что такое декоратор", "decorators-basic"),
    ("как прочитать json", "json-basic"), ("что такое pydantic", "pydantic-basic"),
    ("как вернуть 404 в fastapi", "fastapi-httpexception"), ("как принять json в fastapi", "fastapi-body"),
    ("что такое query параметры", "fastapi-query-params"), ("как запустить fastapi", "fastapi-run"),
    ("что такое rest api", "rest-api"), ("чем отличается get от post", "http-methods"),
    ("что значит ошибка 422", "http-status-codes fastapi-validation"), ("что такое join в sql", "sql-join"),
    ("как проверить палиндром", "algo-palindrome"), ("fizzbuzz", "algo-fizzbuzz"),
    ("как проверить простое число", "algo-prime"), ("числа фибоначчи", "algo-fibonacci"),
    ("как найти максимум в списке", "abs-min-max-sum list-sum-avg algo-max-manual"),
    ("как работает срез", "string-index-slice list-slice"), ("как скопировать список", "list-copy"),
    ("что такое None", "none-type"), ("зачем нужен if __name__ == '__main__'", "if-name-main"),
    ("как создать виртуальное окружение", "venv-pip"), ("что такое docker", "docker-basics"),
    ("как закомментировать код", "comments"), ("как поменять местами две переменные", "multiple-assign"),
    ("что такое рекурсия", "recursion-basic"), ("как сделать список в одну строку", "list-comprehension"),
    ("как сортировать по ключу", "sorted-key"), ("что делает enumerate", "enumerate-func"),
    ("как пройти по двум спискам одновременно", "zip-func"), ("что такое async await", "asyncio-basic fastapi-async"),
    ("как использовать depends", "fastapi-depends"), ("как написать тест", "testing-basic"),
    ("что такое git commit", "git-basics"), ("как работает оператор in", "in-operator"),
    ("в чём разница между is и ==", "is-vs-eq"), ("как считать остаток от деления", "floordiv-mod"),
    ("как возвести число в степень", "power-op"), ("как работает try except finally", "try-except"),
    ("как создать пустой список", "list-basics"), ("как удалить ключ из словаря", "dict-delete"),
    ("как объединить два словаря", "dict-merge"), ("как использовать sqlalchemy", "orm-basics"),
    ("как получить текущую дату", "datetime-basic"), ("как сгенерировать случайное число", "random-module"),
]
TYPOS = [
    ("как добавить элемнт в спсиок", "list-append"), ("как удалить эллемент из списка", "list-remove"),
    ("как отсортирывать список", "list-sort"), ("что такое слорварь", "dict-basics"),
    ("как перевернуть сторку", "string-reverse"), ("что такое цыкл for", "for-loop"),
    ("как рабоатет range", "range-func"), ("что такое функцыя", "def-basic"),
    ("чем отличаеться список от кортежа", "list-vs-tuple"), ("как обработать ошибку try excpet", "try-except"),
    ("что такое декаратор", "decorators-basic"), ("как вернуть 404 в fastpai", "fastapi-httpexception"),
    ("что такое пайдантик", "pydantic-basic"), ("как окрулить число", "round-func"),
    ("как преабразовать строку в число", "convert-types"), ("что такое множесво", "set-basics"),
    ("keyerorr", "errors-keyerror"), ("idnex out of range", "errors-indexerror"),
    ("namerror name is not defined", "errors-nameerror"), ("как работатет while", "while-loop"),
    ("что такое класс и обьект", "class-basic"), ("как сделать спиок в одну строку", "list-comprehension"),
    ("как посчитать длинну строки", "len-func"), ("как разбить строку на слава", "string-split-join"),
    ("палиндрм", "algo-palindrome"), ("fibonaci", "algo-fibonacci"), ("как скопироать список", "list-copy"),
    ("что такое лямда", "lambda-basic"), ("как создать фнкцию", "def-basic"), ("кортеж", "tuple-basics"),
]
_LAYOUT_SRC = [
    ("как добавить элемент в список", "list-append"), ("что такое словарь", "dict-basics"),
    ("как отсортировать список", "list-sort"), ("как перевернуть строку", "string-reverse"),
    ("что такое функция", "def-basic"), ("как обработать ошибку", "try-except"),
    ("как удалить элемент из списка", "list-remove"), ("что такое цикл", "for-loop while-loop"),
    ("как округлить число", "round-func"), ("что такое множество", "set-basics"),
    ("чем отличается список от кортежа", "list-vs-tuple"), ("как получить значение из словаря", "dict-get"),
]
LAYOUT = [(nlp.layout_to_lat(q), ids) for q, ids in _LAYOUT_SRC]
TRANSLIT = [
    ("kak dobavit element v spisok", "list-append"), ("chto takoe slovar", "dict-basics"),
    ("kak otsortirovat spisok", "list-sort"), ("kak razvernut stroku", "string-reverse list-reverse"),
    ("chto takoe funkciya", "def-basic"), ("kak obrabotat oshibku", "try-except"),
    ("chem otlichaetsya spisok ot kortezha", "list-vs-tuple"), ("kak ubrat dublikaty iz spiska", "remove-duplicates"),
    ("kak perebrat slovar", "dict-iterate"), ("chto takoe tsikl for", "for-loop"),
    ("kak okruglit chislo", "round-func"), ("kak udalit element iz spiska", "list-remove"),
]
ENGLISH = [
    ("how to add element to list", "list-append"), ("what is a dictionary", "dict-basics"),
    ("how to sort a list", "list-sort"), ("difference between list and tuple", "list-vs-tuple"),
    ("how to reverse a string", "string-reverse"), ("what is a lambda function", "lambda-basic"),
    ("how to handle exceptions", "try-except"), ("how to read json", "json-basic"),
    ("list comprehension", "list-comprehension"), ("how to remove duplicates from list", "remove-duplicates"),
    ("what is a decorator", "decorators-basic"), ("fastapi path parameters", "fastapi-path-params"),
    ("how to return 404 in fastapi", "fastapi-httpexception"), ("what does enumerate do", "enumerate-func"),
    ("python f string format", "fstring-basic fstring-format-spec"), ("how to copy a list", "list-copy"),
    ("sort vs sorted", "list-sort sorted-func"), ("what is recursion", "recursion-basic"),
]
MIXED = [
    ("как сделать list comprehension", "list-comprehension"), ("как работает dict get", "dict-get"),
    ("что такое try except", "try-except"), ("как использовать append", "list-append"),
    ("sort и sorted отличия", "list-sort sorted-func"), ("как сделать pydantic модель", "fastapi-body pydantic-basic"),
    ("как работает enumerate в python", "enumerate-func"), ("что такое args и kwargs", "args-kwargs"),
]
GROUPS = [("обычные вопросы", NORMAL), ("опечатки", TYPOS), ("неверная раскладка", LAYOUT), ("транслит", TRANSLIT),
          ("английский", ENGLISH), ("смесь RU+EN", MIXED)]

# команды и разговор: (запрос, проверка)
ENGINE_CASES = [
    ("дай подсказку", lambda o: o.get("action") == "hint"), ("подскажи", lambda o: o.get("action") == "hint"),
    ("следующая задача", lambda o: o.get("action") == "next"), ("запусти код", lambda o: o.get("action") == "run"),
    ("что ты умеешь", lambda o: "умею" in o["reply"]), ("что ты можешь", lambda o: "умею" in o["reply"]),
    ("проверь мой код", lambda o: o.get("kind") == "check"), ("объясни задачу", lambda o: True),
    ("мой прогресс", lambda o: "Решено" in o["reply"] or "прогресс" in o["reply"].lower() or "Статистику" in o["reply"]),
    ("привет", lambda o: o.get("card") == "chat-hello"), (nlp.layout_to_lat("привет"), lambda o: o.get("card") == "chat-hello"),
    ("прив", lambda o: o.get("card") == "chat-hello"), ("спасибо", lambda o: o.get("card") == "chat-thanks"),
    ("пока", lambda o: o.get("card") == "chat-bye"), ("расскажи шутку", lambda o: o.get("card") == "chat-joke"),
    ("ты нейросеть?", lambda o: o.get("card") == "chat-ai"), ("я устал", lambda o: o.get("card") == "chat-tired"),
    ("ничего не получается", lambda o: o.get("reply", "") != "" and ("подсказ" in o["reply"].lower() or o.get("card") == "cmd-stuck")),
    ("реши за меня", lambda o: o.get("action") == "hint"), ("как дела", lambda o: o.get("card") == "chat-howare"),
    ("кто ты", lambda o: o.get("card") == "chat-who"), ("hello", lambda o: o.get("card") == "chat-hello"),
    ("thanks", lambda o: o.get("card") == "chat-thanks"), ("ты тупая", lambda o: o.get("card") == "chat-insult"),
    ("2**10", lambda o: "1024" in o["reply"]), ("len([1,2,3])", lambda o: "3" in o["reply"]),
    ("что выведет print(7 // 2)", lambda o: "3" in o["reply"]),
    ("NameError: name 'x' is not defined", lambda o: o.get("kind") == "error"),
    ("def f(x):\n    return x * 2\nprint(f(4))", lambda o: o.get("kind") == "code"),
    ("   ", lambda o: o["reply"] != ""), ("?!?!?!", lambda o: o["reply"] != ""), ("🙂🙂🙂", lambda o: o["reply"] != ""),
    ("а" * 3000, lambda o: o["reply"] != ""), ("\x00\x01 abc", lambda o: o["reply"] != ""),
]
OUT_OF_SCOPE = ["какая столица франции", "рецепт борща", "курс доллара сегодня", "who won the world cup", "как похудеть за неделю",
                "что посмотреть вечером", "прогноз погоды на завтра", "как приготовить пиццу"]


def run(verbose=False):
    fails, total_ok, total = [], 0, 0
    print(f"{'группа':22} {'top1':>6} {'top3':>6}   n")
    for name, cases in GROUPS:
        t1 = t3 = 0
        for q, ids in cases:
            want = set(ids.split())
            res = IDX.search(q, top=3)
            got = [c.id for c, _ in res.ranked]
            ok1 = bool(got) and got[0] in want
            ok3 = bool(set(got) & want)
            t1 += ok1
            t3 += ok3
            if not ok1:
                fails.append((name, q, sorted(want), got[:3], round(res.confidence, 2)))
        n = len(cases)
        total_ok += t1
        total += n
        print(f"{name:22} {t1 / n:6.0%} {t3 / n:6.0%}  {n}")
    print(f"{'ИТОГО (top1)':22} {total_ok / total:6.0%}")

    # конфиденциальность: при уверенном ответе карточка верная; при уверенности ниже порога — не должно быть «наглого» ответа
    wrong_confident = [f for f in fails if f[4] >= HI]
    print(f"\nуверенных, но неверных ответов: {len(wrong_confident)} из {total}")

    A2 = Assistant(os.path.join(ROOT, "data", "kb"), seed=2)
    ctx = {"persona": "goth", "progress": {"completed": 3, "total": 39}, "code": "x = 1", "task": {"title": "Тест", "type": "function", "func_name": "f"}}
    bad_eng = []
    for q, check in ENGINE_CASES:
        try:
            o = A2.reply(q, ctx)
            if not check(o):
                bad_eng.append((q[:40], o.get("card"), o.get("action"), o.get("reply", "")[:60]))
        except Exception as e:
            bad_eng.append((q[:40], "EXC", repr(e), ""))
    print(f"команды/разговор/устойчивость: {len(ENGINE_CASES) - len(bad_eng)}/{len(ENGINE_CASES)}")

    oos_bad = []
    for q in OUT_OF_SCOPE:
        o = A2.reply(q, ctx)
        if o.get("card") and o.get("confidence", 0) >= 1.0 and o.get("kind") != "chat":
            oos_bad.append((q, o.get("card")))
    print(f"вне темы (не должна выдумывать ответ): {len(OUT_OF_SCOPE) - len(oos_bad)}/{len(OUT_OF_SCOPE)}")
    print(f"внутренних сбоев: {len(A2.errors)}")

    if verbose or fails or bad_eng or oos_bad:
        print("\n--- промахи поиска (запрос | ожидалось | получено | уверенность)")
        for f in fails:
            print("  ", f)
        for b in bad_eng:
            print("   ENGINE:", b)
        for b in oos_bad:
            print("   ВНЕ ТЕМЫ ответила:", b)
    return total_ok / total, len(wrong_confident), len(bad_eng), len(oos_bad)


if __name__ == "__main__":
    run("-v" in sys.argv)
