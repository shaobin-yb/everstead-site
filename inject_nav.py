# -*- coding: utf-8 -*-
"""
全站悬浮导航注入 · 2026-09-12 老板需求: 每个页面都能返回上一步 + 返回首页

把 nav-fab.js 自动注入到 everstead-site 所有 html 的 </body> 前(幂等):
- 首页 index.html 跳过(已在首页, FAB 自身也有保护)
- 带密码门的私有页跳过(自动加导航会绕过密码门, 变成"未解锁先露底"):
    client-list.html / client-list-lite.html / private.html / tools/counterparty/counterparty.html
- radar-site/ 的站点页有站内返回导航, 同样跳过(只给顶层 radar.html 注入)
- index-template.html 是模板源(注入后 publish.py 渲染会自动带进首页→被首页保护跳过, 注入与否无害, 跳过保持模板干净)

用法: py inject_nav.py [--all]
默认增量(跳过当日已注入); --all 强制全量重扫(配合 --no-push 重建可测效果)。
"""
import sys
from datetime import date
from pathlib import Path

SITE = Path(__file__).parent
FAB = SITE / "nav-fab.js"
MARKS = SITE / ".nav_marks"

# 路径统一用正斜杠相对 SITE 的小写形式
SKIP = {
    "index.html",
    "index-template.html",
    "client-list.html",
    "client-list-lite.html",
    "private.html",
    "tools/counterparty/counterparty.html",
}


def all_html() -> list:
    out = []
    for p in SITE.rglob("*.html"):
        rel = p.relative_to(SITE).as_posix().lower()
        if rel in SKIP:
            continue
        if rel.startswith("radar-site/"):
            continue
        out.append(p)
    return out


def main() -> None:
    force = "--all" in sys.argv[1:]
    today = date.today().isoformat()
    fab = FAB.read_text(encoding="utf-8")
    tag = '<script src="nav-fab.js"></script>'
    done_today = (MARKS / f"inject_{today}.txt").exists()

    if done_today and not force:
        print("[skip] 今日已注入过, 如需强制重扫加 --all")
        return

    # 深度 → 脚本相对路径前缀
    rel_cache = {}
    injected = 0

    for p in all_html():
        text = p.read_text(encoding="utf-8", errors="replace")
        if tag in text:  # 已注入, 跳过
            continue
        if "</body>" not in text:
            print(f"[warn] 无 </body>, 跳过: {p.relative_to(SITE)}")
            continue
        depth = len(p.relative_to(SITE).parts) - 1
        prefix = rel_cache.setdefault(depth, "../" * depth)
        line = '<script src="' + prefix + 'nav-fab.js"></script>\n</body>'
        p.write_text(text.replace("</body>", line, 1), encoding="utf-8")
        injected += 1

    MARKS.mkdir(exist_ok=True)
    (MARKS / f"inject_{today}.txt").write_text(f"injected {injected}", encoding="utf-8")
    print(f"[ok] 注入 {injected} 个页面, 标记 {today}")


if __name__ == "__main__":
    main()
