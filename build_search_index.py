"""
全站搜索索引生成 → search.json(纯 Python 标准库, 无外部依赖)

数据源(按优先级):
  1. publish.ROOT_ARTIFACTS 首页卡片元数据(标题/描述/类型/日期)
  2. reports/*.md 专题报告全文
  3. market-briefings/latest.md + archive 最近 60 篇全文
  4. knowledge/manifest.json 非 private 条目(title/desc/tags/topic;
     html/md 型条目的原文件正文, 是知识库唯一可得的正文文本)
  5. 公开内容页 HTML 可见文本(radar/cockpit/lending-rate-floor 等)

排除: 密码门页 / 私人专区 / radar-site 478 个公司页(总表已覆盖)
挂点: publish.py main()、client_radar/sync_to_everstead.py publish()
"""
import json
import os
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import publish  # 复用 SITE / ROOT_ARTIFACTS / load_briefing_info / briefing_date

SITE = Path(__file__).parent
OUT = SITE / "search.json"

TEXT_CAP = 64_000        # 单页可见文本上限(radar.html 实测提取约 57K, 全量落入)
ITEM_TEXT_CAP = 8_000    # 普通条目正文上限
BRIEFING_KEEP = 60       # 归档点评最多收录篇数

# 绝对禁止索引(密码门/私人专区/自引用)。相对 SITE, 正斜杠, 小写
# knowledge/iflyink-notes/ 是私人专区(不在 manifest, 有密码门);
# union-card-handbook-2026 / motherland-100 是 manifest private 条目
PRIVATE_PREFIXES = (
    "private.html", "client-list.html", "client-list-lite.html",
    "tools/counterparty/", "tools/meal/", "tools/nursery/",
    "tools/nursery-parents/", "tools/family-links/",
    "tools/baby-name-board/", "tools/naming/",
    "knowledge/iflyink-notes/",
    "knowledge/union-card-handbook-2026/",
    "knowledge/motherland-100/",
    "radar-site/",
)
SKIP_FILES = {"index.html", "index-template.html", "kb.html", "search.json"}

# 补关键词: (页面相对路径, 空格分隔关键词) 构建期并入条目 text。
# lending-rate-floor 的 51 档期限只存在于页内 JS DATA(term 写作"10年"),
# "10年期自律利率"这类组合词靠正文 bigram 命不中, 显式补齐。
EXTRA_KEYWORDS = (
    ("lending-rate-floor.html",
     "10年期 10年 2.65% 10年期自律利率 自律利率 期限 档位 "
     "6个月 2.08% 1年 2.11% 2年 2.19% 3年 2.29% 4年 2.34% 5年 2.41% "
     "7年 2.48% 8年 2.53% 9年 2.58% 10年 2.65% 12年 2.74% "
     "15年 2.85% 20年 2.92% 30年 2.95% 50年 3.03% 51档"),
    ("radar.html", "信托 理财子 收益凭证 结构性存款 上市公司 闲置资金 公告"),
)

# 与 publish.py 的 EXCLUDED_REPORTS 口径一致(老板点名下线的报告, 搜索同样不索引)
EXCLUDED_REPORTS = {"光大理财-客户拜访调研-五看六定"}

# 公开内容页枚举: 根目录 + product-onepagers + tools/shandong(其余 tools/ 子目录是私人专区)
CONTENT_GLOBS = ("*.html", "product-onepagers/*.html", "tools/shandong/*.html")


def is_private(rel: str) -> bool:
    rel = rel.replace("\\", "/").lower()
    return any(rel.startswith(p) for p in PRIVATE_PREFIXES)


# ---- HTML 可见文本提取(html.parser: 容错强, 实体自动解码, 跳过脚本样式) ----
_SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "canvas", "head"}
_BLOCK_TAGS = {"p", "br", "li", "tr", "td", "th", "h1", "h2", "h3", "h4",
               "div", "section", "blockquote", "table", "article", "main"}


class _TextExtractor(HTMLParser):
    def __init__(self, cap: int):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.n = 0
        self.cap = cap
        self.skip: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self.skip.append(tag)
        elif tag in _BLOCK_TAGS:
            self._space()

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            if self.skip and self.skip[-1] == tag:
                self.skip.pop()
        elif tag in _BLOCK_TAGS:
            self._space()

    def handle_data(self, data):
        if self.skip or self.n >= self.cap:
            return
        t = re.sub(r"\s+", " ", data)
        if t.strip():
            self.parts.append(t)
            self.n += len(t)

    def _space(self):
        if self.parts and not self.parts[-1].endswith(" "):
            self.parts.append(" ")


def html_to_text(html: str, cap: int = TEXT_CAP) -> str:
    x = _TextExtractor(cap)
    x.feed(html)
    return "".join(x.parts)[:cap]


