#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 vault 里的学习笔记 md 生成静态站（GitHub Pages）。

    python build.py            # 全量构建到 ./（根目录发布）
    python build.py --serve    # 构建完起本地服务看效果

内容源是 notes.json：加一篇笔记 = 往 notes 数组加一条，deps / leads_to 描述
它和别的笔记之间的**有向**依赖，首页的三种视图（线性 / 树 / 图谱）全部从这里生成。
正文来自 vault 的 md（source 字段），图从 Lab/out 自动找并拷进 assets/img/。

公式走 KaTeX 浏览器端渲染；md 里 Obsidian 的 ![[x.png|N]] 转成 <figure>，
标了宽度的当行内小图（.inset），没标的满栏，特别宽的自动挣脱到 --wide。
"""
import argparse, json, pathlib, re, shutil, sys, html as htmlmod

HERE = pathlib.Path(__file__).resolve().parent
VAULT = pathlib.Path("/Users/markwcl/Documents/Obsidian Vault/EngD-Worksapce/Study/VLA学习主线")
IMG_ROOTS = [VAULT / "Lab", VAULT / "RedNote", pathlib.Path("/Users/markwcl/Documents/Obsidian Vault")]

try:
    import mistune
except ImportError:
    sys.exit("缺 mistune：~/miniconda3/envs/vla-lab/bin/pip install mistune beautifulsoup4 pillow")
from bs4 import BeautifulSoup
from PIL import Image

# 显示宽度的公式和 Lab/_shared/themes.py 里的 web_display_width 必须一致
WEB_SCALE = 0.47
WEB_W_MIN, WEB_W_MAX, WEB_W_COL = 460, 960, 704


# ── 工具 ──────────────────────────────────────────────────────────
def find_img(name):
    for root in IMG_ROOTS:
        if not root.exists():
            continue
        hit = sorted(root.rglob(name))
        if hit:
            # 优先 Lab/out 下的原图，其次任意命中
            # out_web = 网页版（不强制放大字号、边距紧、dpi 高），优先；退回卡片版
            web = [h for h in hit if "/out_web/" in str(h)]
            card = [h for h in hit if "/out/" in str(h)]
            return (web or card or hit)[0]
    return None


def stash_math(md):
    box = []

    def keep(m):
        box.append(m.group(0))
        return f"\x00M{len(box)-1}\x00"

    md = re.sub(r"\$\$.+?\$\$", keep, md, flags=re.S)
    md = re.sub(r"(?<!\$)\$(?!\$).+?(?<!\$)\$(?!\$)", keep, md)
    return md, box


def pop_math(s, box):
    return re.sub(r"\x00M(\d+)\x00", lambda m: box[int(m.group(1))], s)


def slug(s):
    s = re.sub(r"[^\w一-鿿]+", "-", s.strip().lower())
    return s.strip("-") or "s"


# ── md → 正文 HTML ────────────────────────────────────────────────
def render_body(md_text, imgdir, rel_img):
    md_text = re.sub(r"\A---\n.*?\n---\n", "", md_text, flags=re.S)
    figs = []

    def sub_img(m):
        name, _, w = m.group(1).partition("|")
        p = find_img(name.strip())
        if p is None:
            return f"`[图片缺失：{name}]`"
        imgdir.mkdir(parents=True, exist_ok=True)
        dst = imgdir / p.name
        if not dst.exists() or p.stat().st_mtime > dst.stat().st_mtime:
            shutil.copy2(p, dst)
        try:
            iw, ih = Image.open(dst).size
        except Exception:
            iw, ih = 0, 0
        # 显示宽度 = 原图宽 × WEB_SCALE，和 themes.web_display_width 同一个公式。
        # 两边必须一致：出图时按这个宽度兜底字号，页面就得按这个宽度显示，
        # 否则兜底的 15px 底线在页面上根本不成立。
        inset = w.strip().isdigit() and int(w) <= 700
        disp = (WEB_W_MIN if inset
                else int(max(WEB_W_MIN, min(WEB_W_MAX, round(iw * WEB_SCALE)))) if iw
                else WEB_W_COL)
        cls = "wide" if disp > WEB_W_COL + 60 else ""   # 只比正文栏宽一点点就别挣脱了，错位不值得
        figs.append((p.name, cls))
        return (f'<figure class="{cls}" style="--w:{disp}px">'
                f'<img src="{rel_img}/{p.name}" alt="{htmlmod.escape(name.strip())}" '
                f'loading="lazy" width="{iw}" height="{ih}">'
                f'<button class="zoom" aria-label="放大看">⤢</button>'
                f'</figure>')

    md_text = re.sub(r"!\[\[([^\]]+)\]\]", sub_img, md_text)
    md_text = re.sub(r"(?<!!)\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", md_text)
    md_text = re.sub(r"(?<!!)\[\[([^\]]+)\]\]", r"\1", md_text)

    md_text, box = stash_math(md_text)
    body = mistune.create_markdown(escape=False, hard_wrap=True,
                                   plugins=["table", "strikethrough"])(md_text)
    body = pop_math(body, box)

    soup = BeautifulSoup(body, "html.parser")
    # md 里的第一个 h1 就是标题，页头已经渲染过，正文里删掉免得出现两次
    h1 = soup.find("h1")
    if h1:
        h1.decompose()
    # 裸 <figure> 会被 mistune 塞进 <p>，拆出来（figure 不能嵌在 p 里）
    for fig in soup.find_all("figure"):
        par = fig.find_parent("p")
        if par:
            par.insert_before(fig.extract())
    for par in soup.find_all("p"):
        if not par.get_text(strip=True) and not par.find(["img", "figure"]):
            par.decompose()
    # 表格加横向滚动容器
    for tb in soup.find_all("table"):
        wrap = soup.new_tag("div", attrs={"class": "table-wrap"})
        tb.insert_before(wrap)
        wrap.append(tb.extract())
    # 标题加 id，收集目录
    toc = []
    seen = {}
    for h in soup.find_all(["h2", "h3"]):
        t = h.get_text(strip=True)
        s = slug(t)
        seen[s] = seen.get(s, 0) + 1
        if seen[s] > 1:
            s = f"{s}-{seen[s]}"
        h["id"] = s
        toc.append((h.name, s, t))
    return str(soup), toc


# ── 页面骨架 ──────────────────────────────────────────────────────
def shell(cfg, title, body, *, rel="", extra_head="", extra_body="", nav="graph", desc=None):
    b = cfg["site"]
    og_title = htmlmod.escape(title)
    og_desc = htmlmod.escape(desc or b["tagline"])
    links = "".join(
        f'<a href="{rel}{h}"{" class=on" if k == nav else ""}>{n}</a>'
        for k, h, n in [("index", "index.html", "笔记"), ("graph", "map.html", "图谱"),
                        ("about", "about.html", "关于")])
    return f"""<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{htmlmod.escape(title)}</title>
