# -*- coding: utf-8 -*-
"""
重点产品净值 OCR 抓取管道
─────────────────────────
背景（2026-09-20 定型）:
  iFinD「其他理财净值走势」页是 CEF 内嵌网页，canvas 绘制，
  UIA 只能看到 10 个控件 → 表格抓取必失败 → 改用 OCR 读右侧数据面板。

三个已验证的关键点:
  1. PrintWindow 抓不到 CEF 内容（窗口 2880x1800 只返回 1646x1029 陈旧画面）
     → 必须用屏幕像素直截 ImageGrab
  2. 绝不可 OCR 图表区 —— 图上数值随鼠标位置变（曾误读光标点为净值）
     → 只读右侧固定字段面板
  3. 导航: send_keys 输入 "ZY0049.BZJ" + 回车 可切页（实测成功）

流程:
  弹窗确认（10秒无响应=放行）→ 切页 → 截图 → OCR → 解析
  → 写入 nav-history.json → 切回 Claude 窗口 + 完成提示

实测耗时（2026-09-20 优化后）:
  两只产品合计 29 秒（最坏约 45 秒）。优化点:
  - 原固定 sleep(8) 盲等 → 改为轮询窗口标题（省约 12 秒）
  - 弹窗从 3 秒改为 10 秒无响应放行

用法:
  py ocr_nav.py              # 弹窗确认后抓取并写库
  py ocr_nav.py --dry-run    # 只抓不写
  py ocr_nav.py --no-ask     # 不弹窗直接抓（供定时任务/空闲自动触发）
"""
import ctypes
import json
import re
import sys
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

from PIL import ImageGrab

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
HISTORY = BASE / "nav-history.json"

PRODUCTS = {
    "ZY0049": {"name": "中邮资管价值策略1号", "code": "ZY0049.BZJ"},
    "ZY0053": {"name": "中邮资管红利质量量化选股策略", "code": "ZY0053.BZJ"},
}

# 弹窗（2026-09-20 老板定：10 秒无响应 = 自动放行）
MB_YESNO = 0x00000004
MB_ICONQUESTION = 0x00000020
MB_TOPMOST = 0x00040000
MB_SETFOREGROUND = 0x00010000
IDYES, IDNO, IDTIMEOUT = 6, 7, 32000
POPUP_MS = 10000         # 10 秒无响应 = 自动放行
RETRY_MINUTES = 5        # 选"否"后 5 分钟重问

u = ctypes.windll.user32
u.SetProcessDPIAware()
u.MessageBoxTimeoutW.restype = ctypes.c_int


def log(msg):
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg), flush=True)


