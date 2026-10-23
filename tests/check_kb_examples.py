"""Проверяет базу знаний: у каждого примера кода корректный синтаксис, а где возможно, он ещё и выполняется без ошибок.
Запуск из корня проекта:  python tests/check_kb_examples.py"""
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from assistant import kb  # noqa: E402

SKIP_EXEC = re.compile(r"input\(|Session\(|SessionLocal|uvicorn|sqlalchemy|engine|asyncio\.run|open\(")
PRELUDE = """from fastapi import FastAPI, HTTPException, Header, Query, Depends, status, BackgroundTasks
from pydantic import BaseModel
app = FastAPI()
"""
FRAGMENT_TOPICS = ("FastAPI", "HTTP")   # здесь примеры показывают кусок кода, а не весь файл
bad, syntax_only, ran = [], 0, 0
cards = kb.load_dir(os.path.join(ROOT, "data", "kb"))
for c in cards:
    for i, blk in enumerate(c.examples):
        code = "\n".join(blk)
        lines = [l for l in blk if l.strip()]
        if lines and all(l.lstrip().startswith(("#", "--")) for l in lines):
            continue                              # SQL, команды терминала и т.п.
        try:
            compile(code, f"{c.id}[{i}]", "exec")
        except SyntaxError as e:
            bad.append((c.id, i, f"SyntaxError: {e.msg} (строка {e.lineno})"))
            continue
        if SKIP_EXEC.search(code):
            syntax_only += 1
            continue
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write((PRELUDE if c.topic in FRAGMENT_TOPICS else "") + code)
        try:
            r = subprocess.run([sys.executable, f.name], capture_output=True, text=True, timeout=8)
            ran += 1
            if r.returncode != 0:
                bad.append((c.id, i, r.stderr.strip().splitlines()[-1]))
        except subprocess.TimeoutExpired:
            bad.append((c.id, i, "таймаут"))
        finally:
            os.unlink(f.name)
print(f"карточек: {len(cards)}, блоков выполнено: {ran}, только синтаксис: {syntax_only}, проблем: {len(bad)}")
for b in bad:
    print("  ", b)
sys.exit(1 if bad else 0)
