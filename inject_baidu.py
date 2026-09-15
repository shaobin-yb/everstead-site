# -*- coding: utf-8 -*-
"""
百度统计埋点注入 · 2026-09-15 老板需求: 网站访客记录

把 hm.js 埋点注入到 everstead-site 所有公开 html 的 </head> 前(幂等):
- 密码门/私人专区页面跳过(私人页面 URL 不出现在第三方统计后台):
    与 inject_nav.py 的 SKIP 口径一致 + knowledge/iflyink-notes
- index-template.html 跳过(模板源, 由 publish.py 渲染进首页, 首页注入即可)

用法: py inject_baidu.py [--all]
默认增量(当日已注入则跳过); --all 强制全量重扫。
"""
import re
import sys
from datetime import date
from pathlib import Path

SITE = Path(__file__).parent
MARKS = SITE / ".baidu_marks"

# 百度统计埋点 ID(老板 2026-09-15 注册 tongji.baidu.com 提供)
HM_ID = "1d958a32a6588643ee6e67da344c7693"

SKIP = {
    "index-template.html",
    "private.html",
    "client-list.html",
    "client-list-lite.html",
    "tools/counterparty/",
    "tools/unassigned/",
    "tools/scattered-private/",
    "tools/token-usage/",
    "tools/stats/",
    "knowledge/iflyink-notes/",
    "tools/meal/",
    "tools/nursery/",
    "tools/nursery-parents/",
    "tools/family-links/",
    "tools/baby-name-board/",
    "tools/naming/",
    "tools/yuebing-travels/",
    "tools/work-report/",
}


def snippet() -> str:
    return (
        '<script>\n'
        'var _hmt=_hmt||[];\n'
        '(function(){var hm=document.createElement("script");'
        f'hm.src="https://hm.baidu.com/hm.js?{HM_ID}";'
        'var s=document.getElementsByTagName("script")[0];'
        's.parentNode.insertBefore(hm,s);})();\n'
        '</script>'
    )


def all_html() -> list:
    out = []
    for p in SITE.rglob("*.html"):
        rel = p.relative_to(SITE).as_posix().lower()
        if any(rel == s or rel.startswith(s) for s in SKIP):
            continue
        if rel.startswith("radar-site/"):
            continue
        out.append(p)
    return out


def main() -> None:
    if HM_ID.startswith("__"):
        print("[error] 百度统计 ID 未配置, 请老板注册 tongji.baidu.com 后填入 HM_ID")
        sys.exit(1)
    force = "--all" in sys.argv[1:]
    today = date.today().isoformat()
    done_today = (MARKS / f"inject_{today}.txt").exists()
    if done_today and not force:
        print("[skip] 今日已注入过, 如需强制重扫加 --all")
        return
    injected = 0
    for p in all_html():
        text = p.read_text(encoding="utf-8", errors="replace")
        if "hm.baidu.com" in text:
            continue  # 已注入
        if "</head>" not in text:
            print(f"[warn] 无 </head>, 跳过: {p.relative_to(SITE)}")
            continue
        p.write_text(text.replace("</head>", snippet() + "\n</head>", 1),
                     encoding="utf-8")
        injected += 1
    MARKS.mkdir(exist_ok=True)
    (MARKS / f"inject_{today}.txt").write_text(f"injected {injected}", encoding="utf-8")
    print(f"[ok] 注入 {injected} 个页面, 标记 {today}")


if __name__ == "__main__":
    main()
