# -*- coding: utf-8 -*-
"""
重点产品净值管道 update_nav.py
──────────────────────────────
数据源:
  1. 产品净值 — 同花顺 iFinD 客户端「保险资管-深度资料」页 (UIA 抓取)
     代码: ZY0049.BZJ (中邮资管价值策略1号)
           ZY0053.BZJ (中邮资管红利质量量化选股策略)
  2. 基准     — 沪深300 日收盘 (fuyao HTTP API, 000300.SH)
  3. 全收益指数 — 一页通「成立以来收益对照」三条基准线 (2026-09-15 新增):
     沪深300全收益 H00300.CSI / 科创50全收益 000688CNY01.SH (iFinD 远程 MCP HTTP)
     创业板指全收益 399606.SZ (fuyao, 简称"创业板R")

流程: 抓两只产品深度资料页表格(最近10个交易日净值+日涨跌%)
      → 抓沪深300 同窗口收盘价 + 三条全收益指数
      → 追加进 nav-history.json (按日去重)
      → 自算指标 → 写 nav-data.json (前端渲染用)

踩坑(2026-09-15): iFinD index_data 单次返回上限 100 行且含周末填充行
(收盘价与前一日相同), 必须 (a) 按 ≤55 自然日分块抓取, (b) 按 fuyao 交易日历
过滤, 否则波动率被稀释约 1-3 个百分点。成立以来收益以成立日面值 1.0000 为基准
(非序列首值), 与一页通 PDF 口径一致 —— 已在 2026-08-19 口径上逐位对齐验证。

用法:
  py update_nav.py            # 常规运行
  py update_nav.py --dry-run  # 只抓不写库(调试)
  py update_nav.py --no-push  # 不 git push

依赖: py -V:Astral/CPython3.12.14 (含 pywinauto + requests)
      同花顺 iFinD 客户端须在运行且已登录
"""
import ctypes
import json
import sys
import time
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 空闲检测: 老板 N 分钟没碰键鼠才允许 UI 抓取(不抢鼠标的自动化之星方案)
IDLE_MIN_SECONDS = 10 * 60
IDLE_MIN_SECONDS = int(Path(__file__).parent.joinpath("idle_seconds.txt").read_text().strip()) \
    if Path(__file__).parent.joinpath("idle_seconds.txt").exists() else IDLE_MIN_SECONDS


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def system_idle_seconds() -> float:
    lii = _LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(_LASTINPUTINFO)
    if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
        return max(0, (ctypes.windll.kernel32.GetTickCount() - lii.dwTime) / 1000.0)
    return 0.0

BASE = Path(__file__).parent
HISTORY = BASE / "nav-history.json"
DATA = BASE / "nav-data.json"
SITE = BASE.parent  # everstead-site

PRODUCTS = {
    "ZY0049": {"name": "中邮资管价值策略1号", "code": "ZY0049.BZJ",
               "wind": "ZY0049.OF", "inception": "2026-06-10"},
    "ZY0053": {"name": "中邮资管红利质量量化选股策略", "code": "ZY0053.BZJ",
               "wind": "ZY0053.OF", "inception": "2026-07-14"},
}

# 全收益指数(2026-09-15 新增): 一页通「成立以来收益对照」三条基准线。
# ifind 源走远程 MCP HTTP(H00300.CSI / 000688CNY01.SH 为沪深/科创全收益官方代码,
# fuyao 目录里无行情); 创业板指全收益在 fuyao 有行情(399606.SZ, 简称"创业板R")。
INDEXES = {
    "hs300_tr": {"name": "沪深300全收益", "code": "H00300.CSI", "src": "ifind"},
    "cyb_tr": {"name": "创业板指全收益", "code": "399606.SZ", "src": "fuyao"},
    "kc50_tr": {"name": "科创50全收益", "code": "000688CNY01.SH", "src": "ifind"},
}

IFIND_INDEX_URL = "https://api-mcp.51ifind.com:8643/ds-mcp-servers/hexin-ifind-ds-index-mcp"


def _claude_cfg():
    return json.loads(open(Path.home() / ".claude.json", encoding="utf-8").read())


