"""
everstead 成果站发布脚本

用法：
  py publish.py                    # 扫描 reports/*.md 全部重建
  py publish.py <某.md 路径>       # 把新成果拷入 reports/ 并重建
  py publish.py --no-push          # 只本地构建，不 commit/push

流程：md → html（内置轻量转换，无外部依赖）→ 重建 index.html 成果列表
      → git add/commit/push（GitHub Pages 自动发布）
"""
import re
import sys
import subprocess
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SITE = Path(__file__).parent
REPORTS = SITE / "reports"

# 站点根目录固定展品（不经过 md 转换，直接列出卡片）
# 第三项为内容生成日期（拷贝会刷新 mtime，故固定写死，避免卡片日期失真）
ROOT_ARTIFACTS = [
    ("税后收益率计算表", "yield-calc.html", "2026-09-07"),
    ("客户情报雷达 · 总览报告", "radar.html", "2026-09-03"),
    ("客户情报雷达 · 分级站点", "radar-site/index.html", "2026-09-03"),
    ("上市公司购买理财产品情况", "上市公司购买理财产品情况.html", "2026-08-31"),
]

PAGE_CSS = """
body{font-family:'Microsoft YaHei',sans-serif;max-width:860px;margin:0 auto;padding:24px 20px 60px;color:#1f2937;background:#fff;line-height:1.7}
h1{font-size:1.7em;border-bottom:2px solid #1a7f5c;padding-bottom:8px}
h2{font-size:1.3em;margin-top:1.6em;color:#14532d}
h3{font-size:1.1em;color:#166534}
table{border-collapse:collapse;width:100%;margin:12px 0}
th,td{border:1px solid #d1d5db;padding:6px 10px;font-size:14px;text-align:left}
th{background:#f0fdf4}
code{background:#f3f4f6;padding:1px 5px;border-radius:3px;font-size:13px}
blockquote{border-left:3px solid #1a7f5c;margin:10px 0;padding:4px 14px;color:#4b5563;background:#f9fafb}
a{color:#1a7f5c}
.back{display:inline-block;margin-bottom:16px;color:#6b7280;font-size:13px;text-decoration:none}
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


def build_index(reports: list) -> None:
    artifacts = "".join(
        f'<a class="card" href="{path}"><div class="t">{name}</div>'
        f'<div class="m">{date}</div></a>'
        for name, path, date in ROOT_ARTIFACTS if (SITE / path).exists())
    items = artifacts + "".join(
        f'<a class="card" href="reports/{f.stem}.html"><div class="t">{f.stem}</div>'
        f'<div class="m">{datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d")}</div></a>'
        for f in reports)
    html = (f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>everstead · 成果站</title><style>
body{{font-family:'Microsoft YaHei',sans-serif;background:#f6f8f7;margin:0;padding:48px 20px;color:#1f2937}}
.wrap{{max-width:900px;margin:0 auto}}
h1{{font-size:26px;color:#14532d;margin:0 0 4px}}
.sub{{color:#6b7280;font-size:13px;margin-bottom:28px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px}}
a.card{{display:block;background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:16px 18px;
text-decoration:none;color:#1f2937;transition:all .15s}}
a.card:hover{{border-color:#1a7f5c;box-shadow:0 3px 12px rgba(26,127,92,.12);transform:translateY(-2px)}}
.t{{font-weight:700;font-size:15px;line-height:1.5}}
.m{{font-size:12px;color:#9ca3af;margin-top:6px}}
</style></head><body><div class="wrap">
<h1>everstead · 成果站</h1>
<div class="sub">日常成果归档 · 持续更新</div>
<div class="grid">{items}</div>
</div></body></html>""")
    (SITE / "index.html").write_text(html, encoding="utf-8")
    print(f"[build] index.html ({len(reports)} 篇成果)")


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
