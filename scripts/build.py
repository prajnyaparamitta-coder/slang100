"""data/issues/*.json から、site/ のトップページと記事ページを書き出す。

使い方:  python scripts/build.py
"""
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "issues"
SITE = ROOT / "site"

MAG_TITLE = "学校では教わらない？イギリス英語のスラング100"
MAG_DESCRIPTION = "イギリス英語のスラングを一語ずつ、語源や文化的背景とともに紹介する連載。"

FONTS_LINK = (
    "https://fonts.googleapis.com/css2?"
    "family=Bebas+Neue&family=Cormorant+Garamond:ital,wght@1,600&family=DM+Serif+Display"
    "&family=Libre+Baskerville:wght@700&family=Oswald:wght@500&family=Playfair+Display:wght@700"
    "&family=Noto+Serif+JP:wght@400;600&family=Noto+Sans+JP:wght@400;500&display=swap"
)


def esc(s):
    return html.escape(s, quote=True)


def head(title, css_path, description):
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="{esc(description)}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS_LINK}">
<link rel="stylesheet" href="{css_path}">
<title>{esc(title)}</title>
</head>
"""


def load_issues():
    issues = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(DATA.glob("*.json"))]
    return sorted(issues, key=lambda d: d["number"])


def spine_style(d):
    s = d["spine"]
    return f"--spine-bg: {s['bg']}; --spine-fg: {s['fg']};"


def build_index(issues):
    rows = []
    # 新しい号ほど上に積む
    for d in sorted(issues, key=lambda d: -d["number"]):
        n = d["number"]
        rows.append(f"""      <li class="stack__item" id="issue-{n:02d}">
        <a href="issues/{n:02d}.html" class="book" style="{spine_style(d)}">
          <span class="spine spine--{d['spine']['font']}" style="view-transition-name: issue-{n:02d}; view-transition-class: issue;">
            <span class="spine__no">No.{n:02d}</span>
            <span class="spine__title" lang="en">{esc(d['slang'])}</span>
            <span class="spine__sub">{esc(d['subtitle'])}</span>
          </span>
        </a>
      </li>""")

    first, last = issues[0]["number"], issues[-1]["number"]
    page = head(MAG_TITLE, "css/style.css", MAG_DESCRIPTION) + f"""<body class="page-index">
  <header class="masthead">
    <p class="masthead__label">Web Magazine</p>
    <h1 class="masthead__title">{esc(MAG_TITLE)}</h1>
    <p class="masthead__count">第{first}回 — 第{last}回</p>
  </header>

  <main class="stack">
    <ul class="stack__list" role="list">
{chr(10).join(rows)}
    </ul>
  </main>

  <footer class="footer">
    <p>&copy; All rights reserved.</p>
  </footer>
</body>
</html>
"""
    (SITE / "index.html").write_text(page, encoding="utf-8")


def build_article(d, numbers):
    n = d["number"]
    idx = numbers.index(n)
    prev_n = numbers[idx - 1] if idx > 0 else None
    next_n = numbers[idx + 1] if idx < len(numbers) - 1 else None
    prev_link = f'<a href="{prev_n:02d}.html" class="pager__link pager__link--prev">← 第{prev_n}回</a>' if prev_n else "<span></span>"
    next_link = f'<a href="{next_n:02d}.html" class="pager__link pager__link--next">第{next_n}回 →</a>' if next_n else "<span></span>"

    page = head(f"第{n}回 {d['slang']} | {MAG_TITLE}", "../css/style.css", f"{d['slang']} ― {d['subtitle']}") + f"""<body class="page-article" style="{spine_style(d)}">
  <a href="../index.html#issue-{n:02d}" class="back">← 一覧に戻る</a>

  <article class="article">
    <img src="../images/{d['hero']}" alt="" class="article__hero" style="view-transition-name: issue-{n:02d}; view-transition-class: issue;">

    <header class="article__header">
      <p class="article__no">第{n}回</p>
      <h1 class="article__title"><span class="article__slang" lang="en">{esc(d['slang'])}</span><span class="article__subtitle">{esc(d['subtitle'])}</span></h1>
    </header>

    <div class="article__body">
{d['body_html']}
    </div>
  </article>

  <nav class="pager" aria-label="前後の回">
    {prev_link}
    <a href="../index.html#issue-{n:02d}" class="pager__link pager__link--home">一覧</a>
    {next_link}
  </nav>
</body>
</html>
"""
    (SITE / "issues" / f"{n:02d}.html").write_text(page, encoding="utf-8")


def main():
    issues = load_issues()
    if not issues:
        raise SystemExit("data/issues に記事がありません")
    (SITE / "issues").mkdir(parents=True, exist_ok=True)
    build_index(issues)
    numbers = [d["number"] for d in issues]
    for d in issues:
        build_article(d, numbers)
    print(f"{len(issues)}本の記事でサイトを書き出しました")


if __name__ == "__main__":
    main()