def _fuyao_cfg(server):
    """fuyao MCP 配置(url + key)从 ~/.claude.json 读。注意 url 路径与 server 名不同名。"""
    srv = _claude_cfg().get("mcpServers", {}).get(server) or {}
    return srv.get("url", ""), (srv.get("headers") or {}).get("X-api-key", "")


def _fuyao_key(server="fuyao-a-share-index"):
    return _fuyao_cfg(server)[1]


def fetch_hs300(end, days_back=120):
    """fuyao index 历史K线 → [{date, close}] (升序)。"""
    import requests
    end_ms = int(datetime.strptime(end, "%Y-%m-%d").timestamp() * 1000)
    start_ms = end_ms - days_back * 86400 * 1000 * 2  # 自然日近似,多取一倍
    r = requests.post(
        "https://fuyao.aicubes.cn/mcp/a-share-index",
        json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {
                "name": "get_a_share_index_prices_historical",
                "arguments": {
                    "thscode": "000300.SH", "interval": "1d",
                    "start": start_ms, "end": end_ms,
                },
            },
        },
        headers={"Content-Type": "application/json", "X-api-key": _fuyao_key()},
        timeout=60,
    )
    data = r.json()
    content = data.get("result", {}).get("content", [])
    if not content:
        raise RuntimeError("fuyao 返回异常: %s" % str(data)[:200])
    inner = json.loads(content[0]["text"])
    # fuyao 实际结构: data.item[] , 行字段 date_ms / close_price
    rows = inner.get("data", {}).get("item", [])
    out = []
    for row in rows:
        if isinstance(row, dict):
            ts = row.get("date_ms")
            close = row.get("close_price")
            if ts and close:
                d = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
                out.append({"date": d, "close": float(close)})
    out.sort(key=lambda x: x["date"])
    return out


def _fuyao_call(server, name, arguments, timeout=90):
    """fuyao MCP HTTP 调用 → 内层 data 字段(JSON)"""
    import requests
    url, key = _fuyao_cfg(server)
    if not url:
        raise RuntimeError("~/.claude.json 缺 %s 配置" % server)
    r = requests.post(
        url,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": name, "arguments": arguments}},
        headers={"Content-Type": "application/json", "X-api-key": key},
        timeout=timeout,
    )
    content = r.json().get("result", {}).get("content", [])
    if not content:
        raise RuntimeError("fuyao 返回异常: %s" % r.text[:200])
    return json.loads(content[0]["text"])


def fetch_trading_days():
    """fuyao 近一年交易日集合(YYYY-MM-DD)。iFinD 日线含周末填充行, 必须按此过滤。"""
    inner = _fuyao_call("fuyao-a-share", "get_a_share_calendar_trading_days", {})
    out = set()
    for row in inner.get("data", {}).get("item", []):
        d8 = row.get("date", "")
        if len(d8) == 8:
            out.add("%s-%s-%s" % (d8[:4], d8[4:6], d8[6:]))
    return out


def fetch_fuyao_index(thscode, end, days_back=400):
    """fuyao 指数日线 → [{date, close}] (升序)"""
    inner = _fuyao_call("fuyao-a-share-index", "get_a_share_index_prices_historical", {
        "thscode": thscode, "interval": "1d",
        "start": int((datetime.strptime(end, "%Y-%m-%d").timestamp() - days_back * 86400) * 1000),
        "end": int(datetime.strptime(end, "%Y-%m-%d").timestamp() * 1000),
    })
    out = []
    for row in inner.get("data", {}).get("item", []):
        ts, close = row.get("date_ms"), row.get("close_price")
        if ts and close:
            out.append({"date": datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d"),
                        "close": float(close)})
    out.sort(key=lambda x: x["date"])
    return out


