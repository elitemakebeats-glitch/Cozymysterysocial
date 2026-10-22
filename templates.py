"""Plantillas ilustradas para Cozy Mystery Corner.

generate.py llama a render(...) por cada slide. Si falta la carpeta templates/
o la plantilla, devuelve None y generate.py usa el diseño liso de siempre.
Las 8 imagenes van en templates/ con los nombres T1_... a T8_... (.png).
"""
import os
from PIL import Image, ImageDraw

DIR = "templates"
PANEL = (250, 241, 224)
INK = (59, 31, 43)
SX, SY = 1080 / 941, 1920 / 1672

# zonas medidas sobre la imagen original 941x1672: (x0, y0, x1, y1)
Z = {
    "T1_biblioteca_gato":     dict(title=(150, 268, 791, 371), img=(150, 399, 791, 992), text=(150, 1018, 790, 1211)),
    "T2_pergamino_llaves":    dict(title=(124, 234, 817, 343),
                                   rows=[((124, 373, 278, 613), (294, 373, 816, 613)),
                                         ((124, 644, 278, 882), (294, 645, 817, 882)),
                                         ((124, 912, 278, 1150), (294, 912, 817, 1150)),
                                         ((124, 1179, 278, 1416), (294, 1179, 817, 1416))]),
    "T3_mesa_cupcakes":       dict(title=(136, 240, 801, 373), img=(174, 400, 765, 1114), text=(174, 1140, 765, 1388)),
    "T4_escritorio_detective": dict(title=(127, 296, 813, 428), text=(118, 453, 822, 1192)),
    "T5_relojes_cuenta":      dict(circle=(109, 233, 258, 385), title=(273, 257, 796, 363),
                                   img=(155, 396, 786, 1144), text=(136, 1167, 804, 1365)),
    "T6_salon_nostalgia":     dict(title=(146, 267, 794, 375), img=(146, 399, 794, 1138), text=(146, 1161, 794, 1367)),
    "T7_biblioteca_luz":      dict(title=(139, 261, 798, 370), img=(148, 394, 788, 1154), text=(146, 1177, 791, 1395)),
    "T8_carta_sello":         dict(title=(119, 239, 821, 365), img=(119, 398, 395, 857), text=(119, 896, 821, 1374)),
}
BOOKS = ["T7_biblioteca_luz", "T3_mesa_cupcakes", "T6_salon_nostalgia", "T1_biblioteca_gato"]
BY_KIND = {"cover": "T1_biblioteca_gato", "clue": "T4_escritorio_detective", "cta": "T5_relojes_cuenta",
           "dates": "T6_salon_nostalgia", "answers": "T2_pergamino_llaves"}


def sc(b): return [int(b[0] * SX), int(b[1] * SY), int(b[2] * SX), int(b[3] * SY)]


def lum(c): return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def panel(G, d, b, acc):
    d.rounded_rectangle([b[0] - 5, b[1] - 5, b[2] + 5, b[3] + 5], radius=26, fill=PANEL,
                        outline=G.mix(PANEL, acc, 0.55), width=4)


def block(d, im, items, box):
    total = sum(i["h"] for i in items)
    y = box[1] + max(0, (box[3] - box[1] - total) / 2)
    cx = (box[0] + box[2]) / 2
    for it in items:
        it["fn"](d, im, y, cx, 1080)
        y += it["h"]


def title_items(G, d, text, maxw, maxh, start, minsize, col):
    sz = start
    while True:
        f, ls, s = G.fit(d, text, lambda z: G.lora(z, "Bold"), maxw, 6, sz, minsize)
        if len(ls) * s * 1.18 <= maxh or sz <= minsize: break
        sz -= 4
    return G.it_lines(ls, f, col, int(s * 1.18))


def header(G, d, box, text, col, size=46):
    f, ls, s = G.fit(d, text, lambda z: G.pop(z, "Bold"), box[2] - box[0] - 40, 1, size, 22)
    d.text(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), ls[0] if ls else text, font=f, fill=col, anchor="mm")


