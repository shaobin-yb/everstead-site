"""
everstead 成果站发布脚本

用法：
  py publish.py                    # 扫描 reports/*.md 全部重建
  py publish.py <某.md 路径>       # 把新成果拷入 reports/ 并重建
  py publish.py --no-push          # 只本地构建，不 commit/push

流程：md → html（内置轻量转换，无外部依赖）→ 重建 index.html 成果列表
      → git add/commit/push（GitHub Pages 自动发布）
"""
import json
import re
import sys
import subprocess
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SITE = Path(__file__).parent
REPORTS = SITE / "reports"
BRIEFINGS = SITE / "market-briefings"
BRIEFING_ARCHIVE = BRIEFINGS / "archive"

# 站点根目录固定展品（不经过 md 转换，直接列出卡片）
# 每项: (名称, 路径, 日期, 图标, 类型, 描述)
# 类型: radar=雷达/站点  report=专题报告  tool=数据工具
# 日期写死（拷贝会刷新 mtime，避免卡片日期失真）
ROOT_ARTIFACTS = [
    ("保险资管风险责任人知识库", "kb.html", "2026-09-07", "🛡️", "kb",
     "5 大投资管理能力 · 40+ 机构风险责任人档案 · 搜索/折叠/从业经历"),
    ("税后收益率计算表", "yield-calc.html", "2026-09-07", "🧮", "tool",
     "资管产品税后收益率一键计算"),
    ("客户情报雷达", "radar.html", "2026-09-10", "📡", "radar",
     "巨潮每日公告抓取 + 受托方解析 + iFind 打分 · 页内直达 433 家公司分级站点"),
    ("产品一页通", "product-onepagers/红利质量_产品一页通.html", "2026-09-08", "📈", "tool",
     "红利质量/价值1号(净值每日更新) + 国新红利价值/深度价值(要素型) 四张一页通"),
    ("上市公司购买理财产品情况", "上市公司购买理财产品情况.html", "2026-09-07", "📊", "report",
     "上市公司闲置资金理财公告全景统计"),
    ("知识库", "knowledge/index.html", "2026-09-07", "📚", "knowledge",
     "PPT/PDF 翻页预览 + 原文件下载，按主题归档"),
    ("CRM 客户关系管理系统", "#lan-crm", "2026-09-07", "👥", "lan",
     "客户/商机/拜访纪要 · 账号 wangshaobin · 🔒 仅公司内网可访问"),
    ("工具箱", "tools.html", "2026-09-09", "🧰", "tool",
     "网页工具(山东投资3件套) + 本地工具(8个 launch:// 一键唤起) + 私人专区(密码锁)"),
    ("资管投研驾驶舱", "cockpit.html", "2026-09-09", "🖥️", "cockpit",
     "每日盘后自动更新 · 市场总览/温度/产品净值/红利·深度价值关注池异动/龙虎榜/同业新发"),
    ("因子工厂快照", "factors.html", "2026-09-09", "⚗️", "cockpit",
     "关注池 86 只 · 股息率TTM/动量/波动率/成交额 五因子本地计算"),
    ("因子 IC 回测", "factor-ic.html", "2026-09-10", "🧪", "cockpit",
     "86只周频Rank IC · 股息率TTM最强(t=5.7) · 低波异象显著 · 动量无效"),
    ("资产负债管理办法概念梳理", "保险公司资产负债管理办法-概念梳理.html", "2026-09-09", "📖", "report",
     "新规学习页 · 12张概念卡 + 人身险4项/财险3项监管指标扫盲 + IFRS9/17 + 产品化映射"),
    ("2026年贷款利率自律底线", "lending-rate-floor.html", "2026-09-10", "💹", "tool",
     "51档标准期限(6个月-50年)全档位速查 + 利率曲线 + 非标期限向上靠档计算器"),
    # 收盘点评卡片日期动态取 latest.md 的日期(见 load_briefing_info)
    ("每日收盘点评", "market-briefings/index.html", "", "📰", "briefing",
     "每个交易日收盘后更新 · 历史逐日归档"),
]

