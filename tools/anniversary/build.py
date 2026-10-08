# -*- coding: utf-8 -*-
"""纪念日页面生成器

读 data.json → 算出倒数天数/周年/农历 → 注入 index.html 的三个占位符。
占位符: <!--COUNTDOWN--> <!--LIST--> <!--TIMELINE-->

用法:
    py build.py            # 重建 index.html
    py build.py --check    # 只打印核算结果, 不写文件

所有日期计算都在这里做, 页面不含 JS 计算逻辑 —— 打开即准, 不依赖浏览器时间。
"""
import json
import sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).parent
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WEEK = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def lunar_of(y: int, m: int, d: int) -> dict:
    """公历 → 农历文本(用 lunar-python; 缺库时降级为占位, 不让整页崩)"""
    try:
        from lunar_python import Solar
        l = Solar.fromYmd(y, m, d).getLunar()
        return {
            "gz": l.getYearInGanZhi(),
            "sx": l.getYearShengXiao(),
            "md": "%s月%s" % (l.getMonthInChinese(), l.getDayInChinese()),
            "full": "%s年%s%s" % (l.getYearInGanZhi(), l.getMonthInChinese(),
                                  l.getDayInChinese()),
        }
    except Exception as e:
        print("[warn] 农历换算失败 %d-%d-%d: %s" % (y, m, d, e))
        return {"gz": "—", "sx": "—", "md": "—", "full": "—"}


def lunar_to_solar(y: int, month: int, day: int) -> date:
    """农历 → 公历(lunar-python)。农历月序按常规月, 不含闰月。"""
    from lunar_python import Lunar
    s = Lunar.fromYmd(y, month, day).getSolar()
    return date(s.getYear(), s.getMonth(), s.getDay())


def occur_in(y: int, ev: dict) -> date:
    """某年的纪念日落在公历哪天(按该事件的历法规则)"""
    if ev.get("calendar") == "lunar":
        lm = ev["lunar"]
        return lunar_to_solar(y, lm["month"], lm["day"])
    y0, m0, d0 = (int(x) for x in ev["date"].split("-"))
    try:
        return date(y, m0, d0)
    except ValueError:      # 2/29 兜底
        return date(y, m0, 28)


def next_anniversary(ev: dict, today: date):
    """返回 (下次日期, 距今天数, 已满周年数, 下次是第几周年)

    两个"第几周年"含义不同, 必须分开:
      已满 —— 已经庆祝到第几周年(当天算已满)
      下次序号 —— 下次那天会是第几周年
    农历事件(七夕)每年公历日期不同, 必须按农历逐年换算。
    """
    y0 = int(ev["date"].split("-")[0])
    y = today.year
    while True:
        nxt = occur_in(y, ev)
        if nxt >= today:
            break
        y += 1
    y2 = today.year
    while True:
        if occur_in(y2, ev) <= today:
            break
        y2 -= 1
    return nxt, (nxt - today).days, y2 - y0, y - y0


def build_events(today: date) -> list:
    data = json.loads((HERE / "data.json").read_text(encoding="utf-8"))
    out = []
    for e in data["events"]:
        y, m, d = (int(x) for x in e["date"].split("-"))
        start = date(y, m, d)
        lu = lunar_of(y, m, d)
        base = {
            **e,
            "start": start,
            "passed_days": (today - start).days,
            "weekday": WEEK[start.weekday()],
            "lunar": lu,
            "is_milestone": bool(e.get("milestone")),
        }
        if base["is_milestone"]:
            # 一次性里程碑: 不循环, 无倒计时/周年
            base.update({"next": None, "left": None, "anniv": None,
                         "next_anniv": None, "is_today": False})
        else:
            nxt, left, passed, nxt_no = next_anniversary(e, today)
            base.update({"next": nxt, "left": left, "anniv": passed,
                         "next_anniv": nxt_no, "is_today": left == 0})
        out.append(base)
    # 有序纪念日按临近排; 里程碑永远垫底(它们没有"下一次")
    out.sort(key=lambda x: (x["left"] is None, x["left"] if x["left"] is not None else 0))
    return out


