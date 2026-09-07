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

# 站点根目录固定展品（不经过 md 转换，直接列出卡片）
# 每项: (名称, 路径, 日期, 图标, 类型, 描述)
# 类型: radar=雷达/站点  report=专题报告  tool=数据工具
# 日期写死（拷贝会刷新 mtime，避免卡片日期失真）
ROOT_ARTIFACTS = [
    ("税后收益率计算表", "yield-calc.html", "2026-09-07", "🧮", "tool",
     "资管产品税后收益率一键计算"),
    ("客户情报雷达 · 总览报告", "radar.html", "2026-09-03", "📡", "radar",
     "巨潮每日公告抓取 + 受托方解析 + iFind 打分，客户线索早报"),
    ("客户情报雷达 · 分级站点", "radar-site/index.html", "2026-09-03", "🗺️", "radar",
     "按省/公司分级的公告雷达站点，381 家公司明细"),
    ("上市公司购买理财产品情况", "上市公司购买理财产品情况.html", "2026-08-31", "📊", "report",
     "上市公司闲置资金理财公告全景统计"),
    ("知识库", "knowledge/index.html", "2026-09-07", "📚", "knowledge",
     "PPT/PDF 翻页预览 + 原文件下载，按主题归档"),
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
    """读知识库 manifest: 返回(条目数, 最新日期); 不存在返回 (0, "")。"""
    kb_manifest = SITE / "knowledge" / "manifest.json"
    if not kb_manifest.exists():
        return 0, ""
    try:
        m = json.loads(kb_manifest.read_text(encoding="utf-8"))
        items = m.get("items", [])
        latest = max((it.get("date", "") for it in items), default="")
        return len(items), latest
    except Exception:
        return 0, ""


def build_index(reports: list) -> None:
    """从 index-template.html 科技感模板渲染首页(注入卡片 + 统计)。"""
    tpl = SITE / "index-template.html"
    if not tpl.exists():
        # 模板缺失时仍保证可发布: 复制现有 index.html 作为模板(纯卡片增量的场景)
        print("[warn] index-template.html 不存在, 跳过首页重建")
        return
    html = tpl.read_text(encoding="utf-8")
    kb_count, kb_date = load_kb_stats()

    def card(name, href, date, icon, kind, desc, delay):
        return (f'<a class="card" data-type="{kind}" style="animation-delay:{delay:.2f}s" '
                f'href="{href}">'
                f'<span class="corner c1"></span><span class="corner c2"></span>'
                f'<span class="corner c3"></span><span class="corner c4"></span>'
                f'<div class="card-top"><div class="card-ico">{icon}</div>'
                f'<div class="card-tag">{kind.upper()}</div></div>'
                f'<div class="t">{name}</div>'
                f'<div class="m">{desc}</div>'
                f'<div class="d">{date}</div>'
                f'<span class="arrow">→</span></a>')

    cards, delay = [], 0.35
    for name, path, date, icon, kind, desc in ROOT_ARTIFACTS:
        if (SITE / path).exists():
            if kind == "knowledge" and kb_date:
                date = kb_date  # 知识库卡片日期取最新条目日期
            cards.append(card(name, path, date, icon, kind, desc, delay))
            delay += 0.06
    for f in reports:
        rdate = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d")
        cards.append(card(f.stem, f"reports/{f.stem}.html", rdate,
                          "📄", "report", "专题调研 · 工作汇报", delay))
        delay += 0.06

    total = len(cards)
    radar_n = sum(1 for a in ROOT_ARTIFACTS if a[4] == "radar" and (SITE / a[1]).exists())
    report_n = sum(1 for a in ROOT_ARTIFACTS if a[4] == "report" and (SITE / a[1]).exists()) + len(reports)
    tool_n = sum(1 for a in ROOT_ARTIFACTS if a[4] == "tool" and (SITE / a[1]).exists())
    last_date = max(
        [a[2] for a in ROOT_ARTIFACTS if (SITE / a[1]).exists()]
        + [datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d") for f in reports]
    )

    html = (html.replace("<!--CARDS-->", "\n".join(cards))
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
    build_index(reports)
    if push:
        subprocess.run(["git", "-C", str(SITE), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(SITE), "commit", "-m", "发布: 成果站更新"], check=True)
        subprocess.run(["git", "-C", str(SITE), "push"], check=True)
        print("[push] done")
    print("[ok] 全部完成")


if __name__ == "__main__":
    main()
