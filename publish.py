"""
稳稳回报展示平台发布脚本

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

# AI 应用看板的统计口径(2026-09-22 老板拍板)
MIN_PER_ANN = 3          # 每条公告等效人工 3 分钟
WORKDAY_HOURS = 8        # 折算工作日


def ai_metrics() -> dict:
    """AI 应用看板的真实数据。全部从文件/数据库读取, 不硬编码。
    读不到就返回 0, 页面显示 0 而不是编造的数字。"""
    import sqlite3
    out = {"ann": 0, "comp": 0, "hours": 0, "days": 0, "tasks": 0,
           "range": "—"}

    # ① 客户情报雷达: 公告数 / 覆盖公司 / 时间区间
    db = Path(__file__).parent.parent / "client_radar" / "announcements.db"
    if db.exists():
        try:
            con = sqlite3.connect(str(db))
            out["ann"] = con.execute("select count(*) from announcements").fetchone()[0]
            out["comp"] = con.execute(
                "select count(distinct sec_code) from announcements").fetchone()[0]
            d0, d1 = con.execute(
                "select min(pub_date), max(pub_date) from announcements").fetchone()
            if d0 and d1:
                out["range"] = "%s ~ %s" % (d0, d1)
            con.close()
        except Exception as e:
            print("[warn] 读雷达库失败: %s" % e)

    # ② 等效工时
    mins = out["ann"] * MIN_PER_ANN
    out["hours"] = int(round(mins / 60.0))
    out["days"] = int(round(out["hours"] / float(WORKDAY_HOURS)))

    # ③ 工作类定时任务数(排除家庭类)
    HOME_TASKS = {"weekly-baby-prep"}
    tdir = Path.home() / ".claude" / "scheduled-tasks"
    if tdir.exists():
        out["tasks"] = sum(1 for d in tdir.iterdir()
                           if d.is_dir() and d.name not in HOME_TASKS
                           and (d / "SKILL.md").exists())
    return out



# 站点根目录固定展品（不经过 md 转换，直接列出卡片）
# 每项: (名称, 路径, 日期, 图标, 类型, 描述, 分类)
# 类型: radar=雷达/站点  report=专题报告  tool=数据工具  lan=内网  vault=密码专区
# 分类: 首页展厅分组用(2026-09-22 第二轮, 按老板最新分类)
# 日期写死（拷贝会刷新 mtime，避免卡片日期失真）
ROOT_ARTIFACTS = [
    # ---- 报告 ----
    ("红利质量_产品一页通", "product-onepagers/红利质量_产品一页通.html", "2026-09-15", "📕", "report",
     "净值 + 全收益指数对照 · 每日更新", "报告"),
    ("价值1号_产品一页通", "product-onepagers/价值1号_产品一页通.html", "2026-09-15", "📗", "report",
     "净值 + 全收益指数对照 · 每日更新", "报告"),
    ("红利价值量化_产品一页通", "product-onepagers/红利价值量化_产品一页通.html", "2026-09-15", "📘", "report",
     "国新 × 中邮 · 要素型", "报告"),
    ("深度价值量化选股_产品一页通", "product-onepagers/深度价值量化选股_产品一页通.html", "2026-09-15", "📙", "report",
     "国新 × 中邮 · 要素型", "报告"),
    ("产品持仓池", "holdings.html", "2026-09-10", "📦", "report",
     "中邮价值1号(TOP10权重50.57%) + 红利质量(27.17%) 重仓股快照 · 与红利/深度观察池重叠标记", "报告"),
    ("上市公司购买理财产品情况", "上市公司购买理财产品情况.html", "2026-09-07", "📊", "report",
     "上市公司闲置资金理财公告全景统计", "报告"),
    ("资产负债管理办法概念梳理", "保险公司资产负债管理办法-概念梳理.html", "2026-09-09", "📖", "report",
     "新规学习页 · 12张概念卡 + 人身险4项/财险3项监管指标扫盲 + IFRS9/17 + 产品化映射", "报告"),

    # ---- 知识库 ----
    ("保险资管风险责任人知识库", "kb.html", "2026-09-07", "🛡️", "kb",
     "5 大投资管理能力 · 40+ 机构风险责任人档案 · 搜索/折叠/从业经历", "知识库"),
    # 2026-09-22: 老板分类工具里去掉了"成果站知识库"这层包装(4 个主题直接挂知识库下),
    # 但这页是 31 条知识库条目的唯一入口, 删了卡会让条目在站上不可达, 故保留
    ("成果站知识库", "knowledge/index.html", "2026-09-07", "📚", "knowledge",
     "PPT/PDF 翻页预览 + 原文件下载 · 4 主题 31 条", "知识库"),

    # ---- 工具 ----
    ("2026年贷款利率自律底线", "lending-rate-floor.html", "2026-09-10", "💹", "tool",
     "51档标准期限(6个月-50年)全档位速查 + 利率曲线 + 非标期限向上靠档计算器", "工具"),
    ("税后收益率计算表", "yield-calc.html", "2026-09-07", "🧮", "tool",
     "资管产品税后收益率一键计算", "工具"),

    # ---- 驾驶舱 ----
    ("客户情报雷达", "radar.html", "2026-09-11", "📡", "radar",
     "巨潮每日公告抓取 + 受托方解析 + iFind 打分{companies}", "驾驶舱"),
    ("资管投研驾驶舱", "cockpit.html", "2026-09-09", "🖥️", "cockpit",
     "每日盘后自动更新 · 市场总览/温度/产品净值/红利·深度价值关注池异动/龙虎榜/同业新发", "驾驶舱"),
    ("因子工厂快照", "factors.html", "2026-09-09", "⚗️", "cockpit",
     "关注池 86 只 · 股息率TTM/动量/波动率/成交额 五因子本地计算", "驾驶舱"),
    ("因子 IC 回测", "factor-ic.html", "2026-09-10", "🧪", "cockpit",
     "86只周频Rank IC · 股息率TTM最强(t=5.7) · 低波异象显著 · 动量无效", "驾驶舱"),
    # 收盘点评卡片日期动态取 latest.md 的日期(见 load_briefing_info)
    ("每日收盘点评", "market-briefings/index.html", "", "📰", "briefing",
     "每个交易日收盘后更新 · 历史逐日归档", "驾驶舱"),

    # ---- 内网 ----
    # 注: 老板的新结构里 对手库/客户名单/未分配池 同时出现在「工作区」下,
    # 站上不重复出卡, 按主归属放在「内网」
    ("直接交易对手库", "tools/counterparty/counterparty.html", "2026-09-11", "🏦", "lan",
     "在库授信对手 468 家(授信总额 1.95 万亿) + 历史出库 58 家 · 评级/额度/省份/分析师筛选 · 🔒 密码访问", "内网"),
    ("金融客户名单·精选版", "client-list-lite.html", "2026-09-10", "🏛️", "lan",
     "980 家市级及以上机构 · 8类Tab一眼抓重点 · 剔除联合社/信用社/县级农商行 · 🔒 密码访问", "内网"),
    ("CRM 未分配客户池", "tools/unassigned/unassigned.html", "2026-09-14", "🎯", "lan",
     "356 家未分配团队客户 · 搜索/类型/地域筛选 + 条形图联动 · 导出CSV · 🔒 密码访问", "内网"),

    # ---- 密码访问 ----
    ("私人专区", "private.html", "2026-09-15", "🔐", "vault",
     "家庭与私人资料 · 个人密码解锁", "密码访问"),

    # ---- 工作区 ----
    ("工作区", "work.html", "2026-09-09", "💼", "vault",
     "业务资料与工作材料 · 工作密码解锁", "工作区"),
    ("CRM 客户关系管理系统", "http://192.168.100.148:3000", "2026-09-07", "👥", "lan",
     "客户/商机/拜访纪要 · 账号 wangshaobin · 🔒 仅公司内网可访问", "工作区"),
    ("铁蛋近期工作总结", "reports/铁蛋近期工作总结.html", "2026-09-08", "📄", "report",
     "专题调研 · 工作汇报", "工作区"),
]

# 底部友情链接式展示：本地工具（launch:// 协议，仅本机装了 handler 才唤起）
# 每项: (名称, 协议地址, 图标, 描述)
LOCAL_TOOLS = [
    ("小米 MiMo 玩票站", "launch://mimo", "🤖", "多模态 AI：API 聊天/看图 + 本地 7B"),
    ("客户拜访台账", "launch://ledger", "🗂️", "拜访记录 / 客户画像 / 跟进提醒"),
    ("Codex 铁锤", "launch://codex", "🔨", "OpenAI Codex CLI 编程助手"),
    ("DeepSeek Harness", "launch://harness", "🐋", "DeepSeek 编程助手 CLI"),
    ("Obsidian 个人操作系统", "launch://obsidian", "📓", "笔记 / 日记 / 知识库 vault"),
    ("SDKDNS", "launch://sdkdns", "🛰️", "网络代理客户端"),
    ("飞书", "launch://feishu", "💬", "即时通讯 / 办公协作"),
    ("铁蛋控制面板", "launch://dashboard", "🎛️", "启动后访问 localhost:18930"),
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
            f'<a class="back" href="../index.html">← 稳稳回报展示平台</a>'
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
                f'<a class="back" href="../index.html">← 稳稳回报展示平台</a>'
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
            f'<a class="back" href="../index.html">← 稳稳回报展示平台</a>'
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


def fill_board_tokens(panel: str) -> str:
    """board-panel.html 的 __BP_*__ token → board-panel.json 实时值(构建期注入)。

    与产品面板同款策略: 静态首屏即真实数据, 无 JS / fetch 失败也不空白。
    heatmap 元素多(30×30), 静态只注入占位提示, 由 JS 渲染实际矩阵。
    """
    try:
        d = json.loads((SITE / "board-panel.json").read_text(encoding="utf-8"))
    except Exception:
        d = {}

    def rows(items):
        out = []
        for i, r in enumerate(items or [], 1):
            cls = "bp-pos" if r["pct"] >= 0 else "bp-neg"
            out.append(f'<div class="bp-row"><span class="bp-rank">{i}</span>'
                       f'<span class="bp-name">{r["name"]}</span>'
                       f'<span class="bp-turn">{r["turnover_yi"]:.0f}亿</span>'
                       f'<span class="bp-pct {cls}">{r["pct"]:+.2f}%</span></div>')
        return "".join(out)

    def bars(items):
        if not items:
            return ""
        mx = max(abs(t["cum_pct"]) for t in items) or 1
        out = []
        for t in items:
            cls = "pos" if t["cum_pct"] >= 0 else "neg"
            w = max(2, abs(t["cum_pct"]) / mx * 50)
            out.append(f'<div class="bp-bar-row"><span class="bp-bar-name">{t["name"]}</span>'
                       f'<span class="bp-bar-track"><span class="bp-bar-mid"></span>'
                       f'<span class="bp-bar-fill {cls}" style="width:{w:.1f}%"></span></span>'
                       f'<span class="bp-bar-val {cls}">{t["cum_pct"]:+.2f}%</span></div>')
        return "".join(out)

    latest = d.get("latest") or {}
    tokens = {
        "__BP_UPDATED__": d.get("updated", ""),
        "__BP_DAY__": latest.get("date", ""),
        "__BP_SINCE__": d.get("since", ""),
        "__BP_DAYS__": str(d.get("days", "")),
        "__BP_TOP__": rows(latest.get("top")),
        "__BP_BOTTOM__": rows(latest.get("bottom")),
        "__BP_TREND__": bars(d.get("trend")),
        "__BP_HEAT__": '<div style="color:var(--muted);font-size:12px">正在加载轮动矩阵…</div>',
        "__BP_HEATMAP_BOARDS__": json.dumps(d.get("heatmap_boards", []), ensure_ascii=False),
    }
    for k, v in tokens.items():
        panel = panel.replace(k, v or "—")
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

    # 卡片右上角标签: 按类型显示(与筛选行显示名一致)
    TYPE_TAG = {'radar': '雷达', 'tool': '工具', 'report': '报告', 'kb': '知识库',
                'knowledge': '知识库', 'briefing': '点评', 'cockpit': '驾驶舱',
                'lan': '内网', 'external': '外链', 'vault': '密码专区',
                'local': '本地'}

    def card(name, href, date, icon, kind, desc, delay, no, external=False, cat=""):
        ext = ' target="_blank" rel="noopener"' if external else ''
        # lan(仅内网)卡片保留真实内网地址, 点击新标签页打开
        # (2026-09-14 修复: 此前 href 强制置 # 导致 CRM 卡片点击无跳转)
        if kind == "lan":
            ext = ' target="_blank" rel="noopener"'
        tag = TYPE_TAG.get(kind, kind.upper())
        # data-cat: 首页展厅分组用(2026-09-22 起按分类工具的结果分组, 不再用 data-type 推导)
        catattr = f' data-cat="{cat}"' if cat else ''
        return (f'<a class="card" data-type="{kind}"{catattr} data-no="{no}" style="animation-delay:{delay:.2f}s" '
                f'href="{href}"{ext}>'
                f'<span class="corner c1"></span><span class="corner c2"></span>'
                f'<span class="corner c3"></span><span class="corner c4"></span>'
                f'<div class="card-top"><div class="card-ico">{icon}</div>'
                f'<div class="card-tag">{tag}</div></div>'
                f'<div class="t">{name}</div>'
                f'<div class="m">{desc}</div>'
                f'<div class="d"><span class="card-no">{no:02d}</span><span>{date}</span></div>'
                f'<span class="arrow">→</span></a>')

    def local_link(name, href, icon, desc):
        """底部本地工具：launch:// 协议，点击由本机 launch_handler 接管。"""
        return (f'<a class="lt-item" href="{href}" title="{desc}">'
                f'<span class="lt-ico">{icon}</span>'
                f'<span class="lt-body"><span class="lt-n">{name}</span>'
                f'<span class="lt-d">{desc}</span></span>'
                f'<span class="lt-arrow">→</span></a>')

    def exists(path: str) -> bool:
        """外链(局域网 CRM 等)直接视为存在; 本地路径查文件。"""
        return path.startswith(("http://", "https://")) or (SITE / path).exists()

    def radar_company_count() -> int:
        """雷达分级站点的公司页数(卡片描述动态取值, 避免写死后过期)。"""
        d = SITE / "radar-site" / "companies"
        return len(list(d.glob("*.html"))) if d.is_dir() else 0

    cards, delay = [], 0.35
    for name, path, date, icon, kind, desc, cat in ROOT_ARTIFACTS:
        # lan 卡片(仅内网)恒展示
        if kind == "lan" or exists(path):
            if kind == "radar":
                # 2026-09-20: 原写死 "433 家", 扩到近一年后已过期, 改为按实际产物取数
                n = radar_company_count()
                desc = desc.replace("{companies}",
                                    f" · 页内直达 {n} 家公司分级站点" if n else "")
            if kind == "knowledge" and kb_date:
                date = kb_date  # 知识库卡片日期取最新条目日期
            if kind == "briefing":
                date = briefing_date(latest_briefing_text) or datetime.fromtimestamp(
                    (SITE / path).stat().st_mtime).strftime("%Y-%m-%d")
            cards.append(card(name, path, date, icon, kind, desc, delay, len(cards) + 1,
                              external=path.startswith(("http://", "https://")), cat=cat))
            delay += 0.06
    # 2026-09-22: reports/ 目录下的报告已并入 ROOT_ARTIFACTS(铁蛋近期工作总结),
    # 不再扫描目录, 避免同一份报告重复出卡
    EXCLUDED_REPORTS = set()

    # 底部本地工具区(launch:// 协议, 友情链接式)
    local_html = "".join(local_link(n, h, i, d) for n, h, i, d in LOCAL_TOOLS)

    total = len(cards)
    # 2026-09-22: 统计口径改按分类工具的结果(cat 字段)
    def cat_n(cat, kinds=None):
        return sum(1 for a in ROOT_ARTIFACTS
                   if a[6] == cat and exists(a[1]) and (kinds is None or a[4] in kinds))
    report_n = cat_n("报告")
    radar_n  = cat_n("驾驶舱", ("radar",))
    tool_n   = cat_n("工具") + cat_n("驾驶舱", ("cockpit",))  # 与筛选行"工具"口径一致
    last_date = max(
        [a[2] for a in ROOT_ARTIFACTS if a[4] != "lan" and a[2] and exists(a[1])]
    )

    # 行业板块跟踪面板(独立片段, build_board_panel.py 生成数据后由 publish 注入)
    boards_html = ""
    board_panel = SITE / "board-panel.html"
    if board_panel.exists():
        boards_html = fill_board_tokens(board_panel.read_text(encoding="utf-8"))

    # 重点产品绩效面板(独立片段,update_nav.py 生成数据后由 publish 注入)
    products_html = ""
    panel = SITE / "product-panel" / "nav-panel.html"
    if panel.exists():
        products_html = fill_nav_tokens(panel.read_text(encoding="utf-8"))

    # AI 应用看板数据(2026-09-22)
    ai = ai_metrics()

    html = (html.replace("<!--CARDS-->", "\n".join(cards))
                .replace("<!--BOARDS-->", boards_html)
                .replace("<!--PRODUCTS-->", products_html)
                .replace("<!--BRIEFING-->", briefing_html)
                .replace("<!--LOCALTOOLS-->", local_html)
                .replace("{{TOTAL}}", str(total))
                .replace("{{RADAR_COUNT}}", str(radar_n))
                .replace("{{REPORT_COUNT}}", str(report_n))
                .replace("{{KB_COUNT}}", str(kb_count))
                .replace("{{TOOL_COUNT}}", str(tool_n))
                .replace("{{LAST_DATE}}", last_date)
                # 注意: 这里注入纯数字, 千分位由页面 JS 渲染时加 ——
                # 若在这里就写成 "13,088", 前端 parseInt 会截成 13
                .replace("{{AI_ANN}}", str(ai['ann']))
                .replace("{{AI_COMP}}", str(ai['comp']))
                .replace("{{AI_HOURS}}", str(ai['hours']))
                .replace("{{AI_DAYS}}", str(ai['days']))
                .replace("{{AI_TASKS}}", str(ai["tasks"]))
                .replace("{{AI_RANGE}}", ai["range"]))
    (SITE / "index.html").write_text(html, encoding="utf-8")
    print(f"[build] index.html ({total} 个成果卡片, 最近更新 {last_date})")
    print(f"[build] AI 看板: 公告 {ai['ann']} / 公司 {ai['comp']} / "
          f"等效 {ai['hours']}h / 任务 {ai['tasks']}")


def inject_nav() -> None:
    """全站悬浮导航注入(2026-09-12): 调用 inject_nav.py, 增量幂等。"""
    subprocess.run([sys.executable, str(SITE / "inject_nav.py")], check=True)


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
    # 全站搜索索引(2026-09-14)。函数级导入: build_search_index 反向 import publish
    # 复用常量, 模块级互引会循环导入。
    import build_search_index
    build_search_index.main()
    inject_nav()  # 全站悬浮导航(返回上一步+返回首页), 增量幂等
    if push:
        subprocess.run(["git", "-C", str(SITE), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(SITE), "commit", "-m", "发布: 稳稳回报更新"], check=True)
        subprocess.run(["git", "-C", str(SITE), "push"], check=True)
        print("[push] done")
    print("[ok] 全部完成")


if __name__ == "__main__":
    main()
