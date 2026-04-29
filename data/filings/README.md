# data/filings/

首手资料存放处。每个股票一个子目录 (命名: `<ticker>`, 与 `profiles/` 一致)。
PDFs 承诺提交到 repo — 公开披露无版权问题, 本 repo 定位为研究材料库。

## 目录结构

    data/filings/
    └── <ticker>/                      # e.g. 600519.SH, 0700.HK
        ├── 年报-<YYYY>.pdf             # 每年一份, 最近 5 年 起步
        ├── 招股说明书.pdf               # IPO 一次性, 老公司 仍 必须下载
        └── research/                  # 可选, 卖方/买方 深度研报 (英文目录名, 与脚本输出一致)
            └── <broker-pinyin>-<title>-<YYYYMMDD>.pdf

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

一旦 `scripts/download_filings.py` 就绪 (后续 plan task), 可直接运行:

    python scripts/download_filings.py 600519.SH --years 5 --include-prospectus

脚本会自动从 巨潮资讯网 下载 最近 5 年 年报 + 招股说明书 到 `data/filings/600519.SH/`.

## 自动下载研报 (研报自动 via download_research.py)

`scripts/download_research.py` 从 **东方财富** 免费研报 API 拉取 卖方深度研报 PDFs:

    python scripts/download_research.py 600519.SH --years 3 --depth-only --max 15

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
