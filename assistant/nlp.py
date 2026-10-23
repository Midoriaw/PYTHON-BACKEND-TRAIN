import difflib
import re


_QW = "qwertyuiop[]asdfghjkl;'zxcvbnm,.`"
_RU = "йцукенгшщзхъфывапролджэячсмитьбюё"
LAT2CYR = dict(zip(_QW, _RU))
CYR2LAT = dict(zip(_RU, _QW))

_TR3 = {"shch": "щ"}
_TR2 = {"sh": "ш", "ch": "ч", "zh": "ж", "yu": "ю", "ya": "я", "yo": "ё", "ts": "ц", "kh": "х", "ju": "ю", "ja": "я",
        "ye": "е"}
_TR1 = dict(zip("abvgdezijklmnoprstufhcywxq", "абвгдезийклмнопрстуфхцывкск"))
_TR1["c"] = "к"
_TR1["j"] = "й"
_TR1["w"] = "в"
_TR1["x"] = "кс"
_TR1["q"] = "к"
_TR1["y"] = "ы"
_TR1["h"] = "х"


def layout_to_cyr(s: str) -> str:
    return "".join(LAT2CYR.get(ch, ch) for ch in s)


def layout_to_lat(s: str) -> str:
    return "".join(CYR2LAT.get(ch, ch) for ch in s)


def translit_to_cyr(s: str, ts_split: bool = False) -> str:
    out, i = [], 0
    while i < len(s):
        for table, n in ((_TR3, 4), (_TR2, 2)):
            chunk = s[i:i + n]
            if ts_split and chunk == "ts":
                continue
            if chunk in table:
                out.append(table[chunk]); i += n; break
        else:
            ch = s[i]
            if ch == "c" and s[i + 1:i + 2] in ("e", "i", "y"):
                out.append("ц")
            else:
                out.append(_TR1.get(ch, ch))
            i += 1
    return "".join(out)



_RU_SUFFIXES = sorted("""ировать ирует ование ования ованию ением ениям ениях ения ение ений ости ость остью ами ями ого его
ому ему ыми ими ать ять еть ить уть ают яют ает яет ует ешь ишь ете ите ала ила ели али или ыть ов ев ей ом ем ам ям ах ях
ую юю ая яя ое ее ые ие ых их ой ий ый ся сь ть ла ло ли на а я ы и у ю е о ь й""".split(), key=len, reverse=True)


def ru_stem(w: str) -> str:
    if len(w) < 4:
        return w
    for s in _RU_SUFFIXES:
        if w.endswith(s) and len(w) - len(s) >= 3:
            w = w[: -len(s)]
            break
    if len(w) >= 5 and w[-2:] in ("ок", "ек", "ец"):
        w = w[:-2] + w[-1]
    return w


def en_stem(w: str) -> str:
    if len(w) <= 3:
        return w
    for s in ("ing", "ed", "es", "s"):
        if w.endswith(s) and len(w) - len(s) >= 3:
            return w[: -len(s)]
    return w


_CYR = re.compile(r"[а-я]")
_LAT = re.compile(r"[a-z]")
_TOKEN = re.compile(r"[a-zа-я0-9]+")


def stem(w: str) -> str:
    if _CYR.search(w):
        return ru_stem(w)
    return en_stem(w)


def clean(text: str) -> str:
    s = text.lower().replace("ё", "е")
    s = re.sub(r"\bf[\s\-]*(?:string|strings|строк\w*|строчк\w*)", "fstring", s)
    return re.sub(r"(.)\1{2,}", r"\1\1", s)


def tokens(text: str) -> list:
    return _TOKEN.findall(clean(text))


def trigrams(s: str) -> set:
    s = " " + re.sub(r"\s+", " ", s) + " "
    return {s[i:i + 3] for i in range(len(s) - 2)}


def edit_distance(a: str, b: str, limit: int = 3) -> int:

    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2, prev = None, list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if prev2 is not None and i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                v = min(v, prev2[j - 2] + 1)
            cur.append(v)
        prev2, prev = prev, cur
    return prev[-1]


class Vocab:


    def __init__(self, words, freq=None):
        self.words = set(words)
        self.freq = freq or {}
        self.by_len = {}
        for w in self.words:
            self.by_len.setdefault(len(w), []).append(w)
        self._cache = {}

    def known(self, tok: str) -> bool:
        return tok in self.words or stem(tok) in self.words

    def nearest(self, tok: str):
        """Ближайшее известное слово (основа) или None."""
        key = stem(tok)
        if key in self._cache:
            return self._cache[key]
        best = None
        n = len(key)
        limit = 1 if n <= 5 else 2
        if n >= 4:
            bd = limit + 1
            for ln in range(max(3, n - limit), n + limit + 1):
                for w in self.by_len.get(ln, ()):
                    if w[0] != key[0]:
                        continue                      # опечатка в первой букве бывает редко, а ложных замен много
                    d = edit_distance(key, w, limit)
                    better = d < bd or (d == bd and best is not None and self.freq.get(w, 0) > self.freq.get(best, 0))
                    if better:
                        bd, best = d, w
            if bd > limit:
                best = None
        self._cache[key] = best
        return best

    def coverage(self, toks) -> float:
        toks = [t for t in toks if len(t) >= 3]
        if not toks:
            return 0.0
        hit = sum(1 for t in toks if self.known(t) or self.nearest(t))
        return hit / len(toks)


def repair_token(tok: str, vocab: Vocab) -> str:

    from .lexicon import MISSPELLINGS
    if tok in MISSPELLINGS and tok not in ("лист", "иф", "фор", "класс", "импорт", "сет"):
        return MISSPELLINGS[tok]
    if len(tok) < 3 or vocab.known(tok):
        return tok
    cands = []
    if _LAT.search(tok) and not _CYR.search(tok):
        cands.append(layout_to_cyr(tok))
        for split in (False, True):
            tr = translit_to_cyr(tok, split)
            if re.search(r"[аеиоуыэюя]т$", tr):
                cands.append(tr + "ь")
            cands.append(tr)
    elif _CYR.search(tok) and not _LAT.search(tok):
        cands.append(layout_to_lat(tok))
    for c in cands:
        if vocab.known(c):
            return c
    for c in cands:
        near = vocab.nearest(c)
        if near and len(c) >= 5:
            return c
    near = vocab.nearest(tok)
    if near:
        return near
    return tok


def smart_tokens(text: str, vocab: Vocab):

    raw = tokens(text)
    fixed_whole = None
    if raw and not _CYR.search(clean(text)):

        cand = tokens(layout_to_cyr(clean(text)))
        if cand and vocab.coverage(cand) > vocab.coverage(raw) and vocab.coverage(cand) >= 0.5:
            fixed_whole = cand
    if fixed_whole is not None:
        return fixed_whole, "layout"
    out, changed = [], False
    for t in raw:
        r = repair_token(t, vocab)
        changed = changed or r != t
        out.append(r)
    return out, ("typo" if changed else "")