def _ifind_index_window(thscode, d0, d1):
    """iFinD index_data 单窗口(≤55 自然日)。返回 {date: close}"""
    import requests
    auth = ""
    for name, srv in _claude_cfg().get("mcpServers", {}).items():
        if name == "ifind-index":
            auth = srv.get("env", {}).get("IFIND_AUTH", "")
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream",
               "Authorization": "Bearer " + auth}
    requests.post(IFIND_INDEX_URL, json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                   "clientInfo": {"name": "nav-pipeline", "version": "1"}}},
        headers=headers, timeout=60)
    q = "%s 在%s年%s月%s日至%s年%s月%s日期间的每日收盘点位" % (
        thscode, d0.year, d0.month, d0.day, d1.year, d1.month, d1.day)
    r = requests.post(IFIND_INDEX_URL, json={
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "index_data", "arguments": {"query": q}}},
        headers=headers, timeout=120)
    inner = json.loads(r.json()["result"]["content"][0]["text"])
    ans = inner.get("data", "")
    if isinstance(ans, str):
        ans = json.loads(ans)
    out = {}
    for line in ans.get("answer", "").splitlines():
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) >= 4 and c[2].isdigit() and len(c[2]) == 8:
            d8 = c[2]
            try:
                out["%s-%s-%s" % (d8[:4], d8[4:6], d8[6:])] = float(c[3].replace(",", ""))
            except ValueError:
                pass
    return out


def fetch_ifind_index(thscode, end, days_back=400):
    """iFinD 指数日线, 分块抓取绕开单次 100 行截断 → [{date, close}] (升序)

    防污染(2026-09-21 踩坑): iFinD 该 MCP 是**自然语言查询**(非代码查表), 偶发把
    H00300.CSI(全收益) 当成 000300.SH(价格指数) 返回 —— 实测污染段数值与 fuyao
    的价格指数逐位吻合, 量级 4500 vs 正常 6800, 整块突降约 34%。分块边界做连续性
    校验, 越界块直接丢弃(宁可缺一天, 不可污染整段)。
    """
    d1 = datetime.strptime(end, "%Y-%m-%d").date()
    cur = d1 - timedelta(days=days_back)
    merged = {}
    prev_last = None
    while cur <= d1:
        nxt = min(cur + timedelta(days=55), d1)
        chunk = _ifind_index_window(thscode, cur, nxt)
        if chunk:
            dates = sorted(chunk)
            if prev_last is not None:
                ratio = chunk[dates[0]] / prev_last
                # 阈值 0.7/1.43: 正常跨块(至多 ~2 个月)指数波动远小于此,
                # 而价格指数污染约 0.66, 可稳定判别
                if ratio < 0.7 or ratio > 1.43:
                    print("  [warn] %s 块 %s~%s 量级突变 %.0f→%.0f (x%.2f), 判定污染已丢弃"
                          % (thscode, cur, nxt, prev_last, chunk[dates[0]], ratio))
                    cur = nxt + timedelta(days=1)
                    continue
            merged.update(chunk)
            prev_last = chunk[dates[-1]]
        cur = nxt + timedelta(days=1)
    return [{"date": d, "close": v} for d, v in sorted(merged.items())]


def fetch_indexes(end, calendar):
    """三条全收益指数 → {key: [{date, close}]}, 按交易日历过滤非交易日填充行"""
    out = {}
    for key, meta in INDEXES.items():
        try:
            rows = (fetch_ifind_index(meta["code"], end) if meta["src"] == "ifind"
                    else fetch_fuyao_index(meta["code"], end))
            rows = [r for r in rows if r["date"] in calendar and r["date"] <= end]
            # 盘前占位行(2026-09-21 踩坑): 当日未开盘时 iFinD 把上一交易日收盘价
            # 复制到今日(两日值完全相同), 会稀释波动率 → 末尾填充行丢弃。
            # 仅查末尾: 历史序列里零星重复值属正常(涨跌幅恰为 0)
            while len(rows) >= 2 and rows[-1]["close"] == rows[-2]["close"]:
                rows.pop()
            if not rows:
                raise RuntimeError("空序列")
            out[key] = rows
            print("  [%s] %s %d 个交易日, %s -> %s" % (
                meta["src"], meta["name"], len(rows), rows[0]["date"], rows[-1]["date"]))
        except Exception as e:
            print("  [WARN] %s 抓取失败: %s" % (meta["name"], str(e)[:120]))
    return out


