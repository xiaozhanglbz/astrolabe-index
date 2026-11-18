# Astrolabe（星盘）

**你的 agent 不需要你整个档案库。它需要一张地图。**

[![tests](https://github.com/xiaozhanglbz/astrolabe-index/actions/workflows/tests.yml/badge.svg)](https://github.com/xiaozhanglbz/astrolabe-index/actions/workflows/tests.yml)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)
![license](https://img.shields.io/badge/license-MIT-green)

Astrolabe 给一个装着旧稿、旧版本、导出文件的目录，建一份很小的**只读**分层索引，
让 AI agent 能直接走到它要的那个文件，而不是把整个目录塞进上下文。

三级结构：**册 → 章 → 页**。几 KB 的 JSON。没有服务、没有数据库、没有向量库、
不要 API key，只用 Python 3.10+ 和标准库。

---

## 要解决的问题

你把 agent 指向一个有八百个文件的目录，它只有两条烂路可走。

**全塞进去。** 上下文被文件列表填满，真正的问题被埋在中段，每个 token 都要付钱。

**瞎搜。** `ls`、`grep`、`find`——agent 猜文件名，漏掉那个叫「2024-备份-最终版」的
目录，最后回头问你文件在哪。而这正是你想避免的事。

agent 真正需要的不是档案本身，是**档案的地图**。

## 思路

Astrolabe 把目录走一遍，写出一份小目录，描述的是**东西放在哪**，不是**里面写了什么**：

- **册**——一簇相关材料（一个项目、一个客户、一年），带页数、体积、关键词，
  和一个冷热提示（hot / warm / cold）。
- **章**——册里的一个分区，对应一条 entry 路径。
- **页**——真正的文件，按路径可达。

agent 先读总目录（几 KB），挑一个册，读那个册的文件（再几 KB），然后只打开它要的那几页。
三次小读，替代一次巨型读。

你的目录一个字节都不动。索引放在 `_index/`，是生成物，随时能删——重建就是全量重扫，
对正常规模的档案远不到一秒。

## 和别的东西差在哪

**对比 grep / glob / find**——它们只在你已经知道名字时管用。Astrolabe 先给 agent
一张地形图，让它决定**去哪儿找**，再开始匹配字符串。

**对比 RAG / 向量库**——那套要切片、要嵌入模型、要向量库、要检索器，回答的是
「哪段文字和这个问题相似」。Astrolabe 回答的是「我该打开哪个文件」。它是导航层，
不是检索层，而且 0.2 秒跑完，全程不用模型。

**对比 wiki 生成器**——那些会把你的材料重写成一个新知识库。Astrolabe 什么都不重写，
你的档案原样不动，一个字节都不变。

**对比记忆工具**——那些管 agent **记得什么**，Astrolabe 管 agent **找得到什么**。
两个问题，两份文件。

## 三十秒跑起来

不用安装：

```bash
git clone https://github.com/xiaozhanglbz/astrolabe-index
cd astrolabe-index

# 1. 造一份合成演示档案
python3 examples/make_demo.py /tmp/demo-archive

# 2. 建索引
python3 -m astrolabe build /tmp/demo-archive --split-threshold 30

# 3. 和文件系统对账
python3 -m astrolabe check /tmp/demo-archive

# 4. 看体积
python3 -m astrolabe stats /tmp/demo-archive
```

然后指向真实目录：

```bash
python3 -m astrolabe build ~/Documents/old-projects
```

## 安装

需要 Python 3.10 或更高，零依赖。

```bash
# 方式一：克隆即跑，不装任何东西
git clone https://github.com/xiaozhanglbz/astrolabe-index
cd astrolabe-index
python3 -m astrolabe --version

# 方式二：装上 `astrolabe` 命令
pip install -e .

# 方式三：隔离安装
pipx install .
```

## 使用

```bash
# 构建或重建索引（只写 <目录>/_index/，不碰别的东西）
astrolabe build ~/archive

# 针对子目录特别大的目录调小切分阈值
astrolabe build ~/archive --split-threshold 50

# 对账：索引和文件系统是否一致（只读，不一致时退出码 1）
astrolabe check ~/archive

# 报告索引体积和每页字节数
astrolabe stats ~/archive

# 直接把总目录打到 stdout
astrolabe build ~/archive --json
```

三个子命令共用同一组参数，所以 `build`、`check`、`stats` 说的永远是指同一份索引。

## 怎么载入 agent

索引就是普通 JSON，任何能读文件的 agent 都能用。由轻到重四种接法。

### 一、Claude Code——作为 Agent Skill

```bash
mkdir -p ~/.claude/skills/archive-index
cp SKILL.md ~/.claude/skills/archive-index/SKILL.md
```

也可以放在项目里：`.claude/skills/archive-index/SKILL.md`。Claude Code 会自动加载，
遇到满是旧文件的目录时自己用上。

### 二、Codex CLI／任何读 `AGENTS.md` 的 agent

往 `AGENTS.md` 里加这一段：

```markdown
## 在大目录里定位文件
本仓库的档案已用 Astrolabe 建索引。
搜索之前先读 `_index/00_catalog.json`，再读它指向的册文件，然后按页路径打开。
不要把整个档案塞进上下文。
索引看着旧了就跑 `astrolabe check <dir>`；重建用 `astrolabe build <dir>`。
```

### 三、Cursor——作为项目规则

同一段存成 `.cursor/rules/astrolabe.mdc`（或加进 `.cursorrules`），效果一样。

### 四、任意 agent——贴进系统提示词

```text
当一个目录超过大约 50 个文件、而你要在里面找东西时，先找 `_index/00_catalog.json`。

有就先读它（只有几 KB）。从 `volume_list` 挑一个册，读那个册的 `file`，
再打开需要章节的 `entry` 路径。
说「没有这个文件」之前，先看 `_index/gaps.json`。

没有但目录重要：跑一次 `python3 -m astrolabe build <dir>`，然后同上。
```

这段话就是全部协议。剩下的都是便利。

### 五、Python 调用

```python
from pathlib import Path
from astrolabe.core import Config, build

result = build(Config(root=Path("~/archive").expanduser()))
print(result["master"]["volumes"], result["master"]["total_pages"])
```

## 产出什么

```
archive/
├── project-a_20250615/          ← 你的文件，原样不动
├── project-b_2024/
└── _index/                      ← 生成的，随时可删
    ├── 00_catalog.json          ← 第一个读它（几 KB）
    ├── 01_project-a.json        ← 一个册一个文件
    ├── 02_project-b.json
    └── gaps.json                ← 被跳过的文件，以及原因
```

`00_catalog.json` 节选：

```json
{
  "about": "Hierarchical, read-only index. Search order: ...",
  "volumes": 2,
  "total_pages": 338,
  "how_to_search": ["Volume level: ...", "Chapter level: ...", "Page level: ..."],
  "volume_list": [
    {
      "volume": "project-a",
      "file": "_index/01_project-a.json",
      "pages": 338,
      "chapters": 8,
      "size": "4.2M",
      "keywords": ["mockup", "wireframes", "checkout", "20250615"],
      "updated": "2026-08-20",
      "heat": "hot",
      "entry": ["project-a_20250615/", "project-a_20250820/"]
    }
  ]
}
```

每个册文件里有 `chapter_list`，每章带 `entry` 路径，以及 `page_list`（小章）
或 `sample_pages` + `page_distribution`（大章，需要列目录才能看全）。

## agent 该怎么读

1. 读 `_index/00_catalog.json`，从 `volume_list` 挑一个册。
2. 读该册的 `file`，`chapter_list` 里每项都有 `entry` 路径。
3. 按 `entry` 打开页；有 `page_distribution` 的章要列目录才能看全。
4. 说「没有这个文件」之前，先看 `_index/gaps.json`。

就这四步。三次小读，一个答案。

## 参数

| 参数 | 默认 | 含义 |
|---|---|---|
| `-o, --out` | `_index` | 索引目录名 |
| `--split-threshold` | `200` | 章内页数超过此值时，往下再切一层 |
| `--list-threshold` | `20` | 章内页数不超过此值时逐页列名，超过则给样本 |

册的聚类规则在 `astrolabe/core.py` 的 `Config.group_patterns` 里
（`proj_20250615` 和 `proj_2024` 这类带日期的目录会归到同一个册），
跳过规则在同文件的 `skip_ext` 和 `skip_dirs`。

## 性能

合成档案实测，单次运行，无缓存：

| 页数 | 构建耗时 | 索引体积 | 峰值内存 |
|---|---|---|---|
| 5,000 | 0.25 秒 | 216 KB | 约 15 MB |
| 20,000 | 0.82 秒 | 619 KB | 约 16 MB |

折算下来每页 32–44 字节，路径越长越高。小档案会被固定开销拖累——73 页的演示档案
报出来是每页约 120 字节——但规模上去后，每页成本就落在几十字节这一档。
两万页的档案，全部 JSON 加起来还不到 1 MB。

没有增量模式：每次都是全量重扫。这个速度下，重建比重维护缓存更便宜，
而且索引永远不会和磁盘悄悄不一致。

## 边界

- **只读**。源文件从不移动、修改、删除。
- **不是搜索引擎**。它索引位置，不索引内容。要按段落检索请另配全文或语义搜索。
- **主要靠文件名**。名字有意义才索引得出来；一堆 `untitled-3.md` 救不了。
- **每次全量重建**。几万个文件没问题；不是为百万文件的冷存储盘设计的。
- **一个目录一份索引**。嵌套索引不会自动合并。

## 常见问题

**会改我的文件吗？**
不会。只在旁边生成 `_index/`。把那个目录删掉，档案和原来一模一样。

**要不要 API key、GPU、模型？**
都不要。纯标准库，可离线跑。

**能索引 PDF、图片、压缩包吗？**
记它们的名字和路径，不读内容。跳过什么会写进 `gaps.json`，所以 agent 分得清
「不存在」和「没索引」。

**`heat` 是什么？**
按修改时间给的提示：`hot` 三十天内，`warm` 半年内，其余 `cold`。
回答「我最近在弄什么」时有用。

**`_index/` 要不要提交？**
都行。提交上去 agent 不用跑就能拿到地图；不提交就是干净仓库。它是可再生的数据。

**和直接 `tree` 有什么区别？**
`tree` 给你一张平铺的路径清单，没有分组、没有关键词、没有体积、没有新旧、没有三级缩放。
八百个文件就已经读不完，两万个直接没法看。

**为什么叫 Astrolabe？**
星盘不移动星星，它只告诉你星星在哪。

## 相关的东西

- **Wiki 生成器**：把你的材料重写成新知识库。
- **记忆树**：重构 agent 已经记住的东西。
- **Markdown + 向量索引**：按相似度检索段落。
- **Astrolabe**：给 agent 一张陌生档案的只读地图，什么都不改。

是邻居，不是对手。要知识生长，用它们；要资料考古，用这个。

## 开发

```bash
python3 -m unittest discover -s tests -v     # 25 个测试，纯标准库
```

结构：`astrolabe/core.py`（构建与配置）、`astrolabe/audit.py`（对账校验）、
`astrolabe/cli.py`（命令）、`examples/make_demo.py`（合成档案生成器）、`tests/`。

## 许可

MIT。

---

如果它替你的 agent 省下了一个上下文窗口，点个 star 能让下一个人也找到它。