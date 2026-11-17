# Astrolabe（星盘）

给 AI agent 用的分层只读索引。

指向一个装着旧稿、旧版本或导出文件的目录，它写出一份很小的 JSON 目录，
让 agent 按 **册 → 章 → 页** 逐级找，而不是把整个目录塞进上下文。

源目录一个字节都不改。没有数据库、没有向量库、没有服务，只用 Python 标准库。

> 英文说明见 [README.md](README.md)；Agent Skill 入口见 [SKILL.md](SKILL.md)。

## 安装

```bash
git clone <本仓库地址>
cd astrolabe-index

python3 -m astrolabe --version     # 不安装也能直接跑
pip install -e .                   # 可选：装上后多一个 astrolabe 命令
```

需要 Python 3.9 或更高。

## 使用

```bash
# 构建或重建索引（只写 <目录>/_index/，不碰别的东西）
python3 -m astrolabe build ~/archive

# 对账：索引和文件系统是否一致（只读，不一致时退出码 1）
python3 -m astrolabe check ~/archive

# 体积统计
python3 -m astrolabe stats ~/archive
```

先用自带的演示数据试跑：

```bash
python3 examples/make_demo.py /tmp/demo-archive
python3 -m astrolabe build /tmp/demo-archive --split-threshold 30
python3 -m astrolabe check /tmp/demo-archive
```

## 产出

```
archive/
├── project-a_20250615/          ← 你的文件，原样不动
├── project-b_2024/
└── _index/                      ← 生成的，随时可删
    ├── 00_catalog.json          ← 第一个读它（几 KB）
    ├── 01_project-a.json        ← 一个册一个文件
    ├── 02_project-b.json
    └── gaps.json                ← 被跳过的文件清单
```

`00_catalog.json` 节选：

```json
{
  "volumes": 2,
  "total_pages": 338,
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
或 `sample_pages` + `page_distribution`（大章，需要列目录）。

## agent 怎么读

1. 读 `_index/00_catalog.json`，从 `volume_list` 挑一个册。
2. 读该册的 `file`，`chapter_list` 里每项都有 `entry` 路径。
3. 按 `entry` 打开页；有 `page_distribution` 的章需要列目录才能看全。
4. 说「没有这个文件」之前，先看 `_index/gaps.json`。

`SKILL.md` 把这几步封装成了 Agent Skill，Claude Code、Codex、Cursor 可直接加载。

## 参数

| 参数 | 默认 | 含义 |
|---|---|---|
| `-o, --out` | `_index` | 索引目录名 |
| `--split-threshold` | `200` | 章内页数超过此值时，往下再切一层 |
| `--list-threshold` | `20` | 章内页数不超过此值时逐页列名，超过则给样本 |

册的聚类规则在 `astrolabe/core.py` 的 `Config.group_patterns` 里
（`proj_20250615` 和 `proj_2024` 这类带日期的目录会归到同一个册），
跳过规则在同文件的 `skip_ext` 和 `skip_dirs`。

## 边界

- **只读**。源文件从不移动、修改、删除。
- **每次全量重建**。5000 页约 0.2 秒，20000 页约 0.8 秒，峰值内存 15 MB。
- **不是搜索引擎**。它索引位置，不索引内容。需要按段落检索请另配全文或语义搜索。
- **主要靠文件名**。名字有意义才索引得出来；一堆 `untitled-3.md` 救不了。

## 测试

```bash
python3 -m unittest discover -s tests -v
```

## 许可

MIT。