def read_ifind_tables():
    """UIA 抓 iFinD 客户端两只产品的净值表格。返回 {code: [{date, nav, pct}]}"""
    from pywinauto import Application
    from pywinauto.keyboard import send_keys

    app = Application(backend="uia").connect(title_re=".*iFinD.*")
    win = app.top_window()
    result = {}

    def dump_nav_table():
        """净值表格: 50 items = 10行 x 5列 (日期|净值|净值|净值|涨跌%)"""
        for t in win.descendants(control_type="Table"):
            items = t.descendants(control_type="DataItem")
            vals = [it.window_text() for it in items if it.window_text().strip()]
            if len(vals) == 50 and vals and vals[0].startswith("20"):
                rows = []
                for i in range(0, 50, 5):
                    row = vals[i:i + 5]
                    if row[0].startswith("20") and row[1]:
                        try:
                            rows.append({
                                "date": norm_num(row[0]),
                                "nav": float(norm_num(row[1])),
                                "pct": float(norm_num(row[4]).rstrip("%")),
                            })
                        except ValueError:
                            continue
                return rows
        return []

    for code, meta in PRODUCTS.items():
        title = ""
        for attempt in range(4):
            if meta["code"] in title:
                break
            # 卡在 i搜索/首页时先恢复
            if "i搜索" in title:
                send_keys("{ESC}")
                time.sleep(1.5)
                win = app.top_window()
            # 点击页面中部激活,再输代码
            win.click_input(coords=(1400, 500))
            time.sleep(0.6)
            send_keys(meta["code"], pause=0.1)
            time.sleep(0.4)
            send_keys("{ENTER}")
            time.sleep(5.0)
            win = app.top_window()
            title = win.window_text()
            print("  切 %s 尝试%d: %s" % (code, attempt + 1, title[:50]))
        if meta["code"] not in title:
            raise RuntimeError("iFinD 未切换到 %s: %s" % (code, title[:60]))
        rows = dump_nav_table()
        if not rows:
            raise RuntimeError("%s 净值表格读取失败(空)" % code)
        result[code] = rows
        print("[iFinD] %s %d 行, 最新 %s 净值 %s" % (
            meta["name"], len(rows), rows[0]["date"], rows[0]["nav"]))
    return result


def load_history():
    base = {"ZY0049": [], "ZY0053": [], "benchmark": []}
    base.update({k: [] for k in INDEXES})
    if HISTORY.exists():
        hist = json.loads(HISTORY.read_text(encoding="utf-8"))
        for k, v in base.items():
            hist.setdefault(k, v)
        return hist
    return base


def norm_num(x: str | float | int | None) -> str:
    """数值字符串规整: 全角负号/百分号/空格 → 半角, 便于 float() 解析。
    2026-09-10: iFinD Excel 偶发全角 '−'/'％' 混入, 解析前统一清洗(双保险)。"""
    if x is None:
        return ""
    s = str(x)
    return s.replace("−", "-").replace("％", "%").replace("　", " ").strip()


