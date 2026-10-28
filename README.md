# 学校では教わらない？イギリス英語のスラング100

noteの連載マガジンを、背表紙を積んだWebマガジンとして公開するサイト。

## フォルダ
- `site/` … 公開されるサイト（Live Server で `site/index.html` を開けば手元で見られる）
  - `css/style.css` … 見た目（手で編集する）
  - `images/` … ヘッダー画像と本文中の画像
  - `index.html`、`issues/` … 自動で書き出されるので、手で編集しない
- `data/issues/NN.json` … 1回分の記事のデータ（見出し語、副題、背表紙の色と書体、本文）
- `scripts/import_note.py` … noteのRSSを読み、新しい回を取り込む
- `scripts/build.py` … データからサイトを書き出す
- `.github/workflows/update-site.yml` … 毎朝の自動取り込みと公開

## 背表紙の色や書体を変えたいとき
`data/issues/NN.json` の `spine` の `bg`（背表紙の色）、`fg`（文字の色）、`font`（書体）を書き換えて push する。
`font` に使えるのは serif-a / serif-b / condensed / display / slab / italic。

## 手元でサイトを書き出し直すとき
```
pip install -r requirements.txt
python scripts/build.py
```
