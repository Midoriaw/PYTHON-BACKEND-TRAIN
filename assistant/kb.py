"""База знаний: парсер .kb-файлов и поисковый индекс (BM25F + триграммы + синонимы + исправление опечаток)."""
import math
import os
import re
from dataclasses import dataclass, field

from . import lexicon, nlp


@dataclass
class Card:
    id: str
    topic: str = ""
    title: str = ""
    kind: str = "concept"
    level: int = 1
    phrasings: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    paras: list = field(default_factory=list)
    examples: list = field(default_factory=list)
    pitfalls: list = field(default_factory=list)
    tips: list = field(default_factory=list)
    related: list = field(default_factory=list)
    en: str = ""
    src: str = ""


def parse_kb(text: str, src: str = "") -> list:
    cards, cur, new_block = [], None, True
    for ln, raw in enumerate(text.split("\n"), 1):
        line = raw.rstrip()
        if not line.strip() or line.startswith("//"):
            continue
        if line.startswith("@+"):
            cur = Card(id="+" + line[2:].strip(), kind="__addon__", src=f"{src}:{ln}")
            cards.append(cur)
            continue
        if line.startswith("@"):
            parts = [p.strip() for p in line[1:].split("|")]
            cur = Card(id=parts[0], topic=parts[1] if len(parts) > 1 else "", title=parts[2] if len(parts) > 2 else parts[0], src=f"{src}:{ln}")
            cards.append(cur)
            new_block = True
            continue
        if cur is None:
            continue
        if line.startswith(">-"):
            new_block = True
        elif line.startswith(">"):
            code = line[2:] if line.startswith("> ") else line[1:]
            if new_block or not cur.examples:
                cur.examples.append([])
                new_block = False
            cur.examples[-1].append(code)
        elif line.startswith("%"):
            cur.kind = line[1:].strip()
        elif line.startswith("^"):
            cur.level = int(line[1:].strip() or 1)
        elif line.startswith("?"):
            cur.phrasings += [p.strip() for p in line[1:].split(";") if p.strip()]
        elif line.startswith("#"):
            cur.tags += line[1:].split()
        elif line.startswith("="):
            cur.paras.append(line[1:].strip())
        elif line.startswith("!"):
            cur.pitfalls.append(line[1:].strip())
        elif line.startswith("+"):
            cur.tips.append(line[1:].strip())
        elif line.startswith("~"):
            cur.related += line[1:].split()
        elif line.startswith("en:"):
            cur.en = line[3:].strip()
        else:
            raise ValueError(f"{src}:{ln}: не понял строку: {line[:60]!r}")
    return cards


def load_dir(path: str) -> list:
    cards = []
    for fn in sorted(os.listdir(path)):
        if fn.endswith(".kb"):
            with open(os.path.join(path, fn), "r", encoding="utf-8") as f:
                cards += parse_kb(f.read(), fn)
    base = {c.id: c for c in cards if c.kind != "__addon__"}
    for c in [c for c in cards if c.kind == "__addon__"]:
        target = base.get(c.id[1:])
        if target is None:
            raise ValueError(f"{c.src}: дополнение к несуществующей карточке {c.id[1:]!r}")
        target.phrasings += c.phrasings
        target.tags += c.tags
        target.related += [r for r in c.related if r not in target.related]
    cards = [c for c in cards if c.kind != "__addon__"]
    ids = [c.id for c in cards]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise ValueError(f"повторяющиеся id: {sorted(dup)}")
    return cards


_STOP_STEMS = {nlp.stem(w) for w in lexicon.STOPWORDS} | set(lexicon.STOPWORDS)
_WEAK_STEMS = {nlp.stem(w) for w in lexicon.WEAK} | set(lexicon.WEAK)


@dataclass
class Result:
    ranked: list            # [(Card, score)]
    confidence: float
    coverage: float
    qstems: list
    fixed: str = ""         # что исправили: "", "typo", "layout"
    tokens: list = field(default_factory=list)