def import_excel(excel_dir, hist):
    """--import <目录> : 从 iFinD「业绩表现」导出的 xls 导入历史净值。
    文件名格式: 业绩表现(ZY0049).xls / 业绩表现(ZY0053).xls (实为 xlsx)
    数据源标注"同花顺iFinD", 字段: 时间|单位净值|复权|累计|增长率(%)"""
    for code in PRODUCTS:
        f = Path(excel_dir) / ("业绩表现(%s).xls" % code)
        if not f.exists():
            print("  [skip] 找不到 %s" % f.name)
            continue
        # iFinD 导出的 .xls 实为 xlsx (2026-09-08 踩坑: xlrd 不支持 xlsx)
        # openpyxl 按扩展名判断格式, .xls 扩展名直接拒绝 → 临时复制为 .xlsx 再读
        import openpyxl, shutil, tempfile, os
        tmp_x = os.path.join(tempfile.gettempdir(), "ifind_nav_%s.xlsx" % code)
        shutil.copy(str(f), tmp_x)
        rows = []
        try:
            wb = openpyxl.load_workbook(tmp_x, read_only=True, data_only=True)
            sh = wb["净值走势"]
            for row in sh.iter_rows(min_row=2, values_only=True):
                d = str(row[0] or "").strip()
                nav = row[1]
                pct = row[4]
                if not d.startswith("20") or not isinstance(nav, (int, float)):
                    continue
                pct_s = norm_num(pct)
                rows.append({"date": d[:10], "nav": round(float(nav), 4),
                             "pct": None if pct_s == "" else round(float(norm_num(pct_s).rstrip("%")), 4)})
        finally:
            try:
                wb.close()
            except NameError:
                pass
            os.remove(tmp_x)
        if not rows:
            # 2026-09-14 踩坑: 同花顺导出的 xlsx 用 inline 字符串(t="inlineStr"),
            # sharedStrings 为空, openpyxl 读这些单元格返回 None → 上面 0 行。
            # 回退: 直接解包 sheet1.xml 按列解析 (A=日期, B=单位净值, E=增长率)。
            import zipfile
            import xml.etree.ElementTree as ET
            NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            with zipfile.ZipFile(f) as z:  # 读原文件(此时 tmp_x 已被 finally 清理)
                root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
            for row in root.findall(".//m:row", NS):
                cells = {}
                for c in row.findall("m:c", NS):
                    col = "".join(ch for ch in c.get("r", "") if ch.isalpha())
                    if c.get("t") == "inlineStr":
                        is_el = c.find("m:is", NS)
                        cells[col] = "".join(t.text or "" for t in is_el.iter()) if is_el is not None else ""
                    else:
                        v = c.find("m:v", NS)
                        cells[col] = v.text if v is not None else ""
                d = cells.get("A", "").strip()
                try:
                    nav = float(cells.get("B", ""))
                    pct_s = norm_num(cells.get("E", ""))
                    pct = None if pct_s == "" else round(float(norm_num(pct_s).rstrip("%")), 4)
                except (TypeError, ValueError):
                    continue
                if d.startswith("20"):
                    rows.append({"date": d[:10], "nav": round(nav, 4), "pct": pct})

        by_date = {x["date"]: x for x in hist[code]}
        for x in rows:
            by_date[x["date"]] = x
        hist[code] = sorted(by_date.values(), key=lambda x: x["date"])
        print("  [excel] %s 导入 %d 行, 全量 %d 行, 最早 %s" % (
            code, len(rows), len(hist[code]), hist[code][0]["date"]))
    return hist


def merge(hist, fresh, bench):
    for code, rows in fresh.items():
        by_date = {r["date"]: r for r in hist[code]}
        for r in rows:
            by_date[r["date"]] = r  # 同日覆盖(估值修正)
        hist[code] = sorted(by_date.values(), key=lambda x: x["date"])
    by_date = {r["date"]: r for r in hist["benchmark"]}
    for r in bench:
        by_date[r["date"]] = r
    hist["benchmark"] = sorted(by_date.values(), key=lambda x: x["date"])
    return hist


def merge_indexes(hist, idx):
    """合并全收益指数序列。

    防污染兜底(2026-09-21): 分块校验拦不住"坏块在序列开头"的情况, 这里再拿已有
    历史值做同日期对照 —— 同一日期新旧值差超 25% 判为污染, 保留历史值。正常行情下
    同一交易日的收盘点位不会出现这种量级差异(除非指数编制口径变更, 那需人工确认)。
    """
    for key, rows in idx.items():
        by_date = {r["date"]: r for r in hist[key]}
        dropped = 0
        for r in rows:
            old = by_date.get(r["date"])
            if old and old["close"]:
                ratio = r["close"] / old["close"]
                if ratio < 0.75 or ratio > 1.33:
                    dropped += 1
                    continue
            by_date[r["date"]] = r
        if dropped:
            print("  [warn] %s 有 %d 个日期新旧值差异过大, 已保留历史值" % (key, dropped))
        hist[key] = sorted(by_date.values(), key=lambda x: x["date"])
    return hist


def series_metrics(vals):
    """串行指标: 成立以来% / 最大回撤% / 年化波动率%(252 日)"""
    import math
    if len(vals) < 3:
        return None
    rets = [vals[i] / vals[i - 1] - 1 for i in range(1, len(vals))]
    peak, mdd = vals[0], 0.0
    for v in vals:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    n = len(rets)
    mean = sum(rets) / n
    var = sum((r - mean) ** 2 for r in rets) / (n - 1)
    return {
        "cum": round((vals[-1] / vals[0] - 1) * 100, 2),
        "mdd": round(mdd * 100, 2),
        "vol": round(math.sqrt(var) * math.sqrt(252) * 100, 2),
    }


