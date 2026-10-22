"""Cozy Mystery Corner - generador de slides con portadas.

Uso:  python generate.py week1
Lee week1.py (posts, captions, autores), descarga las portadas desde
Google Books, Open Library, Apple Books y Amazon (por ISBN), y crea las slides en out/instagram y out/tiktok.

Portadas manuales: pon la imagen en covers_manual/ con el nombre que aparece
en out/covers_report.md (ejemplo: haunted_homicide.jpg). Siempre tiene prioridad.
"""
import os, sys, re, io, math, time, glob, shutil, importlib.util
try:
    import templates
except ImportError:
    templates = None
USE_TPL = templates is not None and os.path.isdir("templates") and os.environ.get("NO_TEMPLATES") != "1"
from PIL import Image, ImageDraw, ImageFont, ImageFilter
try:
    import requests
except ImportError:
    requests = None

HANDLE = "@cozymysterycorner"
OUT = "out"
FONT_DIRS = [os.environ.get("FONT_DIR", "fonts"), "/usr/share/fonts/truetype/google-fonts",
             "/usr/share/fonts/truetype/dejavu"]
EMO_PATHS = ["/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", "/usr/share/fonts/noto/NotoColorEmoji.ttf"]
UA = {"User-Agent": "CozyMysterySocial/1.0 (personal social media tool)"}

# ---------------------------------------------------------------- fonts
def find_font(name, fallback):
    for d in FONT_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p): return p
    for d in FONT_DIRS:
        p = os.path.join(d, fallback)
        if os.path.exists(p): return p
    return None

def lora(size, w="Bold"):
    p = find_font("Lora-Variable.ttf", "DejaVuSerif-Bold.ttf")
    f = ImageFont.truetype(p, size) if p else ImageFont.load_default()
    try: f.set_variation_by_name(w)
    except Exception: pass
    return f

def pop(size, w="Regular"):
    p = find_font(f"Poppins-{w}.ttf", "DejaVuSans-Bold.ttf" if w in ("Bold", "Medium") else "DejaVuSans.ttf")
    return ImageFont.truetype(p, size) if p else ImageFont.load_default()

