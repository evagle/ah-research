# data/filings/

首手资料的本地缓存和可复现索引。每个股票一个子目录（命名为
`<ticker>`，与 `profiles/` 一致）。

Git 只保存轻量、可审计、可重建的材料。原始 PDF、不可变版本副本和提取
缓存不提交；提交来源 URL、文件名、SHA-256、下载方法、必要的结构化结果和
研究结论。

## 目录结构

    data/filings/
    └── <ticker>/                      # e.g. 600519.SH, 0700.HK
        ├── 年报-<YYYY>.pdf             # 本地原件，已忽略
        ├── 年报-<YYYY>.pdf.source.json # 官方 URL 和 SHA-256，提交
        ├── manifests/                 # 下载选择和查询参数，提交
        ├── versions/                  # 不可变本地缓存，已忽略
        ├── _extracted/                # PDF 提取缓存，已忽略
        ├── _raw/                      # 原始 HTML/API 响应，已忽略
        ├── runs/                      # 临时运行目录，已忽略
        └── research/
            ├── source-index.md        # 来源、文件名、哈希和使用边界，提交
            └── *.pdf                  # 本地原件，已忽略

## 提交策略

- 提交 `.source.json`、不含机器绝对路径的来源 manifest、`source-index.md`
  和人工整理的研究笔记。
- 不提交 PDF、`versions/`、`_extracted/`、`_raw/`、`runs/`、下载锁和
  临时文件。
- 原始 HTML 和 API 响应统一放入 `_raw/`；可审计的结构化摘要保留在来源
  manifest 中。
- `research/*.txt` 视为 PDF 全文提取缓存，不提交；确需保留的内容整理为
  精简 Markdown，并写明来源和使用边界。
- 官方披露的提取文本只有在确实需要全文检索、内容经过检查且体积合理时才
  整理成 Markdown 提交。
- 卖方或付费资料只提交来源元数据和允许引用的研究结论，不提交完整提取文本。
- 仅修改扩展名不会压缩文本。需要归档时优先保留可读的精简 Markdown；不要
  用压缩文件替代可审计的研究结论。

## 命名规范

- **年报:** `年报-<YYYY>.pdf` — `YYYY` 为 会计年度 的 结束年 (2024 年报 = 披露 于 2025 年 但 覆盖 2024 年度)
- **招股说明书:** `招股说明书.pdf` (若 有多次发行, 加日期后缀)
- **研报:** `research/<broker-pinyin>-<title>-<YYYYMMDD>.pdf` — broker 拼音 (e.g. `zhongjin`, `huachuang`), 标题 中文原文 (FS-unsafe 字符替换为 `-`, 上限 60 字符), publishDate `YYYYMMDD`。由 `scripts/download_research.py` 自动生成。

## 下载来源

- **A 股年报:** 巨潮资讯网 http://www.cninfo.com.cn
  - 搜索 股票代码 → 公告 → 年度报告
- **H 股年报:** 香港交易所 https://www.hkexnews.hk
- **招股说明书:** 同上 (巨潮资讯网 / HKEX 披露首发档案)
- **研报:** 研究员工作站内部资源 (不赘述)

## 自动下载 (推荐)

可直接运行：

    uv run python scripts/download_filings.py 600519.SH --years 5 --include-prospectus

脚本会从巨潮资讯网下载最近 5 年年报和招股说明书到
`data/filings/600519.SH/`。H 股使用同一命令，例如：

    uv run python scripts/download_filings.py 09992.HK \
      --years 6 --end-year 2025 --as-of 2026-07-29

下载后应校验 `.source.json` 中的 SHA-256。换设备时使用相同命令即可重建
PDF、`versions/` 和后续提取缓存。

## 跨设备恢复研究资料

`research/source-index.md` 中的每个原始文件至少应记录公开 URL、本地文件名、
SHA-256 和访问限制。换设备后按索引恢复：

    curl --fail --location --retry 3 "$URL" --output "$LOCAL_FILE"
    printf '%s  %s\n' "$SHA256" "$LOCAL_FILE" | shasum -a 256 -c -

需要全文检索时再生成本地提取缓存：

    uv run python scripts/extract_pdf.py "$LOCAL_FILE" --skip-images

若原链接已经失效，来源索引必须明确标记为不可重建。此类文件不能仅凭本地
PDF 支撑可复现结论，应补充可访问的官方来源、合规存档或独立交叉证据。

## 自动下载研报 (研报自动 via download_research.py)

`scripts/download_research.py` 从 **东方财富** 免费研报 API 拉取 卖方深度研报 PDFs:

    uv run python scripts/download_research.py 600519.SH --years 3 --depth-only --max 15

CLI 参数:

- `--years N` — 往前 N 年 (默认 3).
- `--depth-only` — 仅保留 `深度 / 首次 / 覆盖 / 重大` 关键词命中 (attachType or title).
- `--max N` — 总 cap (默认 50), 避免 runaway.
- `--out <dir>` — 默认 `data/filings/<ticker>/research/`.

输出文件名: `<broker-pinyin>-<title>-<YYYYMMDD>.pdf` (e.g. `zhongjin-贵州茅台2024年报点评-批价平稳回升-20241120.pdf`).

**脚本是 idempotent** — 再跑一次会跳过已存在的 >100KB 文件 (与 `download_filings.py` 同策略)。

## Value-Profile Skill 的使用

`.claude/skills/value-profile/SKILL.md` 在 bootstrap 时会 audit 本目录。
若 `data/filings/<ticker>/` 缺少 或 年报少于 2 份, Skill 会 offer 自动运行 fetcher。
