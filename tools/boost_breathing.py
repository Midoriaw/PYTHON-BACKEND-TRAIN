"""
Делает дыхание chibi-SVG заметнее. Оригинал НЕ меняется: результат пишется в другой файл.

Почему не просто «умножить числа» в оригинале:
  * в оригинале scale шёл вокруг точки (0,0) картинки: на вдохе грудь и плечи ехали ВНИЗ-ВПРАВО,
    а у goth ещё и нижняя часть лица;
  * сдвинутая копия клалась поверх неподвижной, и при большей амплитуде двоились лямки и цепочки.

Как сделано здесь:
  * тело (от линии подбородка до талии) режется на тонкие горизонтальные слои; каждый слой поднимается
    чуть выше соседнего и плавно (линейно) переходит в него, получается плавный изгиб без двоения;
  * плечи и грудь поднимаются вверх и чуть расширяются в стороны, лицо и всё ниже талии неподвижно;
  * анимация та же по духу: SMIL внутри SVG, тот же период и те же кривые ease-in/out, PNG не трогается.

Использование:
  python tools/boost_breathing.py assets/chibi_original/goth.svg assets/chibi/goth.svg [--k 1.0]
  --k  множитель силы (1.0 по умолчанию; 1.4 = ещё заметнее; 0.7 = мягче)
Для нового персонажа добавь строку в PRESETS (см. комментарии).
"""
import argparse, os, re, sys

# cx    : центр тела по X (вокруг него грудь расширяется)
# keys  : (y, доля подъёма 0..1) сверху вниз: [линия подбородка -> 0, плечи -> 1, ... грудь -> 1, талия -> 0]
# lift  : максимальный подъём в единицах SVG (ширина картинки 1024). На экране 180 px это lift*0.176 px
# sx    : максимальное расширение груди по X (0.03 = +3 %)
PRESETS = {
    "goth":       dict(cx=530, keys=[(630, 0), (685, 1), (800, 1), (930, 0)], lift=14, sx=0.03),
    "girl":       dict(cx=512, keys=[(590, 0), (650, 1), (840, 1), (990, 0)], lift=14, sx=0.03),
    "schoolgirl": dict(cx=490, keys=[(470, 0), (525, 1), (700, 1), (800, 0)], lift=11, sx=0.03),
}
STEP = 30  # высота одного слоя-перехода, ед. SVG


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def frac(y, keys):
    """Доля подъёма на высоте y: гладкая кривая через ключевые точки."""
    if y <= keys[0][0] or y >= keys[-1][0]:
        return 0.0
    for (ya, fa), (yb, fb) in zip(keys, keys[1:]):
        if ya <= y <= yb:
            return fa + (fb - fa) * smooth((y - ya) / (yb - ya))
    return 0.0


def boost(src, dst, k=1.0, name=None):
    name = name or os.path.splitext(os.path.basename(src))[0]
    if name not in PRESETS:
        sys.exit(f"Нет пресета '{name}' в PRESETS: добавь cx, keys, lift, sx.")
    p = PRESETS[name]
    s = open(src, encoding="utf-8").read()
    head = re.match(r'(<\?xml[^>]*\?>\s*<svg[^>]*>)', s).group(1)
    image = re.search(r'<image id="character".*?/>', s, re.S).group(0)
    dur = re.search(r'dur="([\d.]+s)"', s).group(1)           # период цикла как в оригинале
    spl = f'keyTimes="0;0.5;1" calcMode="spline" keySplines="0.42 0 0.58 1;0.42 0 0.58 1" dur="{dur}" repeatCount="indefinite"'
    cx, keys = p["cx"], p["keys"]
    lift, sxm = p["lift"] * k, p["sx"] * k
    y0, y3 = keys[0][0], keys[-1][0]
    n = -(-(y3 - y0) // STEP)                                   # число слоёв-переходов (округление вверх)

    # Слои идут сверху вниз с шагом STEP. Вес слоя j: «треугольник» с вершиной на c_j (у первого и последнего
    # слоя вершина тянется до края картинки). Сумма весов в любой точке равна 1, а слои СКЛАДЫВАЮТСЯ
    # (mix-blend-mode: plus-lighter), поэтому в покое получается ровно исходная картинка, даже с полупрозрачными
    # пикселями, а при подъёме соседи отличаются на пару единиц: изгиб плавный, двоения нет.
    H = 1536
    defs, layers = [image], []
    for j in range(n + 1):
        c = y0 + j * STEP
        f = frac(c, keys)                                       # подъём слоя = значение кривой в его центре
        d, sx = lift * f, 1 + sxm * f
        if j == 0:
            stops, ya, yb = ('<stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#000"/>'), c, c + STEP
        elif j == n:
            stops, ya, yb = ('<stop offset="0" stop-color="#000"/><stop offset="1" stop-color="#fff"/>'), c - STEP, c
        else:
            stops, ya, yb = ('<stop offset="0" stop-color="#000"/><stop offset="0.5" stop-color="#fff"/>'
                             '<stop offset="1" stop-color="#000"/>'), c - STEP, c + STEP
        defs.append(
            f'<linearGradient id="g{j}" gradientUnits="userSpaceOnUse" x1="0" y1="{ya}" x2="0" y2="{yb}">{stops}</linearGradient>'
            f'<mask id="m{j}" maskUnits="userSpaceOnUse" x="0" y="0" width="1024" height="{H}">'
            f'<rect width="1024" height="{H}" fill="url(#g{j})"/></mask>')
        layers.append(
            f'<g mask="url(#m{j})" style="mix-blend-mode:plus-lighter"><g transform="translate({cx} 0)"><g>'
            f'<animateTransform attributeName="transform" type="scale" values="1 1;{sx:.4f} 1;1 1" {spl}/>'
            f'<g transform="translate(-{cx} 0)"><g>'
            f'<animateTransform attributeName="transform" type="translate" values="0 0;0 -{d:.2f};0 0" {spl}/>'
            '<use href="#character" xlink:href="#character"/></g></g></g></g></g>')

    out = (head + "\n<defs>\n" + "\n".join(defs) + "\n</defs>\n"
           '<g style="isolation:isolate">\n' + "\n".join(layers) + "\n</g>\n</svg>\n")
    open(dst, "w", encoding="utf-8").write(out)
    print(f"{name}: {n} слоёв, подъём до {lift:.1f} ед., расширение +{sxm*100:.1f}%, период {dur} → {dst}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dst"); ap.add_argument("--k", type=float, default=1.0)
    a = ap.parse_args()
    boost(a.src, a.dst, a.k)