PAGE_CSS = """
body{font-family:'Microsoft YaHei',sans-serif;max-width:860px;margin:0 auto;padding:24px 20px 60px;color:#e2ecf7;background:#03060c;
background-image:radial-gradient(1100px 600px at 75% -10%,rgba(59,130,246,.14),transparent 60%),
radial-gradient(900px 500px at -10% 110%,rgba(139,92,246,.10),transparent 60%);
background-attachment:fixed;line-height:1.7}
h1{font-size:1.7em;border-bottom:2px solid rgba(34,211,238,.5);padding-bottom:8px;color:#22d3ee}
h2{font-size:1.3em;margin-top:1.6em;color:#7dd3fc}
h3{font-size:1.1em;color:#a5b4fc}
table{border-collapse:collapse;width:100%;margin:12px 0}
th,td{border:1px solid rgba(56,189,248,.16);padding:6px 10px;font-size:14px;text-align:left}
th{background:rgba(34,211,238,.1)}
code{background:rgba(13,26,48,.9);padding:1px 5px;border-radius:3px;font-size:13px;color:#7dd3fc}
blockquote{border-left:3px solid #22d3ee;margin:10px 0;padding:4px 14px;color:#a9bed6;background:rgba(34,211,238,.06)}
a{color:#67e8f9}
.back{display:inline-block;margin-bottom:16px;color:#7d92ad;font-size:13px;text-decoration:none}
"""


def md_to_html(text: str) -> str:
    """轻量 md → html：标题/表格/列表/引用/粗体/行内代码/链接。够日常报告用。"""
    lines = text.splitlines()
    out, i, in_list = [], 0, None
    while i < len(lines):
        line = lines[i]
        # 表格块
        if line.strip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                rows.append(cells)
                i += 1
            head, body = rows[0], rows[2:]  # 跳过第 2 行分隔线
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>")
            for r in body:
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            out.append("</tbody></table>")
            in_list = None
            continue
        # 标题
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            out.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
            in_list = None
            i += 1
            continue
        # 无序列表
        m = re.match(r"^\s*[-*]\s+(.*)$", line)
        if m:
            if in_list != "ul":
                out.append("<ul>")
                in_list = "ul"
            out.append(f"<li>{inline(m.group(1))}</li>")
            i += 1
            continue
        # 有序列表
        m = re.match(r"^\s*\d+[.)]\s+(.*)$", line)
        if m:
            if in_list != "ol":
                out.append("<ol>")
                in_list = "ol"
            out.append(f"<li>{inline(m.group(1))}</li>")
            i += 1
            continue
        # 引用
        if line.strip().startswith(">"):
            out.append(f"<blockquote>{inline(line.strip()[1:].strip())}</blockquote>")
            in_list = None
            i += 1
            continue
        # 分隔线
        if re.match(r"^\s*(-{3,}|\*{3,})\s*$", line):
            out.append("<hr>")
            in_list = None
            i += 1
            continue
        # 空行
        if not line.strip():
            if in_list:
                out.append(f"</{in_list}>")
                in_list = None
            i += 1
            continue
        # 普通段落（合并连续非空行）
        if in_list:
            out.append(f"</{in_list}>")
            in_list = None
        para = [line.strip()]
        while i + 1 < len(lines) and lines[i + 1].strip() and not re.match(r"^(#{1,4}\s|\||\s*[-*]\s|\s*\d+[.)]\s|>)", lines[i + 1]):
            para.append(lines[i + 1].strip())
            i += 1
        out.append(f"<p>{inline(' '.join(para))}</p>")
        i += 1
    if in_list:
        out.append(f"</{in_list}>")
    return "\n".join(out)


def inline(text: str) -> str:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', text)
    return text