def calc_metrics(hist):
    """从净值序列自算指标。数字全部可溯源,无估计值。"""
    out = {"updated": datetime.now().strftime("%Y-%m-%d %H:%M"), "products": {}}
    for code, meta in PRODUCTS.items():
        rows = hist[code]
        if len(rows) < 2:
            continue
        latest = rows[-1]
        # 成立以来: 产品成立日面值 1.0000 为基准(与一页通 PDF 口径一致)
        cum = (latest["nav"] / 1.0 - 1) * 100

        def win_ret(n):
            if len(rows) <= n:
                return None
            return (latest["nav"] / rows[-(n + 1)]["nav"] - 1) * 100

        own = series_metrics([r["nav"] for r in rows])

        d0 = datetime.strptime(rows[0]["date"], "%Y-%m-%d")
        d1 = datetime.strptime(latest["date"], "%Y-%m-%d")
        years = max((d1 - d0).days / 365.25, 1e-6)
        ann = ((latest["nav"] / 1.0) ** (1 / years) - 1) * 100

        # 成立以来收益对照: 三条全收益指数取产品成立日起的同窗口
        peer = {}
        for key, imeta in INDEXES.items():
            # 与产品同窗口: 起点取产品成立日, 终点截止到产品最新净值日
            # (否则指数多出的交易日会让对照失真 —— PDF 口径即同区间)
            seg = [r["close"] for r in hist.get(key, [])
                   if meta["inception"] <= r["date"] <= latest["date"]]
            m = series_metrics(seg)
            if m:
                peer[key] = m

        out["products"][code] = {
            "name": meta["name"],
            "wind": meta["wind"],
            "inception": meta["inception"],
            "latest_date": latest["date"],
            "nav": latest["nav"],
            "daily_pct": latest.get("pct"),
            "cum_return": round(cum, 2),
            "ret_7d": None if win_ret(7) is None else round(win_ret(7), 2),
            "ret_30d": None if win_ret(30) is None else round(win_ret(30), 2),
            "max_drawdown": own["mdd"] if own else 0.0,
            "vol": own["vol"] if own else None,
            "annualized": round(ann, 2),
            "since": rows[0]["date"],
            "peer": peer,
            "nav_series": [{"d": r["date"], "v": r["nav"]} for r in rows],
        }
    out["benchmark"] = hist["benchmark"]
    out["benchmark_name"] = "沪深300"
    out["indices"] = {k: {"name": INDEXES[k]["name"],
                          "series": [{"d": r["date"], "v": r["close"]} for r in hist.get(k, [])]}
                      for k in INDEXES}
    return out