<meta name="description" content="{htmlmod.escape(b['tagline'])}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,500;8..60,600&family=IBM+Plex+Mono:wght@400;500&family=Inter:wght@400;500&display=swap" rel="stylesheet">
<link rel="icon" href="{rel}assets/favicon.svg" type="image/svg+xml">
<meta property="og:title" content="{og_title}">
<meta property="og:description" content="{og_desc}">
<meta property="og:type" content="website">
<link rel="stylesheet" href="{rel}assets/style.css">
{extra_head}
</head><body>
<header class="site"><div class="wrap">
  <a class="brand" href="{rel}index.html">{htmlmod.escape(b['brand'])}</a>
  <nav>{links}</nav>
</div></header>
{body}
<footer class="site"><div class="wrap">© {htmlmod.escape(b['author'])} · 用实验和图把问题讲清楚</div></footer>
{extra_body}
</body></html>"""


KATEX = """<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"></script>"""

POST_JS = """<script>
document.addEventListener('DOMContentLoaded',()=>{
  if(window.renderMathInElement) renderMathInElement(document.querySelector('article'),{
    delimiters:[{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false}],
    throwOnError:false});
  // 目录跟随：当前可见的小节高亮
  const links=[...document.querySelectorAll('.toc a')];
  const map=new Map(links.map(a=>[a.getAttribute('href').slice(1),a]));
  const io=new IntersectionObserver(es=>{
    es.forEach(e=>{ if(e.isIntersecting){ links.forEach(a=>a.classList.remove('on'));
      const a=map.get(e.target.id); if(a) a.classList.add('on'); } });
  },{rootMargin:'-10% 0px -80% 0px'});
  document.querySelectorAll('article h2,article h3').forEach(h=>io.observe(h));
  // 点纲要平滑滚过去，并把 hash 写进地址栏（能分享到具体小节）
  links.forEach(a=>a.addEventListener('click',e=>{
    const el=document.getElementById(a.getAttribute('href').slice(1));
    if(!el) return;
    e.preventDefault();
    el.scrollIntoView({behavior:'smooth',block:'start'});
    history.replaceState(null,'',a.getAttribute('href'));
  }));
  // 带 hash 进来时，等图片占位算完再跳，否则会偏
  if(location.hash){
    const el=document.getElementById(location.hash.slice(1));
    if(el) setTimeout(()=>el.scrollIntoView({block:'start'}),120);
  }
  // 图进入视口时淡入
  const fo=new IntersectionObserver(es=>es.forEach(e=>{
    if(e.isIntersecting){ e.target.classList.add('in'); fo.unobserve(e.target); }
  }),{rootMargin:'0px 0px -8% 0px'});
  document.querySelectorAll('figure').forEach(f=>fo.observe(f));

  // 图放大：网页上图可以看细节，不像卡片受画幅限制
  const box=document.createElement('div'); box.className='lightbox';
  box.innerHTML='<img alt=""><button class="lb-close" aria-label="关闭">×</button>';
  document.body.appendChild(box);
  const lbImg=box.querySelector('img');
  const open=src=>{ lbImg.src=src; box.classList.add('on');
    document.body.style.overflow='hidden'; };
  const close=()=>{ box.classList.remove('on'); document.body.style.overflow=''; };
  document.querySelectorAll('figure').forEach(f=>{
    const im=f.querySelector('img'); if(!im) return;
    f.addEventListener('click',()=>open(im.currentSrc||im.src));
  });
  box.addEventListener('click',close);
  addEventListener('keydown',e=>{ if(e.key==='Escape') close(); });
});
</script>"""


