"""noteのマガジンのRSSを読み、サイトにまだない回を取り込んで data/issues/NN.json を作る。

使い方:  python scripts/import_note.py

・アクセスするのは、マガジンのRSSと、まだサイトにない回の記事のページだけ。
・取り込みに失敗した回は何も書き込まない（既存のデータや画像には一切触れない）。
・一つでも失敗があれば、最後に終了コード1で終わる（GitHub Actionsで失敗として通知される）。
"""
import colorsys
import io
import json
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "issues"
IMAGES = ROOT / "site" / "images"

RSS_URL = "https://note.com/hay_ato_m/m/md6d0064fd0ea/rss"
FIRST_ISSUE = 1  # 第0回はサイトに載せない
USER_AGENT = "Mozilla/5.0 (compatible; slang100-site-updater; +https://github.com/)"
WAIT_SECONDS = 3  # 連続アクセスの間隔

TITLE_RE = re.compile(r"】\s*(.+?)\s*―\s*(.+?)\s*【第(\d+)回】")

# 自動で選ぶ背表紙の書体（回の番号で順に回す）
FONTS = ["serif-a", "condensed", "serif-b", "display", "slab", "italic"]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read()


def is_english(s):
    letters = [c for c in s if not c.isspace()]
    return bool(letters) and sum(c.isascii() for c in letters) / len(letters) > 0.8


# ---------------------------------------------------------------- RSS
def read_rss():
    root = ET.fromstring(fetch(RSS_URL))
    items = []
    for item in root.findall("./channel/item"):
        title = item.findtext("title", "")
        m = TITLE_RE.search(title)
        if not m:
            continue
        items.append({
            "number": int(m.group(3)),
            "slang": m.group(1).strip("「」"),
            "subtitle": m.group(2),
            "url": item.findtext("link", ""),
        })
    return items


# ---------------------------------------------------------------- 画像
def save_webp(url, name):
    """画像をダウンロードして site/images/name に WebP で保存する。"""
    im = Image.open(io.BytesIO(fetch(url)))
    im = im.convert("RGB")
    if im.width > 1600:
        im = im.resize((1600, round(im.height * 1600 / im.width)))
    im.save(IMAGES / name, "WEBP", quality=82)
    return im


