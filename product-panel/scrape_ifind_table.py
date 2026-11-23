# -*- coding: utf-8 -*-
"""iFinD「业绩走势-数据表格」净值抓取管道。

背景(2026-11-23): iFinD 升级后 UIA 表格抓取失效(翻页后 UIA 树不刷新)、旧 ocr_nav 导航失效。
现方案: 截图 OCR 读「数据表格」(实测 10/10 准) + 点击底部页码翻页, 覆盖到历史已有日期为止。
校验: 净值范围 0.5~5.0 过滤 OCR 误读; 抓完由 update_nav.py 逐日涨跌幅互验。

前置: iFinD 客户端已启动并登录, 窗口可被最大化(脚本会自动置前+最大化, 占用鼠标 1-2 分钟)。
用法:
  py scrape_ifind_table.py            # 抓取并打印, 不写库
  py scrape_ifind_table.py --write    # 抓取并写入 nav-history.json
之后: py update_nav.py --no-push      # 重算指标写 nav-data.json
"""
import ctypes
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import pyautogui
import win32con
import win32gui
from PIL import ImageGrab
from pywinauto import Application

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def find_ifind_window():
    """按标题动态找 iFinD 主窗口(句柄每次启动会变)。"""
    found = []
    def each(h, o):
        t = win32gui.GetWindowText(h)
        if 'iFinD' in t and win32gui.IsWindowVisible(h):
            o.append(h)
    win32gui.EnumWindows(each, found)
    return found[0] if found else None


H = find_ifind_window()
HISTORY = Path(r"D:\cloude code\everstead-site\product-panel\nav-history.json")
PRODUCTS = {"ZY0049": "中邮资管价值策略1号", "ZY0053": "中邮资管红利质量量化选股策略"}
CODES = {"ZY0049": "ZY0049.BZJ", "ZY0053": "ZY0053.BZJ"}
user32 = ctypes.windll.user32


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def foreground():
    fg = user32.GetForegroundWindow()
    fg_t = user32.GetWindowThreadProcessId(fg, None)
    t_t = user32.GetWindowThreadProcessId(H, None)
    user32.AttachThreadInput(fg_t, t_t, True)
    win32gui.ShowWindow(H, win32con.SW_MAXIMIZE)
    user32.SetForegroundWindow(H)
    user32.BringWindowToTop(H)
    user32.AttachThreadInput(fg_t, t_t, False)
    time.sleep(0.8)


def get_table_rect():
    app = Application(backend="uia").connect(handle=H)
    win = app.window(handle=H)
    tables = win.descendants(control_type="Table")
    # 净值表格 = 50 个 DataItem 且首值像日期
    for t in tables:
        items = [it.window_text() for it in t.descendants(control_type="DataItem")
                 if it.window_text().strip()]
        if len(items) == 50 and re.match(r"20\d{2}-\d{2}-\d{2}", items[0] or ""):
            return t.rectangle()
    # 兜底: 用第 5 个 Table
    return tables[4].rectangle()