def build_post(cfg, note, outdir):
    src = VAULT / note["source"]
    if not src.exists():
        print(f"  ! 源文件不存在，跳过：{src}")
        return False
    d = outdir / "notes" / note["id"]
    d.mkdir(parents=True, exist_ok=True)
    body, toc = render_body(src.read_text(encoding="utf-8"),
                            outdir / "assets" / "img" / note["id"], "../../assets/img/" + note["id"])
    # 标题包一层 span：CSS 让它默认收起、hover 整列时滑出（见 style.css 的 .toc）
    toc_html = "".join(
        f'<a href="#{i}" class="{"lv3" if lv == "h3" else ""}" title="{htmlmod.escape(t)}">'
        f'<span>{htmlmod.escape(t)}</span></a>'
        for lv, i, t in toc)
    series = next((s for s in cfg["series"] if s["id"] == note["series"]), {"name": ""})
    tags = " · ".join(note.get("tags", []))
    nxt = [n for n in cfg["notes"] if n["id"] in note.get("leads_to", [])]
    nxt_html = ""
    if nxt:
        items = "".join(
            f'<a class="next-card" href="../{n["id"]}/index.html">'
            f'<span class="num">{n["num"]}</span><b>{htmlmod.escape(n["title"])}</b>'
            f'<span>{htmlmod.escape(n.get("lede",""))}</span></a>'
            if n.get("status") == "published" else
            f'<span class="next-card soon"><span class="num">{n["num"]}</span>'
            f'<b>{htmlmod.escape(n["title"])}</b><span>{htmlmod.escape(n.get("lede",""))}</span></span>'
            for n in nxt)
        nxt_html = f'<div class="col"><h4 style="margin-top:3rem">接下来</h4><div class="next-row">{items}</div></div>'

    page = f"""
<div class="wrap post-head"><div class="col">
  <div class="eyebrow">{htmlmod.escape(series["name"])} · {note["num"]}</div>
  <h1 class="title">{htmlmod.escape(note["title"])}</h1>
  <p class="lede">{htmlmod.escape(note.get("lede",""))}</p>
  <div class="byline"><span>{note.get("date","")}</span><span>{htmlmod.escape(tags)}</span></div>
</div></div>
<nav class="toc" aria-label="目录">{toc_html}</nav>
<article class="wrap"><div class="col">{body}</div>
{nxt_html}
<div class="col post-foot">本文的图全部由 Lab 里的脚本跑出来，数字可复现。</div>
</article>"""
    (d / "index.html").write_text(
        shell(cfg, f'{note["title"]} · {cfg["site"]["brand"]}', page,
              rel="../../", extra_head=KATEX, extra_body=POST_JS, nav="index",
              desc=note.get("lede")),
        encoding="utf-8")
    return True


