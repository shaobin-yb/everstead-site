# -*- coding: utf-8 -*-
"""
重点产品净值管道 update_nav.py
──────────────────────────────
数据源:
  1. 产品净值 — 同花顺 iFinD 客户端「保险资管-深度资料」页 (UIA 抓取)
     代码: ZY0049.BZJ (中邮资管价值策略1号)
           ZY0053.BZJ (中邮资管红利质量量化选股策略)
  2. 基准     — 沪深300 日收盘 (fuyao HTTP API, 000300.SH)

流程: 抓两只产品深度资料页表格(最近10个交易日净值+日涨跌%)
      → 抓沪深300 同窗口收盘价
      → 追加进 nav-history.json (按日去重)
      → 自算指标 → 写 nav-data.json (前端渲染用)

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
from datetime import datetime
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
    "ZY0049": {"name": "中邮资管价值策略1号", "code": "ZY0049.BZJ"},
    "ZY0053": {"name": "中邮资管红利质量量化选股策略", "code": "ZY0053.BZJ"},
}


def _fuyao_key():
    """fuyao key 从 ~/.claude.json 读"""
    cfg = json.loads(open(Path.home() / ".claude.json", encoding="utf-8").read())
    for name, srv in cfg.get("mcpServers", {}).items():
        if name == "fuyao-a-share-index":
            return srv.get("headers", {}).get("X-api-key", "")
    return ""


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
    if HISTORY.exists():
        return json.loads(HISTORY.read_text(encoding="utf-8"))
    return {"ZY0049": [], "ZY0053": [], "benchmark": []}


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


def calc_metrics(hist):
    """从净值序列自算指标。数字全部可溯源,无估计值。"""
    out = {"updated": datetime.now().strftime("%Y-%m-%d %H:%M"), "products": {}}
    for code, meta in PRODUCTS.items():
        rows = hist[code]
        if len(rows) < 2:
            continue
        latest = rows[-1]
        start_nav = rows[0]["nav"]
        cum = (latest["nav"] / start_nav - 1) * 100

        def win_ret(n):
            if len(rows) <= n:
                return None
            return (latest["nav"] / rows[-(n + 1)]["nav"] - 1) * 100

        peak, max_dd = rows[0]["nav"], 0.0
        for r in rows:
            peak = max(peak, r["nav"])
            dd = (r["nav"] / peak - 1) * 100
            max_dd = min(max_dd, dd)

        d0 = datetime.strptime(rows[0]["date"], "%Y-%m-%d")
        d1 = datetime.strptime(latest["date"], "%Y-%m-%d")
        years = max((d1 - d0).days / 365.25, 1e-6)
        ann = ((latest["nav"] / start_nav) ** (1 / years) - 1) * 100

        out["products"][code] = {
            "name": meta["name"],
            "latest_date": latest["date"],
            "nav": latest["nav"],
            "daily_pct": latest.get("pct"),
            "cum_return": round(cum, 2),
            "ret_7d": None if win_ret(7) is None else round(win_ret(7), 2),
            "ret_30d": None if win_ret(30) is None else round(win_ret(30), 2),
            "max_drawdown": round(max_dd, 2),
            "annualized": round(ann, 2),
            "since": rows[0]["date"],
            "nav_series": [{"d": r["date"], "v": r["nav"]} for r in rows],
        }
    out["benchmark"] = hist["benchmark"]
    out["benchmark_name"] = "沪深300"
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
    bench = fetch_hs300(datetime.now().strftime("%Y-%m-%d"))

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

    for k in ("ZY0049", "ZY0053"):
        hist[k] = hist[k][-400:]
    hist["benchmark"] = hist["benchmark"][-250:]

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