def main():
    dry = "--dry-run" in sys.argv
    push = "--no-push" not in sys.argv
    # Excel 导入模式(2026-09-09 起默认): 不碰 UI 不抢鼠标, 读固定导出目录
    EXPORT_DIR = BASE / "ifind_exports"
    excel_dir = EXPORT_DIR
    if "--import" in sys.argv:
        excel_dir = Path(sys.argv[sys.argv.index("--import") + 1])
    ui_mode = "--ui" in sys.argv  # 显式要求才走 UI 抓取(会抢鼠标,慎用)

    print("=" * 56)
    print("[1/3] 产品净值 (%s)" % datetime.now().strftime("%H:%M"))
    hist = load_history()

    # 基准(沪深300)永远可以更新: fuyao API, 不碰 UI
    print("[2/3] fuyao 拉沪深300")
    today = datetime.now().strftime("%Y-%m-%d")
    bench = fetch_hs300(today)

    # 三条全收益指数(一页通对照表用): iFinD HTTP + fuyao, 均不碰 UI
    print("[2.5/3] 拉全收益指数(300/创业板/科创50)")
    try:
        calendar = fetch_trading_days()
        idx = fetch_indexes(today, calendar)
        hist = merge_indexes(hist, idx)
    except Exception as e:
        print("[WARN] 指数抓取整体失败, 沿用历史值: %s" % str(e)[:150])

    xls_ok = all((excel_dir / ("业绩表现(%s).xls" % c)).exists() for c in PRODUCTS)
    got_fresh = False
    if ui_mode:
        print("[ui] 显式 --ui 模式, 抓取会占用界面约30秒")
        fresh = read_ifind_tables()
        hist = merge(hist, fresh, bench)
        got_fresh = True
    elif xls_ok:
        print("[excel] 从 %s 导入 iFinD 业绩表现导出件" % excel_dir)
        hist = import_excel(excel_dir, hist)
    else:
        idle = system_idle_seconds()
        print("[idle] 当前空闲 %.0f 秒 (阈值 %d 秒)" % (idle, IDLE_MIN_SECONDS))
        if idle >= IDLE_MIN_SECONDS:
            print("[ui-auto] 老板已离开, 自动无感抓取(约30秒, 抓完还原前台窗口)")
            fg = ctypes.windll.user32.GetForegroundWindow()
            try:
                fresh = read_ifind_tables()
                hist = merge(hist, fresh, bench)
                got_fresh = True
            finally:
                ctypes.windll.user32.SetForegroundWindow(fg)
        else:
            print("[skip] 老板在用电脑, 不抓 UI。产品净值保留旧值, 基准照常更新")

    if not got_fresh:
        # 无新产品数据时也把基准合并进去
        by_date = {r["date"]: r for r in hist["benchmark"]}
        for r in bench:
            by_date[r["date"]] = r
        hist["benchmark"] = sorted(by_date.values(), key=lambda x: x["date"])

    # 新鲜度校验(2026-09-14 踩坑): 导出件旧于客户端披露, 管道照跑但产品净值
    # 静默停在旧值, 首页数字一直不涨。基准(沪深300)永远最新 → 用基准序列
    # 数产品落后几个交易日; ≥2 时: 老板离开(空闲达标)自动 UIA 补抓, 否则只告警。
    def bench_ahead(code):
        import bisect
        bdates = [x["date"] for x in hist["benchmark"]]
        latest = hist[code][-1]["date"]
        if latest >= bdates[-1]:
            return 0
        return len(bdates) - bisect.bisect_right(bdates, latest)

    if not ui_mode and not got_fresh:
        stale = [c for c in PRODUCTS if bench_ahead(c) >= 2]
        if stale:
            for c in stale:
                print("[stale] %s 净值最新 %s, 基准已到 %s (落后 %d 个交易日) — 导出件可能旧了"
                      % (PRODUCTS[c]["name"], hist[c][-1]["date"],
                         hist["benchmark"][-1]["date"], bench_ahead(c)))
            idle = system_idle_seconds()
            if idle >= IDLE_MIN_SECONDS:
                print("[stale-ui] 老板已离开(空闲 %.0f 秒), 自动 UIA 补抓" % idle)
                fg = ctypes.windll.user32.GetForegroundWindow()
                try:
                    fresh = read_ifind_tables()
                    hist = merge(hist, fresh, bench)
                    got_fresh = True
                finally:
                    ctypes.windll.user32.SetForegroundWindow(fg)
            else:
                print("[stale-skip] 老板在用电脑, 不抢 UI。稍后请 py update_nav.py --ui 手动补抓")

    for k in ("ZY0049", "ZY0053"):
        hist[k] = hist[k][-400:]
    hist["benchmark"] = hist["benchmark"][-250:]
    for k in INDEXES:
        hist[k] = hist[k][-300:]

    if dry:
        print("[dry-run] 不写库")
    else:
        HISTORY.write_text(json.dumps(hist, ensure_ascii=False, indent=1), encoding="utf-8")
        data = calc_metrics(hist)
        DATA.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        print("[3/3] 指标已算, nav-data.json 更新")

    if not dry and push:
        r = subprocess.run(["git", "-C", str(SITE), "add", "-A"],
                           capture_output=True, text=True)
        r = subprocess.run(
            ["git", "-C", str(SITE), "commit", "-m",
             "产品净值更新 %s" % datetime.now().strftime("%Y-%m-%d")],
            capture_output=True, text=True)
        if "nothing to commit" not in r.stdout + r.stderr:
            r = subprocess.run(["git", "-C", str(SITE), "push"],
                               capture_output=True, text=True)
            if r.returncode == 0:
                print("[push] everstead-site 已发布")
            else:
                print("[push FAIL] %s" % r.stderr[-200:])
    print("[ok] 完成")


if __name__ == "__main__":
    main()