def build_report(md_file: Path) -> None:
    text = md_file.read_text(encoding="utf-8", errors="replace")
    title = md_file.stem
    body = md_to_html(text)
    html = (f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1.0">'
            f'<title>{title} · everstead</title><style>{PAGE_CSS}</style></head><body>'
            f'<a class="back" href="../index.html">← everstead 成果站</a>'
            f'<h1>{title}</h1>{body}</body></html>')
    (md_file.with_suffix(".html")).write_text(html, encoding="utf-8")
    print(f"[build] {md_file.name} → html")


def load_kb_stats() -> tuple[int, str]:
    """读知识库 manifest: 返回(公开条目数, 最新日期); 不存在返回 (0, "")。
    private 条目不计数(只出现在密码门后的私人专区, 2026-09-10)。"""
    kb_manifest = SITE / "knowledge" / "manifest.json"
    if not kb_manifest.exists():
        return 0, ""
    try:
        m = json.loads(kb_manifest.read_text(encoding="utf-8"))
        items = [it for it in m.get("items", []) if not it.get("private")]
        latest = max((it.get("date", "") for it in items), default="")
        return len(items), latest
    except Exception:
        return 0, ""


BRIEF_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def briefing_date(text: str, fallback_mtime: datetime | None = None) -> str:
    """从点评首行标题提取日期; 提取失败用文件 mtime 兜底。"""
    first = text.strip().splitlines()[0] if text.strip() else ""
    m = BRIEF_DATE_RE.search(first)
    if m:
        return m.group(1)
    if fallback_mtime:
        return fallback_mtime.strftime("%Y-%m-%d")
    return ""


def load_briefing_info() -> tuple[str, str]:
    """读 latest.md: 返回(正文, 日期); 不存在返回 ("", "")。"""
    latest = BRIEFINGS / "latest.md"
    if not latest.exists():
        return "", ""
    try:
        text = latest.read_text(encoding="utf-8")
        return text, briefing_date(text, datetime.fromtimestamp(latest.stat().st_mtime))
    except Exception:
        return "", ""


def render_briefing() -> str:
    """latest.md → 首页点评栏目 HTML(默认整块收起 accordion); 无点评时返回空串。"""
    text, date = load_briefing_info()
    if not text.strip():
        return ""
    body = md_to_html(text)
    return (f'<section class="section">'
            f'<div class="section-head"><div class="bar"></div>'
            f'<div><h2>每日收盘点评</h2><div class="en">DAILY MARKET BRIEF</div></div>'
            f'<button class="briefing-toggle" id="briefing-toggle" type="button">'
            f'<span id="briefing-toggle-label">展开今日点评 ▾</span></button>'
            f'<a class="briefing-more" href="market-briefings/index.html">查看历史 →</a>'
            f'</div>'
            f'<div class="briefing-wrap" id="briefing-wrap" style="display:none">'
            f'<div class="briefing-body">{body}</div>'
            f'</div>'
            f'<script>(function(){{var w=document.getElementById("briefing-wrap"),'
            f'b=document.getElementById("briefing-toggle"),'
            f'l=document.getElementById("briefing-toggle-label");'
            f'if(!w||!b)return;'
            f'b.addEventListener("click",function(){{'
            f'var open=w.style.display!=="none";'
            f'w.style.display=open?"none":"";'
            f'l.textContent=open?"展开今日点评 ▾":"收起点评 ▴";'
            f'}});}})();</script>'
            f'</section>')