def rows_in_box(G, d, im, rows, box, acc):
    x0, y0, x1, y1 = box
    H = y1 - y0 - 40
    scale = 1.0
    while True:
        th = int(200 * scale); tw = int(th * 0.66)
        textx = x0 + 30 + tw + 28; tmaxw = x1 - 24 - textx
        built, total = [], 0
        for cov, l1, title, sub in rows:
            f1 = G.pop(int(30 * scale), "Bold")
            ft, lst, st = G.fit(d, title, lambda z: G.lora(z, "Bold"), tmaxw, 3, int(44 * scale), 24)
            fs = G.pop(int(26 * scale), "Italic")
            subl = G.wrap(d, sub, fs, tmaxw) if sub else []
            lh1, lht, lhs = int(f1.size * 1.3), int(st * 1.2), int(fs.size * 1.3)
            txt_h = (lh1 if l1 else 0) + lht * len(lst) + lhs * len(subl)
            rh = max(th, txt_h)
            built.append((cov, l1, f1, lst, ft, subl, fs, lh1, lht, lhs, txt_h, rh)); total += rh
        gap = int(30 * scale); total += gap * (len(rows) - 1)
        if total <= H or scale < 0.5: break
        scale -= 0.05
    y = y0 + (y1 - y0 - total) / 2
    for cov, l1, f1, lst, ft, subl, fs, lh1, lht, lhs, txt_h, rh in built:
        if cov is not None:
            c = G.prep_cover(cov, tw, th, radius=10)
            G.paste_cover(im, c, int(x0 + 30 + (tw - c.width) // 2), int(y + (rh - c.height) // 2))
        ty = y + (rh - txt_h) / 2
        if l1:
            d.text((textx, ty + lh1 / 2), l1, font=f1, fill=acc, anchor="lm"); ty += lh1
        for ln in lst:
            d.text((textx, ty + lht / 2), ln, font=ft, fill=INK, anchor="lm"); ty += lht
        for ln in subl:
            d.text((textx, ty + lhs / 2), ln, font=fs, fill=INK, anchor="lm"); ty += lhs
        y += rh + gap


def render(G, sl, plat, idx, total, pidx, theme):
    kind = sl["k"]
    name = BY_KIND.get(kind) or BOOKS[pidx % len(BOOKS)]
    path = os.path.join(DIR, name + ".png")
    if not os.path.exists(path): return None
    if kind == "answers" and len(sl["items"]) > 4: return None
    if kind == "dates" and len(sl["items"]) > 3: return None
    bg, _ink, acc = [G.hexc(x) for x in G.THEMES[theme]]
    if lum(acc) > 150: acc = G.mix(acc, INK, 0.5)
    chip_txt = (255, 255, 255)
    z = Z[name]
    im = Image.open(path).convert("RGB").resize((1080, 1920), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    zones = {k: sc(v) for k, v in z.items() if k != "rows" and k != "circle"}
    rows = [(sc(a), sc(b)) for a, b in z.get("rows", [])]
    circle = sc(z["circle"]) if "circle" in z else None
    for k, b in zones.items(): panel(G, d, b, acc)
    for a, b in rows: panel(G, d, a, acc); panel(G, d, b, acc)
    if circle:
        d.ellipse([circle[0] - 5, circle[1] - 5, circle[2] + 5, circle[3] + 5], fill=PANEL, outline=G.mix(PANEL, acc, 0.55), width=4)
    T, I, X = zones.get("title"), zones.get("img"), zones.get("text")

    if kind == "cover":
        header(G, d, T, "COZY MYSTERY CORNER", INK, 40)
        mw = I[2] - I[0] - 70
        items = [G.it_emoji(d, sl["emo"], 150, mw, INK), G.it_space(30)]
        items += [title_items(G, d, sl["title"], mw, (I[3] - I[1]) - 450, 100, 44, INK), G.it_space(24),
                  G.it_bar(200, 9, acc), G.it_space(24), G.it_text(d, sl["sub"], G.pop(36, "Medium"), acc, mw)]
        block(d, im, items, I)
        block(d, im, [G.it_chip(d, "SWIPE", G.pop(32, "Bold"), acc, chip_txt, arrow=True), G.it_space(14),
                      G.it_text(d, G.HANDLE, G.pop(28, "Medium"), INK, X[2] - X[0] - 40)], X)
    elif kind == "book":
        tag = sl.get("tag")
        header(G, d, T, f"#{sl['n']}  {tag}" if tag else f"#{sl['n']}", INK, 46)
        cov = sl.get("cover")
        if cov is not None:
            c = G.prep_cover(cov, I[2] - I[0] - 60, I[3] - I[1] - 60)
            G.paste_cover(im, c, int((I[0] + I[2] - c.width) / 2), int((I[1] + I[3] - c.height) / 2))
        mw = X[2] - X[0] - 50
        fT, lsT, sT = G.fit(d, sl["title"], lambda zz: G.lora(zz, "Bold"), mw, 2, 54, 28)
        items = [G.it_lines(lsT, fT, INK, int(sT * 1.2))]
        if sl.get("author"): items += [G.it_space(6), G.it_text(d, "by " + sl["author"], G.pop(32, "Medium"), INK, mw)]
        if sl.get("series"): items += [G.it_space(4), G.it_text(d, sl["series"], G.pop(26, "Italic"), acc, mw)]
        block(d, im, items, X)
    elif kind == "clue":
        header(G, d, T, f"CLUE {sl['n']}", acc, 58)
        mw = X[2] - X[0] - 80
        items = [G.it_emoji(d, sl["tok"], 210, mw, INK), G.it_space(60),
                 G.it_text(d, "What\u2019s the title?", G.lora(72, "Bold"), INK, mw), G.it_space(24),
                 G.it_text(d, "Answers on the last slide", G.pop(32, "Regular"), acc, mw)]
        block(d, im, items, X)
    elif kind == "answers":
        header(G, d, T, "THE ANSWERS", INK, 52)
        for n, (it, (ib, tb)) in enumerate(zip(sl["items"], rows), 1):
            cov = it.get("cover")
            if cov is not None:
                c = G.prep_cover(cov, ib[2] - ib[0] - 16, ib[3] - ib[1] - 16, radius=8)
                G.paste_cover(im, c, int((ib[0] + ib[2] - c.width) / 2), int((ib[1] + ib[3] - c.height) / 2))
            else:
                e = G.emoji_img("\U0001F4D6", int((ib[2] - ib[0]) * 0.5))
                im.paste(e, (int((ib[0] + ib[2] - e.width) / 2), int((ib[1] + ib[3] - e.height) / 2)), e)
            mw = tb[2] - tb[0] - 40
            ft, lst, st = G.fit(d, it["title"], lambda zz: G.lora(zz, "Bold"), mw, 3, 44, 24)
            items = [G.it_text(d, f"#{n}", G.pop(28, "Bold"), acc, mw), G.it_lines(lst, ft, INK, int(st * 1.2))]
            if it.get("sub"): items += [G.it_text(d, it["sub"], G.pop(25, "Italic"), INK, mw)]
            tb2 = [tb[0] + 12, tb[1], tb[2], tb[3]]
            block(d, im, items, tb2)
    elif kind == "dates":
        header(G, d, T, sl["head"], INK, 50)
        rr = [(it.get("cover"), it["date"], it["title"], it.get("sub", "")) for it in sl["items"]]
        rows_in_box(G, d, im, rr, I, acc)
        block(d, im, [G.it_text(d, "Save so you don\u2019t miss a date", G.lora(46, "Bold"), INK, X[2] - X[0] - 60), G.it_space(12),
                      G.it_text(d, G.HANDLE, G.pop(28, "Medium"), acc, X[2] - X[0] - 60)], X)
    elif kind == "cta":
        header(G, d, T, "COZY MYSTERY CORNER", INK, 36)
        e = G.emoji_img(sl["emo"][0], 100)
        im.paste(e, (int((circle[0] + circle[2] - e.width) / 2), int((circle[1] + circle[3] - e.height) / 2)), e)
        mw = I[2] - I[0] - 80
        items = [title_items(G, d, sl["text"], mw, (I[3] - I[1]) - 200, 100, 52, INK), G.it_space(30),
                 G.it_bar(200, 9, acc), G.it_space(30),
                 G.it_text(d, "Comment \u00b7 Save \u00b7 Share", G.pop(38, "Medium"), acc, mw)]
        block(d, im, items, I)
        block(d, im, [G.it_chip(d, "FOLLOW " + G.HANDLE, G.pop(32, "Bold"), acc, chip_txt)], X)

    if plat == "ig":
        allb = list(zones.values()) + [b for r in rows for b in r] + ([circle] if circle else [])
        top, bot = min(b[1] for b in allb), max(b[3] for b in allb)
        off = max(0, min(1920 - 1350, int((top + bot) / 2 - 675)))
        im = im.crop((0, off, 1080, off + 1350))
    return im