_ec = {}
def emoji_img(e, size):
    k = (e, size)
    if k in _ec: return _ec[k]
    path = next((p for p in EMO_PATHS if os.path.exists(p)), None)
    if not path:
        im = Image.new("RGBA", (size, size), (0, 0, 0, 0)); _ec[k] = im; return im
    f = ImageFont.truetype(path, 109)
    im = Image.new("RGBA", (200, 160), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((0, 0), e, font=f, embedded_color=True)
    bb = im.getbbox()
    if bb: im = im.crop(bb)
    s = size / 109.0
    im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
    _ec[k] = im
    return im

def hexc(h): h = h.lstrip("#"); return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
def mix(a, b, t): return tuple(int(a[i]*(1-t) + b[i]*t) for i in range(3))

THEMES = {
    "cream":  ("F6EEDC", "3B1F2B", "8C2F39"),
    "autumn": ("F4E1C6", "4E2A14", "C2551F"),
    "teal":   ("E1EFEA", "1D4545", "2E8B7A"),
    "night":  ("231B36", "F5E7C8", "EE8F2D"),
    "xmas":   ("1F3D2F", "F5E7C8", "E9B44C"),
    "pink":   ("FBE3E3", "5E2133", "D9577A"),
    "blue":   ("E3ECF6", "1D2E4A", "3F6FB0"),
    "sepia":  ("EFE2CC", "47301F", "8A5A2B"),
    "plum":   ("EBDFF3", "36204D", "7B4FA3"),
}

# ---------------------------------------------------------------- covers
def norm(s): return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
def slug(s): return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")

AUTHORS = {}
REPORT = {}      # slug -> (title, source)
DROPPED = []     # (post, titulo) libros descartados por no tener portada
_cover_cache = {}

def _fetch_img(url):
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    im = Image.open(io.BytesIO(r.content)).convert("RGB")
    if im.width < 100 or im.height < 140: raise ValueError("imagen demasiado pequena")
    return im

def _google(title, author):
    img = _google_q(title, author)
    if img is None and author: img = _google_q(title, "")
    return img

def _google_q(title, author):
    q = f'intitle:"{title}"' + (f' inauthor:"{author}"' if author else "")
    params = {"q": q, "maxResults": 10, "printType": "books"}
    key = os.environ.get("GOOGLE_BOOKS_API_KEY")
    if key: params["key"] = key
    r = None
    for wait in (0, 4, 12):
        time.sleep(wait)
        r = requests.get("https://www.googleapis.com/books/v1/volumes", params=params, headers=UA, timeout=30)
        if r.status_code != 429: break
    r.raise_for_status()
    nt = norm(title)
    for it in r.json().get("items", []):
        vi = it.get("volumeInfo", {})
        vt = norm(vi.get("title", ""))
        if not vt or not (nt in vt or vt in nt): continue
        links = vi.get("imageLinks") or {}
        link = links.get("extraLarge") or links.get("large") or links.get("medium") or links.get("thumbnail")
        if not link: continue
        link = link.replace("http://", "https://").replace("&edge=curl", "")
        link = re.sub(r"zoom=\d", "zoom=3", link)
        try: return _fetch_img(link)
        except Exception: continue
    return None

def _openlibrary(title, author):
    nt = norm(title)
    for use_author in ((True, False) if author else (False,)):
        params = {"title": title, "limit": 10, "fields": "title,author_name,cover_i"}
        if use_author: params["author"] = author
        r = requests.get("https://openlibrary.org/search.json", params=params, headers=UA, timeout=30)
        r.raise_for_status()
        for d in r.json().get("docs", []):
            vt = norm(d.get("title", ""))
            if d.get("cover_i") and (nt in vt or vt in nt):
                try: return _fetch_img(f"https://covers.openlibrary.org/b/id/{d['cover_i']}-L.jpg")
                except Exception: continue
    return None

def _itunes(title, author, country="us"):
    """Apple Books (iTunes Search API): gratis, sin clave, buena cobertura de novedades."""
    nt = norm(title)
    for term in ([f"{title} {author}", title] if author else [title]):
        r = requests.get("https://itunes.apple.com/search",
                         params={"term": term, "media": "ebook", "entity": "ebook",
                                 "country": country, "limit": 10}, headers=UA, timeout=30)
        r.raise_for_status()
        for d in r.json().get("results", []):
            vt = norm(d.get("trackName", ""))
            url = d.get("artworkUrl100") or d.get("artworkUrl60")
            if not url or not vt or not (nt in vt or vt in nt): continue
            url = re.sub(r"/\d+x\d+(bb)?\.", "/800x800bb.", url)
            try: return _fetch_img(url)
            except Exception: continue
    return None

def _itunes_gb(title, author): return _itunes(title, author, "gb")

def _isbn13_to_10(i):
    if len(i) != 13 or not i.startswith("978"): return None
    core = i[3:12]
    t = sum((10 - k) * int(c) for k, c in enumerate(core)) % 11
    t = (11 - t) % 11
    return core + ("X" if t == 10 else str(t))

def _amazon(title, author):
    """Portada de Amazon por ISBN (el ISBN se saca de Open Library)."""
    nt = norm(title)
    params = {"title": title, "limit": 10, "fields": "title,isbn"}
    if author: params["author"] = author
    r = requests.get("https://openlibrary.org/search.json", params=params, headers=UA, timeout=30)
    r.raise_for_status()
    for d in r.json().get("docs", []):
        vt = norm(d.get("title", ""))
        if not (nt in vt or vt in nt): continue
        for isbn in (d.get("isbn") or [])[:12]:
            i10 = isbn if len(isbn) == 10 else _isbn13_to_10(isbn)
            if not i10: continue
            for host in ("https://images-na.ssl-images-amazon.com", "https://m.media-amazon.com"):
                try: return _fetch_img(f"{host}/images/P/{i10}.01.L.jpg")
                except Exception: continue
    return None

def get_cover(title, author=""):
    s = slug(title)
    if s in _cover_cache: return _cover_cache[s]
    os.makedirs("covers_manual", exist_ok=True); os.makedirs("covers_cache", exist_ok=True)
    img, src = None, "NO ENCONTRADA"
    for p in glob.glob(f"covers_manual/{s}.*"):
        try: img, src = Image.open(p).convert("RGB"), "manual"; break
        except Exception: pass
    if img is None and os.path.exists(f"covers_cache/{s}.jpg"):
        img, src = Image.open(f"covers_cache/{s}.jpg").convert("RGB"), "cache"
    if img is None and requests is not None:
        author = AUTHORS.get(norm(title), author or "")
        for name, fn in (("Google Books", _google), ("Open Library", _openlibrary),
                         ("Apple Books", _itunes), ("Apple Books GB", _itunes_gb), ("Amazon", _amazon)):
            try:
                img = fn(title, author)
            except Exception as e:
                print("  aviso", name, title, "->", e); img = None
            time.sleep(0.6)
            if img is not None:
                src = name; img.save(f"covers_cache/{s}.jpg", quality=92); break
    REPORT[s] = (title, src)
    _cover_cache[s] = img
    return img

# ---------------------------------------------------------------- drawing helpers
def wrap(d, text, font, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= maxw: cur = t
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines

def fit(d, text, fontfn, maxw, maxlines, start, minsize):
    s = start
    while s >= minsize:
        f = fontfn(s); ls = wrap(d, text, f, maxw)
        if len(ls) <= maxlines and all(d.textlength(l, font=f) <= maxw for l in ls):
            return f, ls, s
        s -= 4
    f = fontfn(minsize); return f, wrap(d, text, f, maxw), minsize

def lupa(d, cx, cy, r, col, w):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col, width=w)
    a = math.radians(45)
    x1, y1 = cx + r * math.cos(a), cy + r * math.sin(a)
    d.line([x1, y1, x1 + r * 0.8, y1 + r * 0.8], fill=col, width=int(w * 1.4))

def it_space(h): return dict(h=h, fn=lambda d, im, y, cx, W: None)

def it_text(d, text, font, col, maxw, lh=None):
    lines = wrap(d, text, font, maxw)
    lh = lh or int(font.size * 1.25)
    def fn(d, im, y, cx, W):
        for i, l in enumerate(lines):
            d.text((cx, y + i * lh + lh / 2), l, font=font, fill=col, anchor="mm")
    return dict(h=lh * len(lines), fn=fn)

def it_lines(lines, font, col, lh):
    def fn(d, im, y, cx, W):
        for i, l in enumerate(lines):
            d.text((cx, y + i * lh + lh / 2), l, font=font, fill=col, anchor="mm")
    return dict(h=lh * len(lines), fn=fn)

def it_bar(w, h, col):
    def fn(d, im, y, cx, W): d.rounded_rectangle([cx - w/2, y, cx + w/2, y + h], radius=h/2, fill=col)
    return dict(h=h, fn=fn)

def it_badge(txt, r, fill, tcol, fsz):
    def fn(d, im, y, cx, W):
        d.ellipse([cx - r, y, cx + r, y + 2*r], fill=fill)
        d.text((cx, y + r), txt, font=pop(fsz, "Bold"), fill=tcol, anchor="mm")
    return dict(h=2*r, fn=fn)

def it_chip(d, txt, font, fill, tcol, padx=34, pady=14, arrow=False):
    tw = d.textlength(txt, font=font); h = font.size + 2*pady
    ex = 70 if arrow else 0
    def fn(d, im, y, cx, W):
        tot = tw + ex
        d.rounded_rectangle([cx - tot/2 - padx, y, cx + tot/2 + padx, y + h], radius=h/2, fill=fill)
        d.text((cx - tot/2 + tw/2, y + h/2), txt, font=font, fill=tcol, anchor="mm")
        if arrow:
            ax0 = cx - tot/2 + tw + 18; ax1 = ax0 + 44; ay = y + h/2
            d.line([ax0, ay, ax1, ay], fill=tcol, width=5)
            d.line([ax1 - 14, ay - 14, ax1, ay], fill=tcol, width=5)
            d.line([ax1 - 14, ay + 14, ax1, ay], fill=tcol, width=5)
    return dict(h=h, fn=fn)

def it_emoji(d, tokens, size, maxw, col):
    plus = pop(int(size * 0.45), "Bold")
    def total(s):
        w = 0
        for i, t in enumerate(tokens):
            w += emoji_img(t, s).width
            if i < len(tokens) - 1: w += int(s * 0.7)
        return w
    s = size
    while total(s) > maxw and s > 60: s -= 6
    imgs = [emoji_img(t, s) for t in tokens]
    h = max(i.height for i in imgs); gap = int(s * 0.7)
    def fn(d, im, y, cx, W):
        x = cx - total(s) / 2
        for i, e in enumerate(imgs):
            im.paste(e, (int(x), int(y + (h - e.height) / 2)), e)
            x += e.width
            if i < len(imgs) - 1:
                if len(tokens) > 1:
                    d.text((x + gap / 2, y + h / 2), "+", font=plus, fill=col, anchor="mm")
                x += gap
    return dict(h=h, fn=fn)

def prep_cover(cov, maxw, maxh, radius=14):
    s = min(maxw / cov.width, maxh / cov.height)
    w, h = max(1, int(cov.width * s)), max(1, int(cov.height * s))
    c = cov.resize((w, h), Image.LANCZOS).convert("RGBA")
    m = Image.new("L", (w, h), 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    c.putalpha(m)
    return c

def paste_cover(im, c, x, y):
    sh = Image.new("RGBA", (c.width + 80, c.height + 80), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([40, 50, 40 + c.width, 50 + c.height], radius=14, fill=(0, 0, 0, 120))
    sh = sh.filter(ImageFilter.GaussianBlur(14))
    im.paste(sh, (int(x) - 40, int(y) - 40), sh)
    im.paste(c, (int(x), int(y)), c)

def it_cover(cov, maxw, maxh, badge, acc, bg):
    c = prep_cover(cov, maxw, maxh)
    def fn(d, im, y, cx, W):
        x = int(cx - c.width / 2)
        paste_cover(im, c, x, y)
        if badge:
            d.ellipse([x - 22, y - 22, x + 54, y + 54], fill=acc)
            d.text((x + 16, y + 16), str(badge), font=pop(40, "Bold"), fill=bg, anchor="mm")
    return dict(h=c.height, fn=fn)

def render_block(d, im, items, area, W, card=None, pad=60):
    total = sum(i["h"] for i in items)
    y0, y1 = area
    y = y0 + max(0, (y1 - y0 - total) / 2)
    if card:
        d.rounded_rectangle([90, y - pad, W - 90, y + total + pad], radius=44, fill=card[0], outline=card[1], width=5)
    cx = W / 2
    for it in items:
        it["fn"](d, im, y, cx, W)
        y += it["h"]

def render_rows(d, im, rows, area, W, ink, acc, bg, head=None):
    """rows: (cover|None, small_label, title, sub). Portada a la izquierda, texto a la derecha."""
    ah = area[1] - area[0] - 160
    scale = 1.0
    while True:
        th = int(230 * scale); tw = int(th * 0.66)
        textx = 90 + 56 + tw + 36
        tmaxw = W - 90 - 56 - textx
        built = []; total = 0
        for cov, l1, title, sub in rows:
            f1 = pop(int(34 * scale), "Bold")
            ft, lst, st = fit(d, title, lambda z: lora(z, "Bold"), tmaxw, 3, int(52 * scale), 28)
            fs = pop(int(28 * scale), "Italic")
            subl = wrap(d, sub, fs, tmaxw) if sub else []
            lh1, lht, lhs = int(f1.size * 1.3), int(st * 1.2), int(fs.size * 1.3)
            txt_h = (lh1 if l1 else 0) + lht * len(lst) + lhs * len(subl)
            rh = max(th, txt_h)
            built.append((cov, l1, f1, lst, ft, st, subl, fs, lh1, lht, lhs, txt_h, rh))
            total += rh
        gap = int(44 * scale)
        total += gap * (len(rows) - 1)
        head_item = it_chip(d, head, pop(int(30 * scale), "Bold"), acc, bg) if head else None
        hh = (head_item["h"] + int(36 * scale)) if head_item else 0
        if total + hh <= ah or scale < 0.5: break
        scale -= 0.05
    full = total + hh
    y = area[0] + max(0, (area[1] - area[0] - full) / 2)
    d.rounded_rectangle([60, y - 60, W - 60, y + full + 60], radius=44,
                        fill=mix(bg, acc, 0.10), outline=mix(bg, acc, 0.45), width=5)
    if head_item:
        head_item["fn"](d, im, y, W / 2, W); y += hh
    for cov, l1, f1, lst, ft, st, subl, fs, lh1, lht, lhs, txt_h, rh in built:
        x0 = 90 + 56
        if cov is not None:
            c = prep_cover(cov, tw, th, radius=10)
            paste_cover(im, c, int(x0 + (tw - c.width) // 2), int(y + (rh - c.height) // 2))
        else:
            d.rounded_rectangle([x0, int(y + (rh - th) // 2), x0 + tw, int(y + (rh + th) // 2)], radius=10,
                                fill=mix(bg, acc, 0.22), outline=mix(bg, acc, 0.5), width=3)
            e = emoji_img("\U0001F4D6", int(tw * 0.5))
            im.paste(e, (int(x0 + (tw - e.width) // 2), int(y + (rh - e.height) // 2)), e)
        ty = y + (rh - txt_h) / 2
        if l1:
            d.text((textx, ty + lh1 / 2), l1, font=f1, fill=acc, anchor="lm"); ty += lh1
        for ln in lst:
            d.text((textx, ty + lht / 2), ln, font=ft, fill=ink, anchor="lm"); ty += lht
        for ln in subl:
            d.text((textx, ty + lhs / 2), ln, font=fs, fill=ink, anchor="lm"); ty += lhs
        y += rh + gap

# ---------------------------------------------------------------- slides
def base(W, H, theme, plat, idx, total):
    bg, ink, acc = [hexc(x) for x in THEMES[theme]]
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([34, 34, W - 34, H - 34], radius=36, outline=mix(bg, acc, 0.55), width=6)
    hy = 110 if plat == "ig" else 270
    lupa(d, W/2 - 235, hy, 20, acc, 6)
    d.text((W/2 - 195, hy), "COZY MYSTERY CORNER", font=pop(30, "Medium"), fill=ink, anchor="lm")
    if plat == "ig":
        d.text((W/2, H - 80), f"{idx} / {total}     {HANDLE}", font=pop(28, "Medium"), fill=mix(bg, ink, 0.6), anchor="mm")
        area = (190, H - 140)
    else:
        d.text((W/2, hy + 52), HANDLE, font=pop(26, "Regular"), fill=mix(bg, ink, 0.6), anchor="mm")
        area = (400, H - 440)
    return im, d, bg, ink, acc, area

def render_slide(sl, theme, plat, idx, total):
    W, H = 1080, (1350 if plat == "ig" else 1920)
    im, d, bg, ink, acc, area = base(W, H, theme, plat, idx, total)
    kind = sl["k"]; mw = W - 240
    card = (mix(bg, acc, 0.10), mix(bg, acc, 0.45))
    if kind == "cover":
        items = [it_emoji(d, sl["emo"], 170, mw, ink), it_space(50)]
        maxh = (area[1] - area[0]) - 640
        sz = 118
        while sz > 56:
            f, ls, s = fit(d, sl["title"], lambda z: lora(z, "Bold"), mw, 5, sz, 50)
            if len(ls) * s * 1.18 <= maxh: break
            sz -= 6
        items += [it_lines(ls, f, ink, int(s * 1.18)), it_space(40), it_bar(220, 10, acc), it_space(40)]
        items += [it_text(d, sl["sub"], pop(40, "Medium"), acc, mw)]
        items += [it_space(70), it_chip(d, "SWIPE", pop(32, "Bold"), acc, bg, arrow=True)]
        render_block(d, im, items, area, W)
    elif kind == "book":
        cov = sl.get("cover")
        if cov is not None:
            fT, lsT, sT = fit(d, sl["title"], lambda z: lora(z, "Bold"), mw, 2, 62, 38)
            txt = []
            if sl.get("tag"): txt += [it_chip(d, sl["tag"], pop(26, "Bold"), mix(bg, acc, 0.18), acc, pady=8), it_space(14)]
            txt += [it_lines(lsT, fT, ink, int(sT * 1.2))]
            if sl.get("author"): txt += [it_space(8), it_text(d, "by " + sl["author"], pop(34, "Medium"), ink, mw)]
            if sl.get("series"): txt += [it_space(4), it_text(d, sl["series"], pop(28, "Italic"), acc, mw)]
            th = sum(i["h"] for i in txt)
            ch = min(820, (area[1] - area[0]) - th - 90)
            items = [it_cover(cov, W - 380, ch, sl["n"], acc, bg), it_space(46)] + txt
            render_block(d, im, items, area, W)
        else:
            items = [it_badge(str(sl["n"]), 62, acc, bg, 66), it_space(34)]
            if sl.get("tag"): items += [it_chip(d, sl["tag"], pop(30, "Bold"), mix(bg, acc, 0.18), acc), it_space(24)]
            f, ls, s = fit(d, sl["title"], lambda z: lora(z, "Bold"), mw - 40, 4, 92, 54)
            items += [it_lines(ls, f, ink, int(s * 1.2)), it_space(28), it_bar(160, 8, acc), it_space(28)]
            if sl.get("author"): items += [it_text(d, "by " + sl["author"], pop(44, "Medium"), ink, mw - 40), it_space(12)]
            if sl.get("series"): items += [it_text(d, sl["series"], pop(36, "Italic"), acc, mw - 40)]
            render_block(d, im, items, area, W, card=card)
    elif kind == "clue":
        items = [it_chip(d, f"CLUE {sl['n']}", pop(34, "Bold"), acc, bg), it_space(60)]
        items += [it_emoji(d, sl["tok"], 210, W - 330, ink), it_space(60)]
        items += [it_text(d, "What\u2019s the title?", lora(70, "Bold"), ink, mw), it_space(24)]
        items += [it_text(d, "Answers on the last slide", pop(32, "Regular"), acc, mw)]
        render_block(d, im, items, area, W, card=card)
    elif kind == "answers":
        rows = [(it.get("cover"), f"#{n}", it["title"], it.get("sub", "")) for n, it in enumerate(sl["items"], 1)]
        render_rows(d, im, rows, area, W, ink, acc, bg, head="THE ANSWERS")
    elif kind == "dates":
        rows = [(it.get("cover"), it["date"], it["title"], it.get("sub", "")) for it in sl["items"]]
        render_rows(d, im, rows, area, W, ink, acc, bg, head=sl["head"])
    elif kind == "cta":
        items = [it_emoji(d, sl["emo"], 150, mw, ink), it_space(50)]
        f, ls, s = fit(d, sl["text"], lambda z: lora(z, "Bold"), mw, 5, 92, 56)
        items += [it_lines(ls, f, ink, int(s * 1.2)), it_space(44), it_bar(200, 10, acc), it_space(44)]
        items += [it_text(d, "Comment \u00b7 Save \u00b7 Share", pop(38, "Medium"), acc, mw), it_space(30)]
        items += [it_chip(d, "FOLLOW " + HANDLE, pop(30, "Bold"), acc, bg)]
        render_block(d, im, items, area, W)
    return im

# ---------------------------------------------------------------- main
def load_week(name):
    spec = importlib.util.spec_from_file_location(name, f"{name}.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod

def attach_covers(slides):
    for s in slides:
        if s["k"] == "book":
            s["cover"] = get_cover(s["title"], s.get("author", ""))
        elif s["k"] in ("answers", "dates"):
            for it in s["items"]:
                it["cover"] = get_cover(it["title"])

def build(week):
    global AUTHORS
    mod = load_week(week)
    AUTHORS = {norm(k): v for k, v in getattr(mod, "AUTHORS", {}).items()}
    if os.path.exists(OUT): shutil.rmtree(OUT)
    os.makedirs(OUT)
    cap = [f"# Cozy Mystery Corner \u00b7 {week} \u00b7 Captions y hashtags\n"]
    for pidx, p in enumerate(mod.POSTS):
        print("Post", p["id"], p["name"])
        n = 0; slides = []
        for s in p["slides"]:
            s = dict(s)
            if "items" in s: s["items"] = [dict(i) for i in s["items"]]
            if s["k"] == "book": n += 1; s["n"] = n
            slides.append(s)
        attach_covers(slides)
        # Libros sin portada: se descartan de ese post (y se renumeran los que quedan)
        kept, k = [], 0
        for sl in slides:
            if sl["k"] == "book" and sl.get("cover") is None:
                DROPPED.append((p["id"], sl["title"])); continue
            if sl["k"] == "book": k += 1; sl["n"] = k
            kept.append(sl)
        slides = kept
        tot = len(slides)
        wd = p["day"].split()
        folder = f"{p['id']}_{wd[0].lower()}{wd[1]}_{p['slot'].replace(':', '').replace(' ', '')}_{p['name']}"
        for plat in ("ig", "tt"):
            pdir = os.path.join(OUT, "instagram" if plat == "ig" else "tiktok", folder)
            os.makedirs(pdir)
            for i, s in enumerate(slides, 1):
                img = templates.render(sys.modules[__name__], s, plat, i, tot, pidx, p["theme"]) if USE_TPL else None
                if img is None: img = render_slide(s, p["theme"], plat, i, tot)
                if USE_TPL: img.convert("RGB").save(os.path.join(pdir, f"slide_{i}.jpg"), quality=90, optimize=True)
                else: img.save(os.path.join(pdir, f"slide_{i}.png"), optimize=True)
        cap.append(f"\n## {p['id']} \u00b7 {p['day']} \u00b7 {p['slot']} \u00b7 {p['fmt']}\n")
        ttl = next((s["title"] for s in p["slides"] if s["k"] == "cover"), p["name"])
        cap.append(f"**T\u00cdTULO:** {ttl}\n")
        cap.append(f"**Carpeta:** {folder}\n")
        cap.append(f"**INSTAGRAM caption:**\n{p['ig']}\n\n{mod.IGB} {p['igx']}\n")
        cap.append(f"**TIKTOK caption:**\n{p['tt']} {mod.TTB} {p['ttx']}\n")
    open(os.path.join(OUT, f"captions_{week}.md"), "w", encoding="utf-8").write("\n".join(cap))
    found = [v for v in REPORT.values() if v[1] != "NO ENCONTRADA"]
    miss = [(s, v[0]) for s, v in REPORT.items() if v[1] == "NO ENCONTRADA"]
    rep = ["# Informe de portadas\n", f"Encontradas: {len(found)} \u00b7 Faltan: {len(miss)}\n"]
    if miss:
        rep.append("\n## Faltan (sube la imagen a covers_manual/ con este nombre y vuelve a ejecutar)\n")
        rep += [f"- {t}  ->  covers_manual/{s}.jpg" for s, t in miss]
    if DROPPED:
        rep.append("\n## Descartados de su post (sin portada). Revisa captions que mencionen cuantos libros hay\n")
        rep += [f"- {pid}: {t}" for pid, t in DROPPED]
    rep.append("\n## Encontradas\n")
    rep += [f"- {t} ({src})" for t, src in sorted(found)]
    open(os.path.join(OUT, "covers_report.md"), "w", encoding="utf-8").write("\n".join(rep))
    print("Portadas encontradas:", len(found), "| faltan:", len(miss))
    for pid, t in DROPPED: print("  descartado", pid, t)

if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "week1")