class Index:
    K1, B = 1.4, 0.55
    W_TITLE, W_Q, W_TAG, W_BODY, W_CODE = 3.0, 3.0, 2.0, 1.0, 0.5

    def __init__(self, cards):
        self.cards = cards
        self.by_id = {c.id: c for c in cards}
        self.tf, self.len, self.df = [], [], {}
        self.tri, self.phr = [], []
        self.group_of, self.groups = {}, []
        self._build_groups()
        for c in cards:
            tf = {}
            self._add(tf, c.title, self.W_TITLE)
            for p in c.phrasings:
                self._add(tf, p, self.W_Q)
            self._add(tf, " ".join(c.tags), self.W_TAG)
            self._add(tf, c.topic, self.W_TAG)
            for p in c.paras:
                self._add(tf, p, self.W_BODY)
            for p in c.pitfalls + c.tips:
                self._add(tf, p, self.W_BODY * 0.6)
            for blk in c.examples:
                self._add(tf, " ".join(blk), self.W_CODE)
            self.tf.append(tf)
            self.len.append(sum(tf.values()) or 1.0)
            for t in tf:
                self.df[t] = self.df.get(t, 0) + 1
            head = " ".join([c.title] + c.phrasings + c.tags)
            self.tri.append(nlp.trigrams(nlp.clean(head)))
            self.phr.append([set(self._stems(p)) for p in c.phrasings + [c.title]])
        self.avg = sum(self.len) / max(1, len(self.len))
        self.N = len(cards)
        words = set(self.df) | set(self.group_of) | _STOP_STEMS | {nlp.clean(w) for w in lexicon.STOPWORDS}
        self.vocab = nlp.Vocab({w for w in words if len(w) >= 3}, {**{w: n for w, n in self.df.items()}, **{w: 5 for w in self.group_of}})
        # точные фразы: «как дела», «кто ты» состоят из служебных слов, их проще найти целиком
        self.exact = {}
        for c in cards:
            for ph in c.phrasings + [c.title]:
                self.exact.setdefault(" ".join(nlp.tokens(ph)), c)

    # ---- токены
    def _stems(self, text):
        return [nlp.stem(t) for t in nlp.tokens(text) if t not in _STOP_STEMS and nlp.stem(t) not in _STOP_STEMS]

    def _add(self, tf, text, w):
        for s in self._stems(text):
            tf[s] = tf.get(s, 0.0) + w

    def _build_groups(self):
        for g in lexicon.SYN_GROUPS:
            members = sorted({nlp.stem(nlp.clean(w)) for w in g.split()})
            idx = len(self.groups)
            self.groups.append(members)
            for m in members:
                self.group_of.setdefault(m, []).append(idx)

    def expand(self, stems):
        q = {}
        for s in stems:
            q[s] = max(q.get(s, 0), 0.45 if s in _WEAK_STEMS else 1.0)
        for s in stems:
            for gi in self.group_of.get(s, ()):
                for m in self.groups[gi]:
                    if m != s and m not in q:
                        q[m] = 0.5
        return q

    def idf(self, t):
        n = self.df.get(t, 0)
        return math.log(1 + (self.N - n + 0.5) / (n + 0.5))

    def _fix_stem(self, s):
        """Основа, которой нет ни в карточках, ни в синонимах: заменяем ближайшей известной (опечатка, транслит)."""
        if s in self.df or s in self.group_of or len(s) < 4:
            return s
        return self.vocab.nearest(s) or s

    # ---- поиск
    def search(self, text, boost=None, top=8) -> Result:
        toks, fixed = nlp.smart_tokens(text, self.vocab)
        content = [t for t in toks if t not in _STOP_STEMS and nlp.stem(t) not in _STOP_STEMS]
        stems = [self._fix_stem(t if t in self.vocab.words else nlp.stem(t)) for t in content]
        unknown = sum(1 for t in content if not (t in self.vocab.words or nlp.stem(t) in self.vocab.words))
        unknown_share = unknown / len(content) if content else 0.0
        exact = self.exact.get(" ".join(toks))
        if not stems:
            if exact:
                return Result([(exact, 2.0)], 1.0, 1.0, [], fixed, toks)
            return Result([], 0.0, 0.0, [], fixed, toks)
        q = self.expand(stems)
        primary = set(stems)
        qtri = nlp.trigrams(" ".join(content))
        total_idf = sum(self.idf(s) for s in primary) or 1.0
        scores = []
        for i, c in enumerate(self.cards):
            tf, dl = self.tf[i], self.len[i]
            bm = 0.0
            for t, w in q.items():
                f = tf.get(t)
                if f:
                    bm += w * self.idf(t) * (f * (self.K1 + 1)) / (f + self.K1 * (1 - self.B + self.B * dl / self.avg))
            # покрытие: какая доля (по idf) основных слов запроса встретилась в карточке, с учётом синонимов
            cov_hit = 0.0
            for s in primary:
                if s in tf or any(m in tf for gi in self.group_of.get(s, ()) for m in self.groups[gi]):
                    cov_hit += self.idf(s)
            cov = cov_hit / total_idf
            tri = len(qtri & self.tri[i]) / max(1, len(qtri))
            jac = max((len(primary & ps) / max(1, len(primary | ps)) for ps in self.phr[i]), default=0.0)
            scores.append([c, bm, cov, tri, jac])
        mx = max(s[1] for s in scores) or 1.0
        ranked = []
        for c, bm, cov, tri, jac in scores:
            final = 0.45 * (bm / mx) + 0.25 * cov + 0.1 * tri + 0.3 * jac
            if boost:
                final += 0.12 * len(boost & {nlp.stem(t) for t in c.tags})
            ranked.append((c, final, cov, tri, jac))
        ranked.sort(key=lambda r: -r[1])
        if exact:
            ranked = [r for r in ranked if r[0] is exact][:1] + [r for r in ranked if r[0] is not exact]
            ranked[0] = (ranked[0][0], max(ranked[0][1], ranked[1][1] + 0.2), 1.0, 1.0, 1.0)
        top1 = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = (top1[1] - second) / top1[1] if top1[1] else 0.0
        conf = 0.5 * top1[2] + 0.2 * min(1.0, top1[3] * 1.5) + 0.15 * min(1.0, margin * 2.5) + 0.15 * min(1.0, top1[4] * 1.5)
        if unknown_share >= 0.5 and not exact:
            conf *= 0.5                      # половина слов запроса нам незнакома: честнее сказать «не знаю»
        return Result([(r[0], r[1]) for r in ranked[:top]], conf, top1[2], stems, fixed, toks)