def pick_spine_color(im):
    """ヘッダー画像の色から、背表紙の色と文字の色を決める。"""
    small = im.resize((120, 64))
    q = small.quantize(colors=6, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    best, best_score = (90, 90, 90), -1
    for count, i in q.getcolors():
        r, g, b = pal[i * 3:i * 3 + 3]
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        # 彩度があり、明るすぎも暗すぎもしない色を優先する
        score = count * (0.3 + s) * (1 - abs(l - 0.45) * 1.4)
        if score > best_score:
            best, best_score = (h, l, s), score
    h, l, s = best
    # 本の背表紙らしく、明るさと鮮やかさを整える
    l = min(max(l, 0.28), 0.5)
    s = min(max(s, 0.25), 0.6)
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    bg = "#{:02x}{:02x}{:02x}".format(round(r * 255), round(g * 255), round(b * 255))
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    fg = "#2a1a08" if lum > 0.55 else "#fdf8ee"
    return bg, fg


# ---------------------------------------------------------------- 本文の変換
def inline_html(node):
    """段落の中身を、許可したタグ（strong / a / br）だけ残して書き出す。"""
    out = []
    for c in node.children:
        if isinstance(c, NavigableString):
            out.append(escape_text(str(c)))
        elif c.name in ("strong", "b"):
            out.append(f"<strong>{inline_html(c)}</strong>")
        elif c.name in ("em", "i"):
            out.append(f"<em>{inline_html(c)}</em>")
        elif c.name == "a" and c.get("href"):
            href = escape_attr(c["href"])
            out.append(f'<a href="{href}" target="_blank" rel="noopener">{inline_html(c)}</a>')
        elif c.name == "br":
            out.append("<br>")
        else:
            out.append(inline_html(c))
    return "".join(out)


def escape_text(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def escape_attr(s):
    return escape_text(s).replace('"', "&quot;")


def split_lines(node):
    """<br> で区切られた行を、行ごとのHTMLのリストにする。"""
    lines = inline_html(node).split("<br>")
    return [l.strip() for l in lines]


def plain(html_line):
    return BeautifulSoup(html_line, "html.parser").get_text().strip()


def render_example_block(p):
    """引用ブロック（例文と訳）を、サイトの例文の形にする。空行で例文を分ける。"""
    out = []
    groups, cur = [], []
    for line in split_lines(p):
        if not line:
            if cur:
                groups.append(cur)
                cur = []
        else:
            cur.append(line)
    if cur:
        groups.append(cur)
    for g in groups:
        first, rest = g[0], g[1:]
        if is_english(plain(first)):
            en = f'<span class="article__en">{first}</span>'
            trans = "".join(f'<span class="article__trans">{l}</span>' for l in rest)
            out.append(f'<p class="article__example" lang="en">{en}{trans}</p>')
        else:
            out.append(f'<p class="article__example">{"<br>".join(g)}</p>')
    return out


def strip_bullet(line):
    return re.sub(r"^・\s*", "", line)


def render_paragraph(p):
    lines = split_lines(p)
    texts = [plain(l) for l in lines]
    # 前後の空行を落とす
    while texts and not texts[0]:
        lines, texts = lines[1:], texts[1:]
    while texts and not texts[-1]:
        lines, texts = lines[:-1], texts[:-1]
    if not texts:
        return []
    # すべての行が「・」で始まる段落は、箇条書きにする
    nonempty = [(l, t) for l, t in zip(lines, texts) if t]
    if all(t.startswith("・") for _, t in nonempty):
        items = []
        for l, t in nonempty:
            cls = ' class="is-en"' if is_english(t.lstrip("・")) else ""
            items.append(f"<li{cls}>{strip_bullet(l)}</li>")
        return [f'<ul class="article__list">{"".join(items)}</ul>']
    return ["<p>" + "<br>".join(lines) + "</p>"]


def render_figure(fig, number, counter):
    service = fig.get("embedded-service")
    caption = fig.find("figcaption")
    cap_html = inline_html(caption).strip() if caption else ""
    out = []
    if service == "youtube":
        return out  # YouTubeの埋め込みは、再生できない動画があるため載せない
    if service:
        # そのほかの埋め込み（記事カードや商品リンクなど）は、リンクだけ残す
        href = fig.get("data-src")
        strings = list(fig.stripped_strings)
        title = strings[0] if strings else href
        if href:
            out.append(f'<p class="article__embed"><a href="{escape_attr(href)}" target="_blank" rel="noopener">{escape_text(title)}</a></p>')
        return out
    img = fig.find("img")
    if img:
        src = img.get("data-src") or img.get("src")
        link = fig.find("a", attrs={"data-lightbox": True})
        if link and link.get("href"):
            src = link["href"]
        counter[0] += 1
        name = f"{number:02d}_{counter[0]}.webp"
        save_webp(src, name)
        alt = escape_attr(plain(cap_html)) if cap_html else f"第{number}回の本文中の画像"
        cap = f"<figcaption>{cap_html}</figcaption>" if cap_html else ""
        out.append(f'<figure class="article__figure"><img src="../images/{name}" alt="{alt}" loading="lazy">{cap}</figure>')
        return out
    quote = fig.find("blockquote")
    if quote:
        for p in quote.find_all("p") or [quote]:
            out.extend(render_example_block(p))
        if cap_html:
            out.append(f'<p class="article__source">{cap_html}</p>')
    return out


def paragraph_lines(p):
    lines = split_lines(p)
    return [(l, plain(l)) for l in lines]


def convert_body(body, number):
    out = []
    refs = None  # 「参考」以降は、すべて参考文献の一覧に入れる
    counter = [0]
    for el in body.children:
        if isinstance(el, NavigableString) or el.name in (None, "hr"):
            continue
        if el.has_attr("data-table-of-contents"):
            continue  # 目次は載せない

        if el.name in ("p", "ul", "ol"):
            pairs = paragraph_lines(el) if el.name == "p" else [(inline_html(li), li.get_text(strip=True)) for li in el.find_all("li")]
            nonempty = [(l, t) for l, t in pairs if t]
            if refs is None and nonempty and nonempty[0][1] == "参考":
                refs = [strip_bullet(l) for l, _ in nonempty[1:]]
                continue
            if refs is not None:
                refs.extend(strip_bullet(l) for l, _ in nonempty)
                continue

        if el.name in ("h2", "h3", "h4"):
            out.append(f'<h2 class="article__heading">{escape_text(el.get_text(strip=True))}</h2>')
        elif el.name == "p":
            out.extend(render_paragraph(el))
        elif el.name == "figure":
            out.extend(render_figure(el, number, counter))
        elif el.name in ("ul", "ol"):
            lis = "".join(f"<li>{inline_html(li)}</li>" for li in el.find_all("li"))
            out.append(f'<ul class="article__list">{lis}</ul>')
        elif el.name == "blockquote":
            out.extend(render_example_block(el))

    if refs:
        lis = "".join(f"<li>{r}</li>" for r in refs)
        out.append(f'<section class="refs"><h2 class="refs__title">参考</h2><ul class="refs__list">{lis}</ul></section>')
    return "\n".join(out)


# ---------------------------------------------------------------- 1回分の取り込み
def import_issue(item):
    n = item["number"]
    page = BeautifulSoup(fetch(item["url"]).decode("utf-8"), "html.parser")
    body = page.find(attrs={"data-name": "body"})
    if body is None:
        raise RuntimeError("本文の要素（data-name=\"body\"）が見つからない")
    if len(body.get_text(strip=True)) < 300:
        raise RuntimeError("本文が短すぎる（取り出しに失敗した可能性）")
    og = page.find("meta", property="og:image")
    if og is None or not og.get("content"):
        raise RuntimeError("ヘッダー画像（og:image）が見つからない")

    time.sleep(WAIT_SECONDS)
    hero_name = f"{n:02d}.webp"
    hero = save_webp(og["content"], hero_name)
    bg, fg = pick_spine_color(hero)

    time.sleep(WAIT_SECONDS)
    body_html = convert_body(body, n)

    data = {
        "number": n,
        "slang": item["slang"],
        "subtitle": item["subtitle"],
        "note_url": item["url"],
        "spine": {"bg": bg, "fg": fg, "font": FONTS[(n - 1) % len(FONTS)]},
        "hero": hero_name,
        "source": "note",
        "body_html": body_html,
    }
    # すべて成功してから、最後に1回だけ書き込む
    (DATA / f"{n:02d}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    IMAGES.mkdir(parents=True, exist_ok=True)
    existing = {int(p.stem) for p in DATA.glob("*.json")}

    try:
        items = read_rss()
    except Exception as e:  # RSSが読めなければ何もしない
        print(f"RSSの取得に失敗しました: {e}")
        return 1

    targets = sorted((i for i in items if i["number"] >= FIRST_ISSUE and i["number"] not in existing),
                     key=lambda i: i["number"])
    if not targets:
        print("新しい回はありません")
        return 0

    failed = []
    for item in targets:
        n = item["number"]
        try:
            import_issue(item)
            print(f"第{n}回を取り込みました: {item['slang']}")
        except Exception as e:
            failed.append(n)
            # 途中で作った画像は消しておく（データは書かれていない）
            for p in IMAGES.glob(f"{n:02d}*.webp"):
                if not (DATA / f"{n:02d}.json").exists():
                    p.unlink()
            print(f"第{n}回の取り込みに失敗しました: {e}")
        time.sleep(WAIT_SECONDS)

    if failed:
        print("失敗した回: " + ", ".join(f"第{n}回" for n in failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