def page_title(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def norm_py(s: str) -> str:
    """与前端 JS norm() 同规则: 全角→半角、年期→年、lower、空白折叠。"""
    out = []
    for ch in s:
        code = ord(ch)
        if 0xFF10 <= code <= 0xFF19:      # 全角数字
            out.append(chr(code - 0xFEE0))
        elif 0xFF21 <= code <= 0xFF3A:    # 全角大写
            out.append(chr(code - 0xFEE0))
        elif 0xFF41 <= code <= 0xFF5A:    # 全角小写
            out.append(chr(code - 0xFEE0))
        else:
            out.append({"（": "(", "）": ")", "，": ",", "。": ".", "％": "%"}.get(ch, ch))
    return re.sub(r"\s+", " ", "".join(out).replace("年期", "年")).lower().strip()


def _item(t: str, u: str, d: str, type_: str, icon: str, text: str,
          tags: str = "", cap: int = ITEM_TEXT_CAP) -> dict:
    return {"t": t, "u": u, "d": d, "type": type_, "icon": icon,
            "tags": tags, "text": re.sub(r"\s+", " ", text).strip()[:cap]}


def build() -> dict:
    items: list[dict] = []

    # 1. 首页卡片元数据(标题/描述是首页公开信息; lan 卡无真实 URL)
    for name, path, date, icon, type_, desc in publish.ROOT_ARTIFACTS:
        url = path if path.startswith("#") else path
        items.append(_item(name, url, date, type_, icon,
                           f"{name} {desc}", cap=ITEM_TEXT_CAP))

    # 2. 专题报告全文(镜像首页排除口径)
    for md in publish.REPORTS.glob("*.md"):
        if md.stem in EXCLUDED_REPORTS:
            continue
        text = md.read_text(encoding="utf-8", errors="replace")
        items.append(_item(md.stem, f"reports/{md.stem}.html",
                           datetime.fromtimestamp(md.stat().st_mtime).strftime("%Y-%m-%d"),
                           "report", "📄", text))

    # 3. 收盘点评: latest + 归档最近 N 篇
    latest_text, latest_date = publish.load_briefing_info()
    if latest_text.strip():
        items.append(_item(f"每日收盘点评 {latest_date}", "market-briefings/index.html",
                           latest_date, "briefing", "📰", latest_text))
    archive = publish.BRIEFING_ARCHIVE
    if archive.exists():
        mds = sorted(archive.glob("*.md"), reverse=True)[:BRIEFING_KEEP]
        for md in mds:
            text = md.read_text(encoding="utf-8", errors="replace")
            date = publish.briefing_date(text, datetime.fromtimestamp(md.stat().st_mtime))
            title = text.strip().splitlines()[0].strip(" *") if text.strip() else date
            items.append(_item(f"收盘点评 {title}", f"market-briefings/archive/{md.stem}.html",
                               date, "briefing", "📰", text))

    # 4. 知识库条目(manifest; html/md 型条目把原文件正文并入 —— 知识库仅有的全文来源)
    kb_manifest = SITE / "knowledge" / "manifest.json"
    if kb_manifest.exists():
        m = json.loads(kb_manifest.read_text(encoding="utf-8"))
        topics = {t.get("slug"): t.get("name", "") for t in m.get("topics", [])}
        for it in m.get("items", []):
            if it.get("private"):
                continue
            slug, title = it.get("slug", ""), it.get("title", "")
            desc = it.get("desc", "") or ""
            tags = " ".join(it.get("tags", []) or [])
            tname = topics.get(it.get("topic", ""), "")
            text = f"{title} {desc} {tags} {tname}"
            # html/md 型条目: files/{slug}/{file} 原文可提取正文
            fname = it.get("file", "")
            if it.get("type") in ("html", "md") and slug and fname:
                src = SITE / "knowledge" / "files" / slug / fname
                if src.exists():
                    raw = src.read_text(encoding="utf-8", errors="replace")
                    text += " " + (html_to_text(raw, TEXT_CAP) if fname.endswith(".html") else raw)
            items.append(_item(title, f"knowledge/{slug}/index.html",
                               it.get("date", ""), "knowledge", "📚", text,
                               tags=tags))

    # 5. 公开内容页可见文本 + EXTRA_KEYWORDS
    extra = dict(EXTRA_KEYWORDS)
    for glob_pat in CONTENT_GLOBS:
        for f in sorted(SITE.glob(glob_pat)):
            rel = f.relative_to(SITE).as_posix()
            if f.name in SKIP_FILES or is_private(rel):
                continue
            html = f.read_text(encoding="utf-8", errors="replace")
            title = page_title(html)
            if not title:
                title = f.stem
            # <title> 常含 "· everstead" 后缀, 去掉
            title = re.split(r"\s*[·|]\s*everstead", title, flags=re.I)[0]
            text = html_to_text(html, TEXT_CAP)
            if extra.get(rel):
                text += " " + extra[rel]
            if not text.strip():
                continue
            # 类型按路径映射, 与首页分组口径一致
            type_ = "radar" if rel == "radar.html" else \
                    "cockpit" if rel in ("cockpit.html", "factors.html",
                                         "factor-ic.html", "holdings.html") else \
                    "tool"
            items.append(_item(title, rel, "", type_, "📄", text,
                               cap=TEXT_CAP if rel == "radar.html" else ITEM_TEXT_CAP))

    # 按日期倒序排(无日期的排最后), 同类查询结果天然新内容在前
    items.sort(key=lambda x: x.get("d", ""), reverse=True)
    return {"version": 2, "built": datetime.now().strftime("%Y-%m-%d"),
            "total": len(items), "items": items}


def main() -> None:
    data = build()
    # 原子写: 先落临时文件再替换, 防半截 search.json 被管道推送
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, OUT)
    size_kb = OUT.stat().st_size // 1024
    print(f"[search] search.json {data['total']} 条, {size_kb} KB, built {data['built']}")


if __name__ == "__main__":
    main()