def grab_rows(rect, ocr):
    img = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom))
    res, _ = ocr(np.array(img))
    col_w = (rect.right - rect.left) / 5.0
    rows = {}
    for it in (res or []):
        if it is None or len(it) < 2:
            continue
        box, text = it[0], it[1]
        cx = sum(p[0] for p in box) / 4
        cy = sum(p[1] for p in box) / 4
        key = round(cy / 25)
        rows.setdefault(key, []).append((cx, text.strip()))
    out = []
    for key in sorted(rows):
        cells = sorted(rows[key])
        vals = {}
        for cx, text in cells:
            ci = min(int(cx // col_w), 4)
            vals.setdefault(ci, text)
        d = vals.get(0, "")
        if re.match(r"20\d{2}-\d{2}-\d{2}$", d):
            try:
                nav = float(vals.get(1, ""))
                pct_s = vals.get(4, "").replace("%", "").strip()
                pct = float(pct_s) if pct_s not in ("", "--") else None
            except ValueError:
                continue
            if not (0.5 < nav < 5.0):   # 净值合理性过滤(OCR 误读如 492.0 直接丢弃)
                continue
            out.append({"date": d, "nav": round(nav, 4), "pct": pct})
    return out


def click_page(rect, delta):
    """delta=-1 上一页, +1 下一页。分页器在表格底部, 右对齐。"""
    x_next = rect.right - 26
    x_prev = rect.right - 503
    y = rect.bottom + 37
    pyautogui.click(x_next if delta > 0 else x_prev, y)
    time.sleep(2.8)   # 数据远程加载, 1.8s 不够(2026-11-23 第4页只读到1行)


def switch_product(code):
    """照抄 ocr_nav.goto_product: 不点鼠标, 直接 send_keys 输入代码 + 回车, 轮询标题。"""
    from pywinauto.keyboard import send_keys
    if win32gui.IsIconic(H):
        win32gui.ShowWindow(H, win32con.SW_RESTORE)
        time.sleep(1.0)
    user32.SetForegroundWindow(H)
    time.sleep(0.5)
    for ch in code:
        send_keys(ch, pause=0.07)
    time.sleep(0.8)
    send_keys("{ENTER}")
    t0 = time.time()
    while time.time() - t0 < 15:
        time.sleep(0.3)
        if code.split(".")[0] in win32gui.GetWindowText(H):
            time.sleep(2.0)   # 让表格数据渲染
            return win32gui.GetWindowText(H)
    return win32gui.GetWindowText(H)


def scrape_product(code, stop_date, ocr):
    """从第 1 页开始往后翻, 直到页面最旧日期 <= stop_date 或连续重复。"""
    rows_all = {}
    prev_first = None
    for page in range(1, 15):
        rect = get_table_rect()
        rows = grab_rows(rect, ocr)
        if len(rows) < 8:      # 可能页面还没渲染完, 等 2 秒重试一次
            log(f"  第{page}页仅 {len(rows)} 行, 重试")
            time.sleep(2.0)
            rows = grab_rows(rect, ocr)
        if not rows:
            log(f"  第{page}页 OCR 为空, 停止")
            break
        for r in rows:
            rows_all[r["date"]] = r
        log(f"  第{page}页 {len(rows)} 行 {rows[0]['date']} ~ {rows[-1]['date']} (累计 {len(rows_all)})")
        if rows[0]["date"] == prev_first:
            log("  页面未变化, 停止")
            break
        prev_first = rows[0]["date"]
        if min(r["date"] for r in rows) <= stop_date:
            log(f"  已覆盖到 {stop_date}, 停止")
            break
        click_page(rect, +1)
    return sorted(rows_all.values(), key=lambda x: x["date"])


def main():
    write = "--write" in sys.argv
    foreground()
    log(f"前台: {win32gui.GetWindowText(win32gui.GetForegroundWindow())[:50]}")

    from rapidocr_onnxruntime import RapidOCR
    ocr = RapidOCR()

    hist = json.loads(HISTORY.read_text(encoding="utf-8"))
    result = {}
    for code in PRODUCTS:
        log(f"=== {code} {PRODUCTS[code]} ===")
        switch_product(CODES[code])
        log(f"  当前标题: {win32gui.GetWindowText(H)[:60]}")
        existing = hist.get(code, [])
        stop = existing[-1]["date"] if existing else "2000-01-01"
        log(f"  已有最新 {stop}, 抓取更新的部分")
        # 确保在第 1 页: 点上一页几次(到第 1 页幂等)
        rect = get_table_rect()
        for _ in range(12):
            click_page(rect, -1)
            time.sleep(0.4)
        time.sleep(1.0)
        rows = scrape_product(code, stop, ocr)
        result[code] = rows
        log(f"  共 {len(rows)} 行, 最新 {rows[0]['date'] if rows else '-'}")

    # 合并统计
    total_new = 0
    for code, rows in result.items():
        by_date = {x["date"]: x for x in hist.get(code, [])}
        before = len(by_date)
        for r in rows:
            by_date[r["date"]] = {"date": r["date"], "nav": r["nav"], "pct": r["pct"]}
        hist[code] = sorted(by_date.values(), key=lambda x: x["date"])
        added = len(hist[code]) - before
        total_new += added
        log(f"{code}: 历史 {before} → {len(hist[code])} (+{added}), 最新 {hist[code][-1]['date']}")

    if write and total_new > 0:
        HISTORY.write_text(json.dumps(hist, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"已写库 {HISTORY}")
    else:
        log(f"[dry-run] 不写库 (新增 {total_new})")

    out = Path(r"D:\cloude code\_tmp\ifind_scrape_result.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"结果存 {out}")


if __name__ == "__main__":
    main()