def render(events: list, today: date) -> dict:
    # 倒计时取"最近的循环纪念日"(里程碑没有下一次, 不参与)
    nxt = next(e for e in events if not e["is_milestone"])
    # "在一起"从【在一起纪念日】起算(2011-10-01), 不是求婚日
    pair = next((e for e in events if e["id"] == "together"), None)
    together = (today - pair["start"]).days if pair else 0
    pair_from = pair["start"].isoformat() if pair else "—"
    pair_years = together / 365.25

    if nxt["is_today"]:
        head_num, head_unit = "今天", ""
    else:
        head_num, head_unit = str(nxt["left"]), "天后"

    countdown = f'''<div class="next-card">
    <div class="next-head">
      <span class="next-label">下一个</span>
      <span class="next-title">{nxt["ico"]} {nxt["name"]}</span>
    </div>
    <div class="next-body">
      <div class="next-num">{head_num}</div>
      <div class="next-unit">{head_unit}</div>
      <div class="next-info">
        下次 <b>{nxt["next"].isoformat()}</b>（{WEEK[nxt["next"].weekday()]}）<br>
        届时<b>第 {nxt["next_anniv"]} 周年</b> · 已走过 <b>{nxt["passed_days"]:,}</b> 天<br>
        <span style="opacity:.72">在一起 <b>{together:,}</b> 天 · {pair_years:.1f} 年 · 自 {pair_from}</span>
      </div>
    </div>
  </div>'''

    list_html = []
    for e in events:
        # 农历事件标注历法, 免得看着"日期每年都在变"以为是 bug
        cal = ('<span class="tag" style="color:#c4b5fd;border-color:rgba(196,181,253,.4)">农历</span>'
               if e.get("calendar") == "lunar" else "")
        # 估算的日期明确标出来, 不冒充准确值
        est = ('<span class="tag" style="color:#fbbf24;border-color:rgba(251,191,36,.4)">估算</span>'
               if e.get("estimated") else "")

        if e["is_milestone"]:
            # 里程碑: 无倒计时, 右侧显示"已 N 天"
            list_html.append(f'''    <div class="item milestone">
      <div class="it-ico">{e["ico"]}</div>
      <div class="it-body">
        <div class="it-name">{e["name"]}</div>
        <div class="it-note"><span class="tag">{e["date"]}</span>
          {e["note"]} · 已 {e["passed_days"]:,} 天</div>
      </div>
      <div class="it-right">
        <div class="it-days">第 {e["passed_days"] + 1}<small>天</small></div>
        <div class="it-date">一次性里程碑</div>
      </div>
    </div>''')
            continue

        cls = "item today" if e["is_today"] else "item"
        soon = ' soon' if 0 < e["left"] <= 30 else ''
        days = "今天" if e["is_today"] else f'{e["left"]}<small>天</small>'
        list_html.append(f'''    <div class="{cls}">
      <div class="it-ico">{e["ico"]}</div>
      <div class="it-body">
        <div class="it-name">{e["name"]} {est}</div>
        <div class="it-note">{cal}<span class="tag">{e["date"]}</span>
          {e["note"]} · 已满 {e["anniv"]} 周年 · 已 {e["passed_days"]:,} 天</div>
      </div>
      <div class="it-right">
        <div class="it-days{soon}">{days}</div>
        <div class="it-date">{e["next"].isoformat()}</div>
      </div>
    </div>''')

    tl = []
    for e in sorted(events, key=lambda x: x["start"]):
        ms = '（里程碑）' if e["is_milestone"] else ''
        tl.append(f'''    <div class="tl-item">
      <div class="tl-date">{e["date"]}　{e["weekday"]}</div>
      <div class="tl-name">{e["ico"]} {e["name"]}{ms}</div>
      <div class="tl-note">{e["detail"]}　·　距今 {e["passed_days"]:,} 天</div>
    </div>''')

    return {
        "<!--COUNTDOWN-->": countdown,
        "<!--LIST-->": "\n".join(list_html),
        "<!--TIMELINE-->": "\n".join(tl),
        "_meta": {"together": together, "next": nxt},
    }


def main():
    check_only = "--check" in sys.argv
    today = date.today()
    events = build_events(today)

    print("=" * 66)
    print("纪念日核算 (基准 %s)" % today.isoformat())
    print("=" * 66)
    for e in events:
        if e["is_milestone"]:
            print("  %-12s %s  %-4s  已 %5d 天  [里程碑, 不循环]"
                  % (e["name"], e["date"], e["weekday"], e["passed_days"]))
        else:
            print("  %-12s %s  %-4s  已 %5d 天  已满 %d 周年  下次 %s (还有 %d 天, 届时第 %d 周年)"
                  % (e["name"], e["date"], e["weekday"], e["passed_days"],
                     e["anniv"], e["next"].isoformat(), e["left"], e["next_anniv"]))
        print("              农历 %s · %s" % (e["lunar"]["full"], e["note"]))
    pair = next((e for e in events if e["id"] == "together"), None)
    if pair:
        d0 = pair["start"]
        print()
        print("  在一起(自 %s): %d 天 ≈ %.1f 年"
              % (d0.isoformat(), (today - d0).days, (today - d0).days / 365.25))
    if any(e.get("estimated") for e in events):
        print("  ⚠ 含估算日期: %s"
              % ", ".join(e["name"] for e in events if e.get("estimated")))

    if check_only:
        return

    # 从 template.html 生成, 不是从 index.html ——
    # 否则第二次运行时就找不到占位符了(它们已被上次生成替换掉)。
    tpl = HERE / "template.html"
    if not tpl.exists():
        print("[error] 缺 template.html")
        return
    html = tpl.read_text(encoding="utf-8")
    r = render(events, today)
    for k in ("<!--COUNTDOWN-->", "<!--LIST-->", "<!--TIMELINE-->"):
        if k not in html:
            print("[error] 模板缺占位符: %s" % k)
            return
        html = html.replace(k, r[k])
    (HERE / "index.html").write_text(html, encoding="utf-8")
    print("\n[ok] index.html 已重建(模板 %s)" % tpl.name)


if __name__ == "__main__":
    main()