def build_index(cfg, outdir):
    b = cfg["site"]
    rows = []
    for se in cfg["series"]:
        items = [n for n in cfg["notes"] if n["series"] == se["id"]]
        pub = [n for n in items if n.get("status") == "published"]
        soon = [n for n in items if n.get("status") != "published"]
        cards = "".join(
            f'<a class="entry" href="notes/{n["id"]}/index.html">'
            f'<span class="num">{se["name"]} / {n["num"]}</span>'
            f'<h2>{htmlmod.escape(n["title"])}</h2>'
            f'<p>{htmlmod.escape(n.get("lede",""))}</p>'
            f'<span class="meta">{" · ".join(n.get("tags",[]))}</span></a>' for n in pub)
        queue = "".join(
            f'<li><span class="num">{n["num"]}</span>'
            f'<b>{htmlmod.escape(n["title"])}</b>'
            f'<span>{htmlmod.escape(n.get("lede",""))}</span></li>' for n in soon)
        q_html = (f'<details class="queue"><summary>还没写的 {len(soon)} 篇</summary>'
                  f'<ol>{queue}</ol></details>') if soon else ""
        rows.append(f'<section class="col"><h4>{htmlmod.escape(se["name"])}</h4>'
                    f'<p class="series-desc">{htmlmod.escape(se["desc"])}</p>'
                    f'{cards}{q_html}</section>')
    page = f"""
<div class="wrap hero"><div class="col">
  <h1>{htmlmod.escape(b["tagline"])}</h1>
  <p>{htmlmod.escape(b["intro"])}</p>
</div></div>
<div class="wrap" style="padding-bottom:5rem">{"".join(rows)}</div>"""
    (outdir / "index.html").write_text(
        shell(cfg, b["title"], page, nav="index"), encoding="utf-8")


def build_about(cfg, outdir):
    b = cfg["site"]
    page = f"""
<div class="wrap post-head"><div class="col">
  <h1 class="title">关于</h1>
  <p class="lede">{htmlmod.escape(b["intro"])}</p>
</div></div>
<article class="wrap"><div class="col">
<p>这里放的是我自己的学习笔记。写法只有一条规矩：<strong>每篇从一个我答不上来的问题开始</strong>，
做实验、画图、把它讲到自己能复述为止。不写综述，不抄结论。</p>
<p>所有配图都是脚本跑出来的，数字可复现；正文里出现的每个数，都能在对应的图或表里找到出处。</p>
<h2 id="how">怎么读</h2>
<p><strong>线性</strong>：按编号顺序读，每篇解决上一篇留下的问题。
<strong>图谱</strong>：如果你只关心某个点，去<a href="map.html">图谱</a>找它，
再顺着箭头往回看它依赖什么。箭头是有向的，指向「读完这篇才好读下一篇」。</p>
</div></article>"""
    (outdir / "about.html").write_text(
        shell(cfg, f'关于 · {b["brand"]}', page, nav="about"), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE))
    ap.add_argument("--serve", action="store_true")
    a = ap.parse_args()
    outdir = pathlib.Path(a.out).resolve()
    cfg = json.loads((HERE / "notes.json").read_text(encoding="utf-8"))

    (outdir / "assets").mkdir(parents=True, exist_ok=True)
    (outdir / ".nojekyll").write_text("")
    (outdir / "assets" / "notes.json").write_text(
        json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    n_ok = 0
    for note in cfg["notes"]:
        if note.get("status") == "published" and note.get("source"):
            if build_post(cfg, note, outdir):
                n_ok += 1
                print(f"  ✓ notes/{note['id']}/")
    build_index(cfg, outdir)
    build_about(cfg, outdir)
    build_map(cfg, outdir)
    print(f"\n{n_ok} 篇正文 + 首页 + 图谱 + 关于 → {outdir}")

    if a.serve:
        import http.server, socketserver, functools, webbrowser, threading
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(outdir))
        with socketserver.TCPServer(("", 8765), h) as sv:
            print("http://localhost:8765  (Ctrl-C 停)")
            threading.Timer(1, lambda: webbrowser.open("http://localhost:8765")).start()
            sv.serve_forever()


def build_map(cfg, outdir):
    page = """
<div class="wrap post-head"><div class="col">
  <div class="eyebrow">MAP</div>
  <h1 class="title">笔记之间怎么连</h1>
  <p class="lede">箭头是有向的：从「得先读这篇」指向「然后才好读这篇」。
  点任意一个节点会把视野收到它的直接上下游，再点一次放开。</p>
</div></div>
<div class="wrap map-wrap">
  <div class="map-toolbar">
    <span class="map-hint">hover 看上下游 · 点击锁定 · 拖动摆位置 · 滚轮缩放</span>
  </div>
  <div id="stage"><svg id="graph"></svg><div id="tip"></div></div>
  <div id="panel" class="map-panel" hidden></div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>
<script src="assets/map.js"></script>"""
    (outdir / "map.html").write_text(
        shell(cfg, "图谱 · 学习笔记", page, nav="graph"), encoding="utf-8")


if __name__ == "__main__":
    main()