def build_briefing_archive() -> None:
    """渲染 archive/*.md → html, 并生成归档列表页(倒序)。"""
    entries = []
    mds = sorted(BRIEFING_ARCHIVE.glob("*.md"), reverse=True) if BRIEFING_ARCHIVE.exists() else []
    for md in mds:
        text = md.read_text(encoding="utf-8", errors="replace")
        date = briefing_date(text, datetime.fromtimestamp(md.stat().st_mtime))
        title = text.strip().splitlines()[0].strip(" *") if text.strip() else date
        body = md_to_html(text)
        html = (f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">'
                f'<meta name="viewport" content="width=device-width, initial-scale=1.0">'
                f'<title>{date} 收盘点评 · everstead</title><style>{PAGE_CSS}</style></head><body>'
                f'<a class="back" href="../index.html">← everstead 成果站</a>'
                f'<h1>{date} A股收评</h1>{body}</body></html>')
        (md.with_suffix(".html")).write_text(html, encoding="utf-8")
        entries.append((date, md.name, title))
        print(f"[build] 简报 {md.name} → html")
    items = "".join(
        f'<li><a href="archive/{name}"><span class="d">{date}</span>{title}</a></li>'
        for date, name, title in entries
    )
    page = (f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1.0">'
            f'<title>每日收盘点评 · 历史归档 · everstead</title><style>{PAGE_CSS}</style></head><body>'
            f'<a class="back" href="../index.html">← everstead 成果站</a>'
            f'<h1>每日收盘点评 · 历史归档</h1>'
            f'<p>共 {len(entries)} 篇，点击查看任意一天。</p>'
            f'<ul>{"".join(items) or "<li>暂无归档</li>"}</ul></body></html>')
    BRIEFINGS.mkdir(exist_ok=True)
    (BRIEFINGS / "index.html").write_text(page, encoding="utf-8")
    print(f"[build] market-briefings/index.html ({len(entries)} 篇归档)")


def fill_nav_tokens(panel: str) -> str:
    """nav-panel.html 里的 __NAV_*__ token → nav-data.json 实时值(构建期注入)。
    无数据/文件缺失 → 替换为 '—'(JS 拿到数据会再覆盖)。
    2026-09-10: 静态首屏即真实数据, fetch 失败/无 JS 也不见空白。"""
    try:
        nav = json.loads((SITE / "product-panel" / "nav-data.json").read_text(encoding="utf-8"))
    except Exception:
        nav = {}
    data = nav.get("products", {})
    prods = list(data.keys())
    tokens = {"__NAV_UPDATED__": nav.get("updated", "")}
    if prods:
        p = data[prods[0]]
        tokens["__NAV_SINCE__"] = p.get("since", "")
    for code, p in data.items():
        tok = code  # token 用完整产品代码, 与模板占位符 __NAV_ZY0049__ 等对应
        def f(x):
            return "" if x is None else ("%+.2f%%" % x if isinstance(x, (int, float)) else str(x))
        tokens[f"__NAV_{tok}__"] = ("%.4f" % p["nav"]) if isinstance(p.get("nav"), (int, float)) else "—"
        tokens[f"__PCT_{tok}__"] = f(p.get("daily_pct"))
        tokens[f"__CUM_{tok}__"] = f(p.get("cum_return"))
        tokens[f"__ANN_{tok}__"] = f(p.get("annualized"))
        tokens[f"__DD_{tok}__"] = f(p.get("max_drawdown"))
    for k, v in tokens.items():
        if not v:
            v = "—"
        panel = panel.replace(k, v)
    return panel


