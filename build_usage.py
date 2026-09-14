# -*- coding: utf-8 -*-
"""
Token 用量展板数据聚合 → tools/token-usage/index.html (2026-09-14 老板需求)

扫描 ~/.claude/projects/**/*.jsonl 会话转录, 按主会话 assistant 消息的 usage 求和
(输入/输出/缓存读/缓存写), 聚合出: 每日趋势 × 模型 / 项目 / 会话 三视图 + KPI。
时间统一转北京时间按日分桶。数据内联进页面 HTML —— 页面带 CRM 同级密码门,
不产出公开 JSON, 且上搜索索引排除表。

用法:
  py build_usage.py            # 增量扫描(状态文件记 mtime+字节偏移, 只读新增行)
  py build_usage.py --full     # 全量重扫
  py build_usage.py --dry      # 只打印统计不写页面
"""
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECTS_DIR = Path.home() / ".claude" / "projects"
STATE_FILE = Path("D:/cloude code/.usage_scan_state.json")
SITE = Path(__file__).resolve().parent
OUT = SITE / "tools" / "token-usage" / "index.html"

TZ = timezone(timedelta(hours=8))  # 北京时间
TITLE_LEN = 42
TOP_SESSIONS = 30


def bj_date(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.astimezone(TZ).strftime("%Y-%m-%d")
    except Exception:
        return ""


def project_label(cwd: str) -> str:
    c = (cwd or "").replace("/", "\\")
    low = c.lower()
    if c == r"D:\cloude code":
        return "主工作区"
    if low.startswith(r"d:\cloude code\everstead-site"):
        return "成果站"
    if low.startswith(r"d:\cloude code"):
        return "主工作区子项目"
    if low.startswith(r"c:\users\13167\.claude"):
        return "铁蛋配置"
    if low.startswith(r"c:\users\13167\desktop"):
        return "桌面"
    return "其他"


def user_text(content) -> str:
    """从消息 content 提取纯文本(首条用户消息 → 会话标题)。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                parts.append(b.get("text", ""))
        return " ".join(parts)
    return ""


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state), encoding="utf-8")


def main():
    full = "--full" in sys.argv
    dry = "--dry" in sys.argv
    t0 = datetime.now()
    state = {} if full else load_state()
    # 会话累计聚合从状态恢复(增量时新行叠加到历史累计上)
    sessions = defaultdict(lambda: {"title": "", "cwd": "", "first": "", "last": "",
                                    "total": 0, "models": defaultdict(lambda: [0, 0, 0, 0])})
    for sid, s0 in state.get("sessions", {}).items():
        s = sessions[sid]
        s.update({"title": s0.get("title", ""), "cwd": s0.get("cwd", ""),
                  "first": s0.get("first", ""), "last": s0.get("last", ""),
                  "total": s0.get("total", 0)})
        for m, v in (s0.get("models") or {}).items():
            s["models"][m] = list(v)
    days = defaultdict(lambda: {"total": 0, "input": 0, "output": 0, "cache_read": 0,
                                "cache_creation": 0, "by_model": defaultdict(int),
                                "model_detail": defaultdict(lambda: [0, 0, 0, 0]),
                                "sessions": set()})
    # 每日聚合: 状态存日级累计, 新行往上叠加(不重放历史)
    for day, d0 in state.get("days", {}).items():
        dd = days[day]
        dd.update({"total": d0.get("total", 0), "input": d0.get("input", 0),
                   "output": d0.get("output", 0), "cache_read": d0.get("cache_read", 0),
                   "cache_creation": d0.get("cache_creation", 0)})
        for m, v in (d0.get("by_model") or {}).items():
            dd["by_model"][m] = v
        for m, v in (d0.get("model_detail") or {}).items():
            dd["model_detail"][m] = list(v)
        dd["sessions"] = set(d0.get("sessions", []))
    new_lines = 0
    files = sorted(PROJECTS_DIR.glob("*/*.jsonl"))
    fstate = state.setdefault("files", {})
    for f in files:
        key = str(f)
        try:
            size = f.stat().st_size
        except OSError:
            continue
        st = fstate.get(key, {})
        # jsonl 只追加不改写 → 用 size 判断续读点(mtime 每次追加都变, 不能作依据);
        # size < offset 说明文件被重写, 从 0 重读
        offset = st.get("offset", 0) if st.get("offset", 0) <= size else 0
        s = sessions[f.stem]
        if st.get("title"):
            s["title"] = st["title"]  # 增量时标题在 offset 之前, 从状态恢复
        with open(f, encoding="utf-8", errors="replace") as fh:
            fh.seek(offset)
            while True:
                line = fh.readline()
                if not line:
                    break
                new_lines += 1
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                m = d.get("message") or {}
                if m.get("role") == "user" and not s["title"]:
                    txt = user_text(m.get("content")).strip()
                    if txt and not txt.startswith("<"):
                        s["title"] = re.sub(r"\s+", " ", txt)[:TITLE_LEN]
                if d.get("isSidechain"):
                    continue  # 子代理行无 usage, 不独立计费
                u = m.get("usage")
                if m.get("role") != "assistant" or not u or m.get("model") == "<synthetic>":
                    continue
                i = u.get("input_tokens") or 0
                o = u.get("output_tokens") or 0
                cr = u.get("cache_read_input_tokens") or 0
                cc = u.get("cache_creation_input_tokens") or 0
                if i + o + cr + cc == 0:
                    continue
                tok = i + o + cr + cc
                s["total"] += tok
                v = s["models"][m.get("model") or "unknown"]
                v[0] += i; v[1] += o; v[2] += cr; v[3] += cc
                day = bj_date(d.get("timestamp") or "")
                if day:
                    if not s["first"] or day < s["first"]:
                        s["first"] = day
                    if not s["last"] or day > s["last"]:
                        s["last"] = day
                    dd = days[day]
                    dd["total"] += tok
                    dd["input"] += i
                    dd["output"] += o
                    dd["cache_read"] += cr
                    dd["cache_creation"] += cc
                    dd["by_model"][m.get("model") or "unknown"] += tok
                    md = dd["model_detail"][m.get("model") or "unknown"]
                    md[0] += i; md[1] += o; md[2] += cr; md[3] += cc
                    dd["sessions"].add(d.get("sessionId") or f.stem)
                s["cwd"] = s["cwd"] or d.get("cwd") or ""
            fstate[key] = {"offset": fh.tell(), "title": s["title"]}
    # 状态回存: 会话累计 + 日累计(序列化 set)
    def sess_dump(s):
        return {"title": s["title"], "cwd": s["cwd"], "first": s["first"],
                "last": s["last"], "total": s["total"],
                "models": {m: list(v) for m, v in s["models"].items()}}
    def day_dump(d):
        return {"total": d["total"], "input": d["input"], "output": d["output"],
                "cache_read": d["cache_read"], "cache_creation": d["cache_creation"],
                "by_model": dict(d["by_model"]),
                "model_detail": {m: list(v) for m, v in d["model_detail"].items()},
                "sessions": sorted(d["sessions"])}
    state["sessions"] = {sid: sess_dump(s) for sid, s in sessions.items() if s["total"] > 0}
    state["days"] = {day: day_dump(d) for day, d in days.items()}
    if not full:
        save_state(state)

    # ---- 模型 / 项目 聚合 ----
    models = defaultdict(lambda: [0, 0, 0, 0])
    projects = defaultdict(lambda: {"total": 0, "sessions": set(),
                                    "model_detail": defaultdict(lambda: [0, 0, 0, 0])})
    for sid, s in sessions.items():
        if s["total"] <= 0:
            continue
        pl = project_label(s["cwd"])
        projects[pl]["total"] += s["total"]
        projects[pl]["sessions"].add(sid)
        for m, v in s["models"].items():
            for k in range(4):
                models[m][k] += v[k]
                projects[pl]["model_detail"][m][k] += v[k]

    # ---- 组装输出 ----
    total_tok = sum(v[0] + v[1] + v[2] + v[3] for v in models.values())
    total_in = sum(v[0] for v in models.values())
    total_out = sum(v[1] for v in models.values())
    total_cr = sum(v[2] for v in models.values())
    sess_list = [{"id": sid, "t": s["title"] or "(无标题)", "p": project_label(s["cwd"]),
                  "d": s["first"], "d2": s["last"], "tok": s["total"],
                  "models": {m: {"i": v[0], "o": v[1], "cr": v[2], "cc": v[3]}
                             for m, v in s["models"].items()}}
                 for sid, s in sessions.items() if s["total"] > 0]
    sess_list.sort(key=lambda x: -x["tok"])
    day_list = [{"d": k, **{kk: vv for kk, vv in v.items()
                            if kk not in ("by_model", "sessions", "model_detail")},
                 "by_model": dict(v["by_model"]),
                 "model_detail": {m: list(mv) for m, mv in v["model_detail"].items()},
                 "sessions": len(v["sessions"])}
                for k, v in sorted(days.items())]
    model_list = [{"m": k, "i": v[0], "o": v[1], "cr": v[2], "cc": v[3],
                   "tok": v[0] + v[1] + v[2] + v[3]} for k, v in models.items()]
    model_list.sort(key=lambda x: -x["tok"])
    proj_list = [{"p": k, "tok": v["total"], "sessions": len(v["sessions"]),
                  "model_detail": {m: list(mv) for m, mv in v["model_detail"].items()}}
                 for k, v in projects.items()]
    proj_list.sort(key=lambda x: -x["tok"])

    data = {
        "built": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "totals": {"tok": total_tok, "in": total_in, "out": total_out,
                   "cr": total_cr, "sessions": len(sess_list),
                   "days": len(day_list)},
        "days": day_list,
        "models": model_list,
        "projects": proj_list,
        "sessions": sess_list[:TOP_SESSIONS],
    }
    scan_sec = (datetime.now() - t0).total_seconds()
    print(f"[usage] {len(sessions)} 个会话, {len(day_list)} 个活跃日, "
          f"累计 {total_tok:,} token (新增扫描 {new_lines} 行, 耗时 {scan_sec:.1f}s)")
    if dry:
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    OUT.write_text(PAGE_TEMPLATE.replace("/*__USAGE_DATA__*/", payload),
                   encoding="utf-8")
    print(f"[ok] {OUT.relative_to(SITE)} 已更新 ({OUT.stat().st_size // 1024} KB)")


# ================= 页面模板(CRM 同级密码门, 数据注入 __USAGE_DATA__) =================
PAGE_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex,nofollow">
<title>Token 用量展板 · EVERSTEAD</title>
<style>
:root{
  --bg:#03060c;
  --panel:rgba(10,20,38,.55);
  --line:rgba(56,189,248,.16);
  --line-strong:rgba(56,189,248,.45);
  --cyan:#22d3ee; --blue:#3b82f6; --violet:#8b5cf6;
  --green:#34d399; --orange:#fb923c; --rose:#f43f5e;
  --text:#e2ecf7; --muted:#7d92ad;
  --glow:0 0 24px rgba(34,211,238,.25);
  --mono:'JetBrains Mono','Cascadia Mono','Consolas','Courier New',ui-monospace,monospace;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Microsoft YaHei','PingFang SC','Helvetica Neue',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden;-webkit-font-smoothing:antialiased}
a{text-decoration:none;color:inherit}
.bg-grid{position:fixed;inset:0;z-index:0;pointer-events:none;
  background:radial-gradient(1100px 600px at 75% -10%,rgba(59,130,246,.16),transparent 60%),
    radial-gradient(900px 500px at -10% 110%,rgba(139,92,246,.12),transparent 60%),
    linear-gradient(rgba(56,189,248,.045) 1px,transparent 1px),
    linear-gradient(90deg,rgba(56,189,248,.045) 1px,transparent 1px),var(--bg);
  background-size:auto,auto,44px 44px,44px 44px,auto;
  mask-image:radial-gradient(ellipse 120% 90% at 50% 0%,#000 55%,transparent 100%);
  -webkit-mask-image:radial-gradient(ellipse 120% 90% at 50% 0%,#000 55%,transparent 100%)}
.wrap{position:relative;z-index:3;max-width:1240px;margin:0 auto;padding:0 24px 56px}
.topbar{display:flex;align-items:center;gap:14px;padding:22px 0 16px}
.topbar .logo{width:40px;height:40px;border-radius:10px;flex-shrink:0;background:linear-gradient(135deg,var(--cyan),var(--violet));display:flex;align-items:center;justify-content:center;font-weight:800;font-size:19px;color:#03101f;box-shadow:var(--glow);font-family:var(--mono)}
.topbar .brand{font-family:var(--mono);font-weight:700;letter-spacing:.28em;font-size:15px}
.topbar .brand em{font-style:normal;background:linear-gradient(90deg,var(--cyan),var(--blue),var(--violet));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.topbar .back{margin-left:auto;font-family:var(--mono);font-size:11px;letter-spacing:.14em;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:6px 14px;background:rgba(10,20,38,.4);transition:border-color .25s,color .25s}
.topbar .back:hover{border-color:var(--line-strong);color:var(--cyan)}
.sub{font-family:var(--mono);font-size:12px;color:var(--muted);letter-spacing:.08em;padding:0 0 18px}

.gate{position:fixed;inset:0;z-index:99;display:flex;align-items:center;justify-content:center;background:rgba(3,6,12,.92);backdrop-filter:blur(10px)}
.gate-panel{background:var(--panel);border:1px solid var(--line-strong);border-radius:16px;padding:36px 40px;text-align:center;box-shadow:var(--glow);min-width:320px}
.g-ico{font-size:34px}
.gate h2{font-size:18px;margin-top:10px;letter-spacing:.06em}
.gate p{font-size:12px;color:var(--muted);margin-top:6px;font-family:var(--mono)}
.gate input{margin-top:20px;width:100%;background:rgba(5,12,25,.9);border:1px solid var(--line-strong);border-radius:8px;padding:10px 14px;color:var(--text);font-size:14px;outline:none;text-align:center;letter-spacing:.3em}
.gate input:focus{border-color:var(--cyan);box-shadow:var(--glow)}
.gate button{margin-top:12px;width:100%;background:linear-gradient(135deg,var(--cyan),var(--blue));border:none;border-radius:8px;padding:10px;font-weight:700;color:#03101f;cursor:pointer;font-size:14px;letter-spacing:.3em}
.gate button:hover{filter:brightness(1.15)}
.gate.err .gate-panel{animation:shake .4s}
@keyframes shake{0%,100%{transform:translateX(0)}25%{transform:translateX(-8px)}75%{transform:translateX(8px)}}

.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;backdrop-filter:blur(6px)}
.stat .k{font-size:11px;color:var(--muted);letter-spacing:.12em;font-family:var(--mono)}
.stat .v{font-size:21px;font-weight:700;margin-top:5px;font-family:var(--mono);color:var(--cyan)}
.stat .v small{font-size:11px;font-weight:400;color:var(--muted);margin-left:2px}
.chart-wrap{position:relative}
.tooltip{position:fixed;z-index:9999;pointer-events:none;background:rgba(5,12,25,.97);
  border:1px solid var(--line-strong);border-radius:10px;padding:10px 12px;
  font-family:var(--mono);font-size:11px;line-height:1.75;box-shadow:var(--glow);
  min-width:200px;display:none}
.tooltip .tt-h{color:var(--cyan);font-weight:700;font-size:12px;margin-bottom:4px}
.tooltip .tt-r{display:flex;align-items:center;gap:6px;color:var(--muted)}
.tooltip .tt-r .dot{width:7px;height:7px;border-radius:2px;flex-shrink:0}
.tooltip .tt-r b{margin-left:auto;color:var(--text);font-weight:600}
.tooltip .tt-t{border-top:1px solid var(--line);margin-top:6px;padding-top:6px;color:var(--text)}
.pr-dialog{position:fixed;inset:0;z-index:9998;background:rgba(3,6,12,.8);
  display:none;align-items:center;justify-content:center;backdrop-filter:blur(6px)}
.pr-dialog.show{display:flex}
.pr-panel{background:var(--panel);border:1px solid var(--line-strong);border-radius:16px;
  padding:22px 26px;box-shadow:var(--glow);width:min(560px,92vw);max-height:86vh;overflow-y:auto}
.pr-panel h3{font-size:15px;margin-bottom:4px}
.pr-sub{font-size:11px;color:var(--muted);font-family:var(--mono);margin-bottom:14px;line-height:1.7}
.pr-grid{display:grid;grid-template-columns:auto 1fr 1fr 1fr 1fr;gap:8px 10px;
  align-items:center;margin-bottom:16px;font-size:12px}
.pr-grid .ph{font-family:var(--mono);font-size:10px;color:var(--muted);letter-spacing:.06em}
.pr-grid .pm{font-family:var(--mono);color:var(--text);font-size:11.5px;white-space:nowrap}
.pr-grid input{background:rgba(5,12,25,.9);border:1px solid var(--line);border-radius:6px;
  padding:6px 8px;color:var(--text);font-family:var(--mono);font-size:12px;width:100%;outline:none}
.pr-grid input:focus{border-color:var(--cyan)}
.pr-btns{display:flex;gap:10px;justify-content:flex-end}
.pr-btns button{border-radius:8px;padding:8px 18px;font-size:13px;cursor:pointer;font-weight:700}
.pr-save{background:linear-gradient(135deg,var(--cyan),var(--blue));border:none;color:#03101f}
.pr-reset{background:transparent;border:1px solid var(--line-strong);color:var(--muted)}
.pr-cancel{background:transparent;border:1px solid var(--line);color:var(--muted)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px 20px;margin-bottom:16px;backdrop-filter:blur(6px)}
.card-head{display:flex;align-items:center;gap:10px;margin-bottom:14px}
.card-head h2{font-size:14px;letter-spacing:.1em}
.card-head .en{font-family:var(--mono);font-size:10px;color:var(--muted);letter-spacing:.2em}
.card-head .right{margin-left:auto;display:flex;gap:8px}
.tog{border:1px solid var(--line);background:rgba(10,20,38,.4);color:var(--muted);font-family:var(--mono);font-size:11px;border-radius:999px;padding:4px 12px;cursor:pointer;letter-spacing:.1em}
.tog.on{border-color:var(--cyan);color:var(--cyan)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}
@media (max-width:900px){.grid2{grid-template-columns:1fr}.stats{grid-template-columns:repeat(3,1fr)}}
svg text{font-family:var(--mono);font-size:10px;fill:var(--muted)}
.legend{display:flex;flex-wrap:wrap;gap:8px 18px;margin-top:10px}
.lg{font-size:12px;color:var(--muted);display:flex;align-items:center;gap:6px}
.lg .dot{width:9px;height:9px;border-radius:3px;flex-shrink:0}
.lg b{color:var(--text);font-family:var(--mono);font-weight:600}
.mbar{display:flex;height:26px;border-radius:8px;overflow:hidden;margin-bottom:12px}
.mbar div{height:100%;transition:filter .2s}
.mbar div:hover{filter:brightness(1.25)}
.mrow{display:flex;align-items:center;gap:10px;margin-bottom:9px;font-size:12px}
.mrow .mlab{width:130px;flex-shrink:0;color:var(--text);font-family:var(--mono)}
.mrow .mtrack{flex:1;height:14px;background:rgba(56,189,248,.08);border-radius:999px;overflow:hidden}
.mrow .mfill{height:100%;border-radius:999px;background:linear-gradient(90deg,var(--cyan),var(--blue))}
.mrow .mval{width:170px;flex-shrink:0;text-align:right;color:var(--muted);font-family:var(--mono)}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th{font-family:var(--mono);font-size:10.5px;color:var(--muted);letter-spacing:.12em;text-align:left;padding:8px 10px;border-bottom:1px solid var(--line-strong);white-space:nowrap}
td{padding:9px 10px;border-bottom:1px solid var(--line);color:var(--text)}
td.mono{font-family:var(--mono);color:var(--cyan);text-align:right;white-space:nowrap}
td.dim{color:var(--muted);font-family:var(--mono);font-size:11px;white-space:nowrap}
td .mtag{display:inline-block;border:1px solid var(--line-strong);border-radius:999px;padding:1px 8px;font-size:10px;font-family:var(--mono);color:var(--cyan);margin:1px 3px 1px 0}
tr:hover td{background:rgba(34,211,238,.04)}
.foot{margin-top:18px;font-family:var(--mono);font-size:11px;color:var(--muted);letter-spacing:.06em;line-height:1.9}
</style>
</head>
<body>
<div class="bg-grid"></div>

<div class="gate" id="gate">
  <div class="gate-panel">
    <div class="g-ico">🔒</div>
    <h2>Token 用量展板</h2>
    <p>铁蛋 AI 用量统计 · 密码访问</p>
    <input type="password" id="pw" placeholder="请输入访问密码" autocomplete="off">
    <button id="btn">解 锁</button>
  </div>
</div>

<div class="wrap">
  <div class="topbar">
    <div class="logo">E</div>
    <div class="brand">EVERSTEAD <em>TOKEN BOARD</em></div>
    <a class="back" href="../../tools.html">← 工具箱</a>
  </div>
  <div class="sub">TOKEN USAGE DASHBOARD · 铁蛋会话用量全景 · 数据源 ~/.claude/projects 会话转录 · 北京时间</div>

  <div class="stats" id="stats"></div>

  <div class="card">
    <div class="card-head">
      <h2>每日用量趋势</h2><div class="en">DAILY TREND</div>
      <div class="right">
        <button class="tog on" id="tog30" type="button">近 30 天</button>
        <button class="tog" id="tog90" type="button">近 90 天</button>
      </div>
    </div>
    <div class="chart-wrap"><div id="chart"></div></div>
    <div class="legend" id="chartLegend"></div>
  </div>

  <div class="grid2">
    <div class="card">
      <div class="card-head"><h2>按模型分拆</h2><div class="en">BY MODEL</div></div>
      <div class="mbar" id="mbar"></div>
      <div id="mrows"></div>
    </div>
    <div class="card">
      <div class="card-head"><h2>按项目分拆</h2><div class="en">BY PROJECT</div></div>
      <div id="prows"></div>
    </div>
  </div>

  <div class="card">
    <div class="card-head"><h2>会话明细 TOP 30</h2><div class="en">SESSION LEADERBOARD</div></div>
    <div style="overflow-x:auto">
    <table>
      <thead><tr><th>#</th><th>会话标题</th><th>活跃日期</th><th>项目</th><th>模型</th><th style="text-align:right">TOKENS</th></tr></thead>
      <tbody id="sessBody"></tbody>
    </table>
    </div>
  </div>

  <div class="foot" id="foot"></div>
</div>

<script>
var PASSWORD_HASH = "62030069b40c02d1dd642d438194850f14d9e79a25abd1e53c02f7391f8242c8";
var GATE_KEY = 'cp_token_usage_ok';
function sha256(ascii){function rightRotate(value,amount){return(value>>>amount)|(value<<(32-amount))}
var mathPow=Math.pow,maxWord=mathPow(2,32),result='',words=[],asciiBitLength=ascii.length*8,hash=sha256.h=sha256.h||[],k=sha256.k=sha256.k||[],primeCounter=k.length,isComposite={};
for(var candidate=2;primeCounter<64;candidate++){if(!isComposite[candidate]){for(var i=0;i<313;i+=candidate)isComposite[i]=candidate;hash[primeCounter]=(mathPow(candidate,.5)*maxWord)|0;k[primeCounter++]=(mathPow(candidate,1/3)*maxWord)|0}}
ascii+='\x80';while(ascii.length%64-56)ascii+='\x00';
for(var i=0;i<ascii.length;i++){var j=ascii.charCodeAt(i);if(j>>8)return'';words[i>>2]|=j<<((3-i)%4)*8}
words[words.length]=((asciiBitLength/maxWord)|0);words[words.length]=(asciiBitLength);
for(var j=0;j<words.length;){var w=words.slice(j,j+=16),oldHash=hash;hash=hash.slice(0,8);
for(var i=0;i<64;i++){var w15=w[i-15],w2=w[i-2],a=hash[0],e=hash[4];
var temp1=hash[7]+(rightRotate(e,6)^rightRotate(e,11)^rightRotate(e,25))+((e&hash[5])^((~e)&hash[6]))+k[i]+(w[i]=(i<16)?w[i]:(w[i-16]+(rightRotate(w15,7)^rightRotate(w15,18)^(w15>>>3))+w[i-7]+(rightRotate(w2,17)^rightRotate(w2,19)^(w2>>>10)))|0);
var temp2=(rightRotate(a,2)^rightRotate(a,13)^rightRotate(a,22))+((a&hash[1])^(a&hash[2])^(hash[1]&hash[2]));
hash=[(temp1+temp2)|0].concat(hash);hash[4]=(hash[4]+temp1)|0}
for(var i=0;i<8;i++)hash[i]=(hash[i]+oldHash[i])|0}
for(var i=0;i<8;i++){for(var j=3;j+1;j--){var b=(hash[i]>>(j*8))&255;result+=((b<16)?0:'')+b.toString(16)}}
return result}
function unlock(){var gate=document.getElementById('gate'),input=document.getElementById('pw');
if(sha256(input.value)===PASSWORD_HASH){sessionStorage.setItem(GATE_KEY,'1');gate.style.display='none'}
else{gate.classList.remove('err');void gate.offsetWidth;gate.classList.add('err');input.value='';input.focus()}}
document.getElementById('btn').addEventListener('click',unlock);
document.getElementById('pw').addEventListener('keydown',function(e){if(e.key==='Enter')unlock()});
if(sessionStorage.getItem(GATE_KEY)==='1'){document.getElementById('gate').style.display='none'}

/* ================= 成本模型(2026-09-14, 页内可调, 存 localStorage) =================
   单价: 元/百万 tokens。默认取 DeepSeek V4 峰谷定价闲时档(第三方报道口径);
   老板有真实账单时点「⚙ 价格校准」改数字, 全页立即重算。 */
var DEFAULT_PRICES = {
  'deepseek-v4-pro':   {h: 0.15, m: 4.5,  o: 13.5, w: 1.5},
  'deepseek-v4-flash': {h: 0.05, m: 1.5,  o: 4.5,  w: 1.5},
  'deepseek-flash':    {h: 0.05, m: 1.5,  o: 4.5,  w: 1.5},
  'unknown':           {h: 0.05, m: 1.5,  o: 4.5,  w: 1.5}
};  /* h=缓存命中 m=缓存未命中 o=输出 w=缓存写(按未命中计, 无独立官价) */
function getPrices(){
  try{return JSON.parse(localStorage.getItem('tok_prices')||'null')||DEFAULT_PRICES}
  catch(e){return DEFAULT_PRICES}
}
function costOfModel(m, i, o, cr, cc){
  var p=getPrices()[m]||DEFAULT_PRICES['unknown'];
  /* 缓存读按命中价; 缓存写并入输入未命中价(DeepSeek 无独立 cache write 定价) */
  return (cr/1e6*p.h + (i+cc)/1e6*p.m + o/1e6*p.o);
}
function modelTotals(it){  /* it = {models:{m:{i,o,cr,cc}}} → {cost, costPerModel:{m:¥}} */
  var cost=0, per={};
  Object.keys(it.models||{}).forEach(function(m){
    var v=it.models[m]; var c=costOfModel(m,v.i,v.o,v.cr,v.cc);
    cost+=c; per[m]=c;
  });
  return {cost:cost, per:per};
}
function cnY(v){
  if(v>=1e4)return (v/1e4).toFixed(2)+' 万';
  return v>=100?Math.round(v)+' 元':(v>=1? v.toFixed(1)+' 元': v.toFixed(2)+' 元');
}

/* ================= 数据渲染 ================= */
var U = /*__USAGE_DATA__*/;
var PAL = ['#22d3ee','#8b5cf6','#34d399','#fb923c','#f43f5e','#3b82f6'];
function hm(n){
  if(n>=1e8)return (n/1e8).toFixed(2)+' 亿';
  if(n>=1e4)return (n/1e4).toFixed(1)+' 万';
  if(n>=1e3)return (n/1e3).toFixed(1)+' K';
  return String(n);
}
function el(tag,cls,html){var e=document.createElement(tag);if(cls)e.className=cls;if(html!=null)e.innerHTML=html;return e}

/* KPI(成本按当前价格模型实时计算) */
(function(){
  var T=U.totals;
  var today=U.days.length?U.days[U.days.length-1]:null;
  var avg=U.days.length?Math.round(T.tok/U.days.length):0;
  var cacheRate=T.cr/(T.cr+T.in)*100;
  var totCost=U.models.reduce(function(a,m){return a+costOfModel(m.m,m.i,m.o,m.cr,m.cc)},0);
  /* 今日成本: 用今日逐模型明细精确计算(数据侧已给 i/o/cr/cc) */
  var todayCost=0;
  if(today){
    Object.keys(today.model_detail||{}).forEach(function(m){
      var v=today.model_detail[m];
      todayCost+=costOfModel(m,v[0],v[1],v[2],v[3]);
    });
  }
  var avgCost=U.days.length?totCost/U.days.length:0;
  var cards=[
    ['累计 TOKEN', hm(T.tok)],
    ['累计成本', '¥ '+cnY(totCost)],
    ['今日 TOKEN', hm(today?today.total:0)],
    ['今日成本', '¥ '+cnY(todayCost)],
    ['会话数', T.sessions+' 次'],
    ['缓存命中率', cacheRate.toFixed(1)+'%'],
    ['日均 TOKEN', hm(avg)],
    ['日均成本', '¥ '+cnY(avgCost)]
  ];
  var box=document.getElementById('stats');
  box.innerHTML='';
  cards.forEach(function(c){
    var s=el('div','stat');
    s.appendChild(el('div','k',c[0]));
    s.appendChild(el('div','v',c[1]));
    box.appendChild(s);
  });
  var pr=el('button','tog');
  pr.style.cssText='margin-top:10px;font-size:11px';
  pr.textContent='⚙ 价格校准';
  pr.addEventListener('click',showPriceDialog);
  box.parentElement.insertBefore(pr, box.nextSibling);
})();

/* 每日趋势: 面积图 + 自绘即时 tooltip(mousemove 驱动, 无 SVG title 延迟) */
var CHART_N=30;
var TT=null;  /* tooltip 单例 */
function tipEl(){
  if(TT)return TT;
  TT=document.createElement('div');TT.className='tooltip';
  document.body.appendChild(TT);
  return TT;
}
function showTip(ev,day,models){
  var t=tipEl();
  var rows='';
  models.forEach(function(m,i){
    rows+='<div class="tt-r"><span class="dot" style="background:'+PAL[i%PAL.length]+'"></span>'
      +m.name+'<b>'+hm(m.val)+'</b></div>';
  });
  var cost=0;
  var md=day.model_detail||{};
  Object.keys(md).forEach(function(m){var v=md[m];cost+=costOfModel(m,v[0],v[1],v[2],v[3])});
  t.innerHTML='<div class="tt-h">'+day.d+'</div>'+rows
    +'<div class="tt-t">'+hm(day.total)+' token · <span style="color:#fbbf24">¥ '+cnY(cost)+'</span>'
    +(day.sessions?' · '+day.sessions+' 会话':'')+'</div>';
  t.style.display='block';
  var W=window.innerWidth, mw=t.offsetWidth, mh=t.offsetHeight;
  var px=ev.clientX+14, py=ev.clientY-10;
  if(px+mw>W-8)px=ev.clientX-mw-14;
  if(py+mh>window.innerHeight-8)py=window.innerHeight-mh-8;
  t.style.left=px+'px';t.style.top=py+'px';
}
function hideTip(){if(TT)TT.style.display='none'}
function drawChart(){
  var box=document.getElementById('chart');
  box.innerHTML='';
  var days=U.days.slice(-CHART_N);
  if(!days.length){box.innerHTML='<div style="color:var(--muted);font-size:12px">暂无数据</div>';return}
  var W=1000,H=240,padL=56,padR=12,padT=14,padB=26;
  var v=days.map(function(d){return d.total});
  var mx=Math.max.apply(null,v)*1.1;
  var iw=W-padL-padR, ih=H-padT-padB;
  var step=iw/Math.max(1,days.length-1);
  function x(i){return padL+i*step}
  function y(val){return padT+ih*(1-val/mx)}
  var path='M'+x(0).toFixed(1)+','+y(v[0]).toFixed(1);
  for(var i=1;i<days.length;i++)path+=' L'+x(i).toFixed(1)+','+y(v[i]).toFixed(1);
  var area=path+' L'+x(days.length-1).toFixed(1)+','+(padT+ih)+' L'+x(0).toFixed(1)+','+(padT+ih)+' Z';
  var ticks=3;
  var svg='<svg viewBox="0 0 '+W+' '+H+'" style="width:100%;height:auto;display:block">'
    +'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
    +'<stop offset="0" stop-color="#22d3ee" stop-opacity=".35"/>'
    +'<stop offset="1" stop-color="#22d3ee" stop-opacity="0"/></linearGradient></defs>';
  for(var t=0;t<=ticks;t++){
    var yy=padT+ih*t/ticks, val=mx*(1-t/ticks);
    svg+='<line x1="'+padL+'" y1="'+yy+'" x2="'+(W-padR)+'" y2="'+yy+'" stroke="rgba(56,189,248,.12)"/>'
      +'<text x="'+(padL-6)+'" y="'+(yy+3)+'" text-anchor="end">'+hm(val)+'</text>';
  }
  var labelStep=Math.ceil(days.length/6);
  days.forEach(function(d,i){
    if(i%labelStep===0||i===days.length-1){
      svg+='<text x="'+x(i)+'" y="'+(H-8)+'" text-anchor="middle">'+d.d.slice(5)+'</text>';
    }
  });
  svg+='<path d="'+area+'" fill="url(#g)"/>'
    +'<path d="'+path+'" fill="none" stroke="#22d3ee" stroke-width="2" stroke-linejoin="round"/>'
    +'<rect class="hover-zone" x="0" y="0" width="'+W+'" height="'+H+'" fill="transparent"/>';
  days.forEach(function(d,i){
    svg+='<circle class="pt" data-i="'+i+'" cx="'+x(i).toFixed(1)+'" cy="'+y(d.total).toFixed(1)+'" r="3.4" fill="#22d3ee" opacity="0"/>';
  });
  svg+='</svg>';
  box.innerHTML=svg;
  /* mousemove: 按 SVG 坐标系换算最近数据点 → 高亮 + 即时 tooltip */
  var svgEl=box.querySelector('svg');
  var pts=box.querySelectorAll('.pt');
  svgEl.addEventListener('mousemove',function(ev){
    var r=svgEl.getBoundingClientRect();
    var sx=(ev.clientX-r.left)/r.width*W;
    var i=Math.max(0,Math.min(days.length-1,Math.round((sx-padL)/step)));
    pts.forEach(function(p){p.setAttribute('opacity',p.getAttribute('data-i')==i?'1':'0')});
    var byModel=days[i].by_model||{};
    var ms=Object.keys(byModel).map(function(m){
      return {name:m.replace(/^deepseek-/,'DS '),val:byModel[m]};
    }).sort(function(a,b){return b.val-a.val});
    showTip(ev,days[i],ms);
  });
  svgEl.addEventListener('mouseleave',function(){
    hideTip();
    pts.forEach(function(p){p.setAttribute('opacity','0')});
  });
  var lg=document.getElementById('chartLegend');
  lg.innerHTML='<div class="lg"><span class="dot" style="background:#22d3ee"></span><b>'+hm(v.reduce(function(a,b){return a+b},0))+'</b> 近 '+CHART_N+' 天合计</div>'
    +'<div class="lg"><span class="dot" style="background:rgba(34,211,238,.35)"></span>峰值 '+hm(mx/1.1)+' / 天</div>'
    +'<div class="lg"><span class="dot" style="background:var(--muted)"></span>输入 '+hm(U.totals.in)+' · 输出 '+hm(U.totals.out)+' · 缓存读 '+hm(U.totals.cr)+'</div>';
}
document.getElementById('tog30').addEventListener('click',function(){CHART_N=30;this.classList.add('on');document.getElementById('tog90').classList.remove('on');drawChart()});
document.getElementById('tog90').addEventListener('click',function(){CHART_N=90;this.classList.add('on');document.getElementById('tog30').classList.remove('on');drawChart()});

/* 模型分拆(成本随价格实时计算) */
function renderModels(){
  var ms=U.models, tot=U.totals.tok;
  var bar=document.getElementById('mbar'), rows=document.getElementById('mrows');
  bar.innerHTML='';rows.innerHTML='';
  ms.forEach(function(m,i){
    var seg=el('div');seg.style.width=(m.tok/tot*100).toFixed(2)+'%';
    seg.style.background=PAL[i%PAL.length];
    seg.title=m.m+' · '+hm(m.tok);
    bar.appendChild(seg);
  });
  ms.forEach(function(m,i){
    var r=el('div','mrow');
    r.appendChild(el('div','mlab',m.m.replace(/^deepseek-/,'DS ')));
    var track=el('div','mtrack');
    track.appendChild((function(){var f=el('div','mfill');f.style.width=(m.tok/tot*100).toFixed(1)+'%';f.style.background=PAL[i%PAL.length];return f})());
    r.appendChild(track);
    var cost=costOfModel(m.m,m.i,m.o,m.cr,m.cc);
    r.appendChild(el('div','mval',hm(m.tok)+' · ¥ '+cnY(cost)+' · '+(m.tok/tot*100).toFixed(1)+'%'));
    rows.appendChild(r);
  });
}
renderModels();

/* 项目分拆(成本随价格实时计算) */
function renderProjects(){
  var ps=U.projects, mx=Math.max.apply(null,ps.map(function(p){return p.tok}));
  var rows=document.getElementById('prows');
  rows.innerHTML='';
  ps.forEach(function(p){
    var cost=0;
    Object.keys(p.model_detail||{}).forEach(function(m){
      var v=p.model_detail[m];cost+=costOfModel(m,v[0],v[1],v[2],v[3]);
    });
    var r=el('div','mrow');
    r.appendChild(el('div','mlab',p.p));
    var track=el('div','mtrack');
    track.appendChild((function(){var f=el('div','mfill');f.style.width=(p.tok/mx*100).toFixed(1)+'%';return f})());
    r.appendChild(track);
    r.appendChild(el('div','mval',hm(p.tok)+' · ¥ '+cnY(cost)+' · '+p.sessions+' 次会话'));
    rows.appendChild(r);
  });
}
renderProjects();

/* 会话明细(成本随价格实时计算) */
function renderSessions(){
  var tb=document.getElementById('sessBody');
  tb.innerHTML='';
  U.sessions.forEach(function(s,i){
    var cost=0;
    Object.keys(s.models||{}).forEach(function(m){
      var v=s.models[m];cost+=costOfModel(m,v.i,v.o,v.cr,v.cc);
    });
    var tr=el('tr');
    tr.appendChild(el('td','dim','#'+(i+1)));
    tr.appendChild(el('td',null,s.t));
    tr.appendChild(el('td','dim',s.d+(s.d2&&s.d2!==s.d?' ~ '+s.d2.slice(5):'')));
    tr.appendChild(el('td',null,s.p));
    var mc=el('td');
    Object.keys(s.models||{}).forEach(function(m){mc.appendChild(el('span','mtag',m.replace(/^deepseek-/,'DS ')))});
    tr.appendChild(mc);
    tr.appendChild(el('td','mono',hm(s.tok)+' <span style="color:#fbbf24;font-size:11px">¥ '+cnY(cost)+'</span>'));
    tb.appendChild(tr);
  });
}
renderSessions();

document.getElementById('foot').innerHTML =
  '构建时间 '+U.built+' · 统计口径: 主会话 assistant 消息 usage 求和(输入/输出/缓存读写全计入) · 子代理(sidechain)不计 · 令牌数源自会话转录逐字累加<br>'
  +'数据每日 18:07 自动刷新 · 🔒 本页与 CRM 同级密码门 · 不进入公开搜索索引 · '
  +'成本单价为 DeepSeek V4 峰谷闲时档(第三方报道口径, 点击「⚙ 价格校准」可改)';
drawChart();

/* ================= 价格校准弹窗 ================= */
function showPriceDialog(){
  var prices=getPrices();
  var dlg=document.getElementById('prDialog');
  if(!dlg){
    dlg=el('div','pr-dialog');dlg.id='prDialog';
    var panel=el('div','pr-panel');
    panel.appendChild(el('h3',null,'⚙ 价格校准'));
    panel.appendChild(el('div','pr-sub',
      '单价: 元 / 百万 tokens。默认 DeepSeek V4 峰谷闲时档(第三方报道口径);<br>'
      +'h=缓存命中 m=缓存未命中 o=输出 w=缓存写(无独立官价, 默认按未命中计)。<br>'
      +'改完保存立即全页重算, 存在浏览器本地。'));
    var grid=el('div','pr-grid');
    ['模型','h','m','o','w'].forEach(function(h){
      grid.appendChild(el('div','ph',h));
    });
    var inputs={};
    Object.keys(DEFAULT_PRICES).forEach(function(m){
      grid.appendChild(el('div','pm',m.replace(/^deepseek-/,'DS ')));
      ['h','m','o','w'].forEach(function(f){
        var inp=document.createElement('input');inp.type='number';inp.step='0.01';inp.min='0';
        inp.value=prices[m]?prices[m][f]:DEFAULT_PRICES[m][f];
        grid.appendChild(inp);
        inputs[m+'|'+f]=inp;
      });
    });
    panel.appendChild(grid);
    var btns=el('div','pr-btns');
    var bSave=el('button','pr-save','保存');var bReset=el('button','pr-reset','恢复默认');var bCancel=el('button','pr-cancel','取消');
    bSave.addEventListener('click',function(){
      var p={};
      Object.keys(DEFAULT_PRICES).forEach(function(m){
        p[m]={};
        ['h','m','o','w'].forEach(function(f){
          var v=parseFloat(inputs[m+'|'+f].value);
          p[m][f]=isFinite(v)?v:DEFAULT_PRICES[m][f];
        });
      });
      localStorage.setItem('tok_prices',JSON.stringify(p));
      dlg.classList.remove('show');
      rerenderAll();
    });
    bReset.addEventListener('click',function(){
      localStorage.removeItem('tok_prices');
      dlg.classList.remove('show');
      rerenderAll();
    });
    bCancel.addEventListener('click',function(){dlg.classList.remove('show')});
    btns.appendChild(bSave);btns.appendChild(bReset);btns.appendChild(bCancel);
    panel.appendChild(btns);
    dlg.appendChild(panel);
    dlg.addEventListener('click',function(e){if(e.target===dlg)dlg.classList.remove('show')});
    document.body.appendChild(dlg);
  }else{
    /* 刷新输入框为当前价格 */
    var prices2=getPrices();
    var inputs2=dlg.querySelectorAll('.pr-grid input');
    var mi=0,fj=0;
    Object.keys(DEFAULT_PRICES).forEach(function(m){
      ['h','m','o','w'].forEach(function(f){
        inputs2[mi*4+fj].value=prices2[m][f];fj++;
      });
      fj=0;mi++;
    });
  }
  dlg.classList.add('show');
}
function rerenderAll(){
  /* KPI/模型/项目/会话全部重渲染(图表 token 不受价格影响, 只需重算成本提示) */
  var T=U.totals;
  var totCost=U.models.reduce(function(a,m){return a+costOfModel(m.m,m.i,m.o,m.cr,m.cc)},0);
  var today=U.days.length?U.days[U.days.length-1]:null;
  var todayCost=0;
  if(today){
    Object.keys(today.model_detail||{}).forEach(function(m){
      var v=today.model_detail[m];todayCost+=costOfModel(m,v[0],v[1],v[2],v[3]);
    });
  }
  var avgCost=U.days.length?totCost/U.days.length:0;
  var box=document.getElementById('stats');
  box.innerHTML='';
  var cards=[
    ['累计 TOKEN', hm(T.tok)],['累计成本', '¥ '+cnY(totCost)],
    ['今日 TOKEN', hm(today?today.total:0)],['今日成本', '¥ '+cnY(todayCost)],
    ['会话数', T.sessions+' 次'],['缓存命中率', (T.cr/(T.cr+T.in)*100).toFixed(1)+'%'],
    ['日均 TOKEN', hm(Math.round(T.tok/U.days.length))],['日均成本', '¥ '+cnY(avgCost)]
  ];
  cards.forEach(function(c){
    var s=el('div','stat');
    s.appendChild(el('div','k',c[0]));
    s.appendChild(el('div','v',c[1]));
    box.appendChild(s);
  });
  renderModels();renderProjects();renderSessions();drawChart();
}
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