def idle_seconds():
    class LII(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
    lii = LII()
    lii.cbSize = ctypes.sizeof(LII)
    u.GetLastInputInfo(ctypes.byref(lii))
    return (ctypes.windll.kernel32.GetTickCount() - lii.dwTime) / 1000.0


def ask_permission():
    """10 秒无响应 = 放行；选否 = 等 5 分钟重问；循环直到允许。

    弹窗期间会抢焦点(否则老板看不到), 但**不碰键鼠**——只等待。
    """
    u.MessageBoxTimeoutW.restype = ctypes.c_int
    while True:
        r = u.MessageBoxTimeoutW(
            None,
            "要现在抓产品净值吗？\n\n"
            "会占用鼠标约 1-2 分钟，期间请不要操作电脑。\n"
            "抓完会自动切回对话窗口提醒你。\n\n"
            "10 秒不选 = 自动开始。",
            "铁蛋 · 净值抓取",
            MB_YESNO | MB_ICONQUESTION | MB_TOPMOST | MB_SETFOREGROUND,
            0, POPUP_MS,
        )
        if r in (IDYES, IDTIMEOUT):
            log("已获准（%s）" % ("点选是" if r == IDYES else "超时放行"))
            return True
        if r == IDNO:
            log("已选否，%d 分钟后重问" % RETRY_MINUTES)
            time.sleep(RETRY_MINUTES * 60)
            continue
        return True


def ifind_hwnd():
    h = u.FindWindowW("iFinD", None)
    if not h:
        raise RuntimeError("找不到 iFinD 窗口（客户端未运行？）")
    return h


def win_title(hwnd):
    n = u.GetWindowTextLengthW(hwnd)
    b = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(hwnd, b, n + 1)
    return b.value


def grab(hwnd):
    """截取窗口区域（屏幕像素直截，PrintWindow 对 CEF 无效）"""
    r = wintypes.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    # 最小化窗口 rect 会是 (-32000,-32000,-31724,-31955) 的 276x45 残片,
    # 只判 w<=0 拦不住 → 会拿残片 OCR 出空结果静默失败(2026-09-21)。用绝对下限截断
    if w < 800 or h < 600:
        raise RuntimeError("窗口尺寸异常 %dx%d（最小化或未就绪？）" % (w, h))
    return ImageGrab.grab(all_screens=True).crop((r.left, r.top, r.right, r.bottom))


def goto_product(hwnd, code, timeout=12):
    """send_keys 输入产品代码切页。

    2026-09-20 优化: 原固定 sleep(8) 是最大浪费(占总耗时 34%)。
    改为**轮询窗口标题**——标题一变成目标页就立即返回, 通常 2-4 秒即可。
    """
    from pywinauto.keyboard import send_keys

    # 最小化时 SetForegroundWindow 无效, 且标题轮询会误判成功
    # (最小化标题仍含"净值走势"), 导致对着 276x45 残片 OCR → 静默失败(2026-09-21)
    if u.IsIconic(hwnd):
        log("  窗口最小化, 先恢复")
        u.ShowWindow(hwnd, 9)          # SW_RESTORE
        time.sleep(1.0)

    u.SetForegroundWindow(hwnd)
    time.sleep(0.5)
    for ch in code:
        send_keys(ch, pause=0.07)
    time.sleep(0.8)
    send_keys("{ENTER}")

    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(0.3)
        title = win_title(hwnd)
        if "净值走势" in title or "深度资料" in title or code.split(".")[0] in title:
            time.sleep(0.6)      # 标题变了再多等一点, 让内容渲染完
            return win_title(hwnd)
    return win_title(hwnd)


def crop_panel(img):
    """裁右侧数据面板（约窗口右侧 23%，纵向 6%~62%），放大 3 倍提升 OCR 命中"""
    from PIL import Image
    w, h = img.size
    c = img.crop((int(w * 0.77), int(h * 0.06), w, int(h * 0.62)))
    return c.resize((c.width * 3, c.height * 3), Image.LANCZOS)


def parse_panel(res):
    """从 OCR 结果解析字段。

    实测面板两列布局（截自 2004x2922 放大图）:
        y=534  [x=496]最新净值 [x=1029]1.0393  ｜ [x=1286]上期净值 [x=1833]1.0427
        y=820  [x=421]涨跌     [x=1027]-0.003  ｜ [x=1306]累计净值 [x=1832]1.0393
        y=1113 [x=421]涨幅     [x=1173]-0.33%最新日期  [x=1772]20260917

    值列在 x≈1020(左) 和 x≈1830(右)。左列标签在 x≈420-500。
    → **按 y 行 + x 分列** 解析, 不能靠出现顺序。
    """
    items = []
    for it in (res or []):
        try:
            box, text = it[0], it[1]
            y = sum(p[1] for p in box) / 4.0
            x = sum(p[0] for p in box) / 4.0
            items.append((y, x, text.strip()))
        except Exception:
            continue

    # 左列值区 x∈[950,1250], 右列值区 x>1600
    def is_left_value(x):
        return 950 <= x <= 1250

    def is_right_value(x):
        return x > 1600

    out = {}
    nav_left, nav_right = [], []

    for y, x, text in items:
        t = text.replace(" ", "")

        # 净值（1.xxxx 形态）
        for m in re.finditer(r"1\.\d{3,6}", t):
            v = float(m.group())
            if is_left_value(x) and not nav_left:
                nav_left.append((y, v))
            elif is_right_value(x) and not nav_right:
                nav_right.append((y, v))

        # 日期
        m = re.search(r"(20\d{6})", t)
        if m:
            out.setdefault("date_raw", m.group(1))

        # 当日涨幅: 与日期同一行(黏在一起), 或 x 落到左列值区且带 %
        m = re.search(r"(-?\d+\.\d+)%", t)
        if m and "净值" not in t:
            pct = float(m.group(1))
            if "最新日期" in t or (is_left_value(x) and abs(pct) < 20):
                out.setdefault("pct", pct)

    # 日期行的 y 用于定位涨幅（两列都可能出现"涨幅"标签）
    date_y = None
    for y, x, text in items:
        if re.search(r"20\d{6}", text):
            date_y = y
            break

    if nav_left:
        out["nav"] = min(nav_left)[1]
    if nav_right:
        out["prev_nav"] = min(nav_right)[1]
    return out


def fetch_one(hwnd, code, meta, ocr):
    log("切 %s (%s)" % (meta["name"], code))
    title = goto_product(hwnd, code)
    if code not in title and "净值" not in title:
        log("  ⚠️ 标题异常: %s" % title[:50])
        return None

    img = grab(hwnd)
    panel_path = BASE / ("_panel_%s.png" % code)
    crop_panel(img).save(panel_path)
    r = ocr(str(panel_path))
    res = r[0] if isinstance(r, tuple) else r
    panel_path.unlink(missing_ok=True)
    data = parse_panel(res)

    if not data.get("nav") or not data.get("date_raw"):
        log("  ❌ 解析失败: %s" % data)
        return None

    d = data["date_raw"]
    date = "%s-%s-%s" % (d[:4], d[4:6], d[6:])
    nav = data["nav"]

    # 交叉校验: 用上期净值和涨幅反推, 偏差应 < 0.05 个百分点
    check = ""
    if data.get("prev_nav") and data.get("pct") is not None:
        expect = (nav / data["prev_nav"] - 1) * 100
        diff = abs(expect - data["pct"])
        check = " [校验 %.2f%% vs %.2f%% 偏差%.3f]" % (expect, data["pct"], diff)
        if diff > 0.05:
            log("  ⚠️ 校验偏差过大，可能 OCR 误读")

    log("  ✅ %s 净值 %s%s" % (date, nav, check))
    return {"date": date, "nav": nav, "pct": data.get("pct")}


def back_to_claude():
    """抓取完成后把 Claude 对话窗口切回前台, 给老板明确的'可以继续用电脑了'信号"""
    try:
        h = u.FindWindowW("Chrome_WidgetWin_1", "Claude")
        if not h:
            # 标题可能带后缀, 找含 "Claude" 的
            for cand in _visible_windows():
                if "Claude" in cand[1]:
                    h = cand[0]
                    break
        if h:
            u.ShowWindow(h, 9)          # SW_RESTORE
            time.sleep(0.3)
            u.SetForegroundWindow(h)
            log("已切回 Claude 对话窗口")
        else:
            log("未找到 Claude 窗口（不影响抓取结果）")
    except Exception as e:
        log("切回窗口失败: %s" % str(e)[:60])


def _visible_windows():
    out = []
    PP = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def cb(h, l):
        if u.IsWindowVisible(h):
            n = u.GetWindowTextLengthW(h)
            if n:
                b = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(h, b, n + 1)
                out.append((h, b.value))
        return True

    u.EnumWindows(PP(cb), 0)
    return out


def notify_done(fresh, ok=True):
    """完成提示: 置顶弹窗, 3 秒自动关（不阻塞）"""
    if ok and fresh:
        lines = ["抓取完成 ✓", ""]
        for code, r in fresh.items():
            lines.append("%s  %s  净值 %s" % (
                PRODUCTS[code]["name"][:12], r["date"], r["nav"]))
        lines.append("")
        lines.append("已切回对话窗口，可以继续用电脑了。")
        msg = "\n".join(lines)
    else:
        msg = "抓取未成功，请查看对话窗口的输出日志。"
    u.MessageBoxTimeoutW(None, msg, "铁蛋 · 净值抓取", 0x00000040 | MB_TOPMOST | MB_SETFOREGROUND,
                         0, 3000)


def main():
    dry = "--dry-run" in sys.argv
    no_ask = "--no-ask" in sys.argv

    hwnd = ifind_hwnd()
    log("窗口: %s" % win_title(hwnd)[:60])

    if not no_ask:
        if not ask_permission():
            log("未获准，退出")
            return

    from rapidocr_onnxruntime import RapidOCR
    ocr = RapidOCR()

    fresh = {}
    for code, meta in PRODUCTS.items():
        try:
            row = fetch_one(hwnd, code, meta, ocr)
            if row:
                fresh[code] = row
        except Exception as e:
            log("  ❌ %s 失败: %s" % (code, str(e)[:100]))

    log("抓取结果: %s" % json.dumps(fresh, ensure_ascii=False))
    if not fresh:
        log("无数据，退出")
        back_to_claude()
        notify_done({}, ok=False)
        return

    if dry:
        log("[dry-run] 不写库")
        back_to_claude()
        notify_done(fresh)
        return

    hist = json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else {}
    for code, row in fresh.items():
        by_date = {x["date"]: x for x in hist.get(code, [])}
        by_date[row["date"]] = row
        hist[code] = sorted(by_date.values(), key=lambda x: x["date"])
        log("  %s 写入 %s=%s, 共 %d 条" % (code, row["date"], row["nav"], len(hist[code])))

    HISTORY.write_text(json.dumps(hist, ensure_ascii=False, indent=1), encoding="utf-8")
    log("[ok] nav-history.json 已更新")

    # 重算指标 + 刷新前端数据
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("un", BASE / "update_nav.py")
        un = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(un)
        data = un.calc_metrics(hist)
        (BASE / "nav-data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        log("[ok] nav-data.json 已刷新")
    except Exception as e:
        log("[WARN] 指标重算失败: %s" % str(e)[:120])

    # 完成信号: 切回对话窗口 + 置顶提示
    back_to_claude()
    notify_done(fresh)


if __name__ == "__main__":
    main()