def build_index(reports: list) -> None:
    """从 index-template.html 科技感模板渲染首页(注入卡片 + 统计)。"""
    tpl = SITE / "index-template.html"
    if not tpl.exists():
        # 模板缺失时仍保证可发布: 复制现有 index.html 作为模板(纯卡片增量的场景)
        print("[warn] index-template.html 不存在, 跳过首页重建")
        return
    html = tpl.read_text(encoding="utf-8")
    kb_count, kb_date = load_kb_stats()
    latest_briefing_text, _ = load_briefing_info()
    briefing_html = render_briefing()

    def card(name, href, date, icon, kind, desc, delay, external=False):
        ext = ' target="_blank" rel="noopener"' if external else ''
        # lan(仅内网)卡片不携带可点击地址, href=# 不跳转, 顶部标签 LAN
        if kind == "lan":
            href = "#"
        return (f'<a class="card" data-type="{kind}" style="animation-delay:{delay:.2f}s" '
                f'href="{href}"{ext}>'
                f'<span class="corner c1"></span><span class="corner c2"></span>'
                f'<span class="corner c3"></span><span class="corner c4"></span>'
                f'<div class="card-top"><div class="card-ico">{icon}</div>'
                f'<div class="card-tag">LAN · 内网</div></div>'
                f'<div class="t">{name}</div>'
                f'<div class="m">{desc}</div>'
                f'<div class="d">{date}</div>'
                f'<span class="arrow">→</span></a>')

    def exists(path: str) -> bool:
        """外链(局域网 CRM 等)直接视为存在; 本地路径查文件。"""
        return path.startswith(("http://", "https://")) or (SITE / path).exists()

    cards, delay = [], 0.35
    for name, path, date, icon, kind, desc in ROOT_ARTIFACTS:
        # lan 卡片(仅内网)恒展示
        if kind == "lan" or exists(path):
            if kind == "knowledge" and kb_date:
                date = kb_date  # 知识库卡片日期取最新条目日期
            if kind == "briefing":
                date = briefing_date(latest_briefing_text) or datetime.fromtimestamp(
                    (SITE / path).stat().st_mtime).strftime("%Y-%m-%d")
            cards.append(card(name, path, date, icon, kind, desc, delay,
                              external=path.startswith(("http://", "https://"))))
            delay += 0.06
    for f in reports:
        rdate = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d")
        cards.append(card(f.stem, f"reports/{f.stem}.html", rdate,
                          "📄", "report", "专题调研 · 工作汇报", delay))
        delay += 0.06

    total = len(cards)
    radar_n = sum(1 for a in ROOT_ARTIFACTS if a[4] == "radar" and exists(a[1]))
    report_n = sum(1 for a in ROOT_ARTIFACTS if a[4] == "report" and exists(a[1])) + len(reports)
    tool_n = sum(1 for a in ROOT_ARTIFACTS if a[4] == "tool" and exists(a[1]))
    last_date = max(
        [a[2] for a in ROOT_ARTIFACTS if a[4] != "lan" and exists(a[1])]
        + [datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d") for f in reports]
    )

    # 重点产品绩效面板(独立片段,update_nav.py 生成数据后由 publish 注入)
    products_html = ""
    panel = SITE / "product-panel" / "nav-panel.html"
    if panel.exists():
        products_html = fill_nav_tokens(panel.read_text(encoding="utf-8"))

    html = (html.replace("<!--CARDS-->", "\n".join(cards))
                .replace("<!--PRODUCTS-->", products_html)
                .replace("<!--BRIEFING-->", briefing_html)
                .replace("{{TOTAL}}", str(total))
                .replace("{{RADAR_COUNT}}", str(radar_n))
                .replace("{{REPORT_COUNT}}", str(report_n))
                .replace("{{KB_COUNT}}", str(kb_count))
                .replace("{{LAST_DATE}}", last_date))
    (SITE / "index.html").write_text(html, encoding="utf-8")
    print(f"[build] index.html ({total} 个成果卡片, 最近更新 {last_date})")


def main():
    args = [a for a in sys.argv[1:] if a != "--no-push"]
    push = "--no-push" not in sys.argv[1:]
    if args:  # 指定源文件 → 拷入 reports/
        src = Path(args[0]).resolve()
        if not src.exists():
            print(f"[error] 文件不存在: {src}")
            sys.exit(1)
        dst = REPORTS / src.name
        dst.write_text(src.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        print(f"[copy] {src.name} → reports/")
    reports = sorted(REPORTS.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not reports:
        print("[error] reports/ 下没有 md 文件")
        sys.exit(1)
    for f in reports:
        build_report(f)
    build_briefing_archive()
    build_index(reports)
    if push:
        subprocess.run(["git", "-C", str(SITE), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(SITE), "commit", "-m", "发布: 成果站更新"], check=True)
        subprocess.run(["git", "-C", str(SITE), "push"], check=True)
        print("[push] done")
    print("[ok] 全部完成")


if __name__ == "__main__":
    main()
