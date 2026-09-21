# 学习笔记站

米白主题的静态笔记站，从 Obsidian vault 里的 md 生成，发布到 GitHub Pages。
小红书只做引流：那边发几张卡片图 + 一句钩子，正文放这里。

```
vla-notes/
├── notes.json          ← 内容清单（唯一要手写的地方）
├── build.py            ← md → html
├── assets/
│   ├── style.css       ← 全部样式
│   ├── map.js          ← 关系图谱
│   ├── notes.json      ← 构建时从根目录拷来，给图谱读
│   └── img/<笔记id>/   ← 自动从 Lab 拷进来的配图
├── index.html          ← 首页（构建产物）
├── map.html            ← 图谱
├── about.html
└── notes/<笔记id>/index.html
```

构建产物直接提交（GitHub Pages 从根目录发布，不跑 CI）。

---

## 加一篇笔记

**只改 `notes.json`**，往 `notes` 数组里加一条：

```json
{
  "id": "rn02-transformer-block",
  "series": "vla",
  "num": "02",
  "title": "Transformer Block",
  "lede": "一句话说清这篇在解决什么，会出现在首页和图谱的浮层里。",
  "source": "RedNote/RN02-Transformer-Block.md",
  "date": "2026-10",
  "status": "published",
  "tags": ["transformer", "ffn"],
  "deps": ["rn01-attention"],
  "leads_to": ["rn03-autoregressive"]
}
```

| 字段 | 说明 |
|---|---|
| `id` | 目录名和图谱节点 id，定了别改（改了等于换 URL） |
| `source` | 相对 `Study/VLA学习主线/` 的 md 路径 |
| `status` | `published` 才会生成正文；其余只在首页「还没写的」和图谱里以虚线节点出现 |
| `deps` | **有向**：读这篇之前该先读哪些 |
| `leads_to` | **有向**：读完之后接哪些。和 `deps` 重复声明没关系，构建时会去重 |

然后：

```bash
conda activate vla-lab
python build.py            # 重建全站
python build.py --serve    # 顺便起 localhost:8765 看效果
```

配图不用手动拷：md 里写 `![[图名.png]]`，`build.py` 会去 Lab 里找，优先拿 `out_web/` 的网页版，找不到就退回 `out/` 的卡片版。

### 新开一个系列

往 `series` 数组加一条 `{id, name, desc}`，笔记的 `series` 字段指过去即可。
目录形态不用改代码：`deps`/`leads_to` 是线性就是线性，是树就是树，交叉引用就成网。

---

## 配图

网页版和小红书卡片版是**两套**，同一份脚本出：

```bash
cd Lab/RN01-注意力
python run-all.py              # 卡片版 → out/     （字号按 22px 底线兜底）
VLA_WEB=1 python run-all.py    # 网页版 → out_web/ （保持原字号、边距紧、dpi 220）
```

为什么分两套：卡片要贴进 1080×1440 在手机上看，图被缩到 0.5 倍，所以 `save_card()`
会把太小的字强行放大；网页上图是 700~960px 显示、还能点开看原图，不需要放大，
放大了反而笨重。规则写在 `Lab/_shared/themes.py` 顶部。

页面上的呈现按图自己的形状定，不用手工指定：

| 图的形状 | 呈现 |
|---|---|
| md 里标了 `\|N` 且 N ≤ 700 | 窄图，跟正文同一节奏 |
| 横图（宽 ≥ 高） | 挣脱到 960px，比正文栏宽 |
| 竖图（高 > 宽） | 正文栏宽 704px（挣脱了也会被高度顶回来，反而更窄） |

所有图都可以点开看原图。

---

## 发布到 GitHub Pages

一次性设置：

```bash
cd ~/Documents/Repository/vla-notes
git init && git add -A && git commit -m "init"
gh repo create <名字> --public --source=. --push     # 或到 github.com 手动建仓再 push
```

然后在仓库 **Settings → Pages** 里把 Source 设成 `Deploy from a branch`、
分支 `main`、目录 `/ (root)`。地址是 `https://<用户名>.github.io/<仓库名>/`。

想用 `<用户名>.github.io` 这种根域名，仓库名就必须叫 `<用户名>.github.io`。

之后每次更新：

```bash
python build.py && git add -A && git commit -m "add rn02" && git push
```

`.nojekyll` 已经生成，Jekyll 不会插手。

---

## 设计约定

米白暖调，和 Lab 配图的 `warm` 主题同源。所有颜色、字体、栏宽在 `style.css` 顶部的
`:root` 里，改那里就够了。

| 令牌 | 值 | 用途 |
|---|---|---|
| `--bg` | `#F8F5EF` | 页面底 |
| `--ink` | `#2E2822` | 正文 |
| `--hot` | `#B3565B` | 强调（配图里的 `#C1666B` 压暗一档以过对比度） |
| `--measure` | `44rem` | 正文栏宽，约 40 个汉字一行 |
| `--wide` | `60rem` | 图能挣脱到的宽度 |

正文衬线（Source Serif 4 + 宋体），元信息和图注等宽（IBM Plex Mono）加字距，
表格无衬线。三种字族各司其职，不混用。
