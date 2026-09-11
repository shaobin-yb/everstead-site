#!/usr/bin/env python3
"""生成私人专区「讯飞本文件」板块页面。

从 doxent_summaries/ 分组归纳 + 总纪要 + 主题线生成 4 个 HTML 页面，
全部套用 private.html 同一把密码锁（同 hash + 同 sessionStorage key 'private_ok'）。
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
import publish  # 复用 publish.py 的 md_to_html

SITE = Path(__file__).parent
OUT = SITE / "knowledge" / "iflyink-notes"
SRC = Path(r"D:\cloude code")

# 分组 → 年份映射
YEAR_GROUPS = {
    2024: ["g00", "g01", "g02", "g03"],
    2025: ["g04", "g05", "g06", "g07", "g08", "g09", "g10", "g11", "g12", "g13"],
    2026: ["g14", "g15", "g16", "g17", "g18"],
}

# 与 private.html 同一把锁
GATE_CSS = """
.pvgate{
  max-width:420px;margin:30px auto 0;padding:32px 28px;text-align:center;
  border:1px solid rgba(56,189,248,.16);border-radius:14px;
  background:rgba(10,20,38,.55);backdrop-filter:blur(10px);
}
.pvgate .lock{font-size:34px;margin-bottom:10px}
.pvgate p{font-size:12px;color:#7d92ad;margin-bottom:18px;line-height:1.8}
.pvgate input{
  width:100%;padding:11px 14px;font-family:'JetBrains Mono',Consolas,monospace;
  font-size:16px;letter-spacing:.35em;text-align:center;color:#e2ecf7;
  background:rgba(3,6,12,.6);border:1px solid rgba(56,189,248,.16);
  border-radius:10px;outline:none;
}
.pvgate input:focus{border-color:rgba(56,189,248,.45);box-shadow:0 0 0 3px rgba(56,189,248,.12)}
.pvgate button{
  margin-top:14px;width:100%;padding:11px;font-size:14px;font-weight:600;letter-spacing:.2em;
  color:#03101f;cursor:pointer;background:linear-gradient(90deg,#22d3ee,#8b5cf6);
  border:none;border-radius:10px;
}
.pvgate .err-msg{display:none;margin-top:10px;font-size:12px;color:#f43f5e}
.pvgate.err .err-msg{display:block}
"""

GATE_JS = """
/* 与 private.html 同一把锁: 同 hash + 同 sessionStorage key('private_ok') */
var PASSWORD_HASH = "a68afcaa33dc88de7217371b041b422543aa16e2958365dde8112487475e37cd";
function sha256(ascii) {
  function rightRotate(value, amount) { return (value>>>amount) | (value<<(32-amount)); }
  var mathPow = Math.pow;
  var maxWord = mathPow(2, 32);
  var result = '';
  var words = [];
  var asciiBitLength = ascii.length*8;
  var hash = sha256.h = sha256.h || [];
  var k = sha256.k = sha256.k || [];
  var primeCounter = k.length;
  var isComposite = {};
  for (var candidate = 2; primeCounter < 64; candidate++) {
    if (!isComposite[candidate]) {
      for (var i = 0; i < 313; i += candidate) isComposite[i] = candidate;
      hash[primeCounter] = (mathPow(candidate, .5)*maxWord)|0;
      k[primeCounter++] = (mathPow(candidate, 1/3)*maxWord)|0;
    }
  }
  ascii += '\\x80';
  while (ascii.length%64 - 56) ascii += '\\x00';
  for (var i = 0; i < ascii.length; i++) {
    var j = ascii.charCodeAt(i);
    if (j>>8) return '';
    words[i>>2] |= j << ((3 - i)%4)*8;
  }
  words[words.length] = ((asciiBitLength/maxWord)|0);
  words[words.length] = (asciiBitLength);
  for (var j = 0; j < words.length;) {
    var w = words.slice(j, j += 16);
    var oldHash = hash;
    hash = hash.slice(0, 8);
    for (var i = 0; i < 64; i++) {
      var w15 = w[i - 15], w2 = w[i - 2];
      var a = hash[0], e = hash[4];
      var temp1 = hash[7]
        + (rightRotate(e, 6) ^ rightRotate(e, 11) ^ rightRotate(e, 25))
        + ((e&hash[5])^((~e)&hash[6]))
        + k[i]
        + (w[i] = (i < 16) ? w[i] : (
            w[i - 16]
            + (rightRotate(w15, 7) ^ rightRotate(w15, 18) ^ (w15>>>3))
            + w[i - 7]
            + (rightRotate(w2, 17) ^ rightRotate(w2, 19) ^ (w2>>>10))
          )|0
        );
      var temp2 = (rightRotate(a, 2) ^ rightRotate(a, 13) ^ rightRotate(a, 22))
        + ((a&hash[1])^(a&hash[2])^(hash[1]&hash[2]));
      hash = [(temp1 + temp2)|0].concat(hash);
      hash[4] = (hash[4] + temp1)|0;
    }
    for (var i = 0; i < 8; i++) hash[i] = (hash[i] + oldHash[i])|0;
  }
  for (var i = 0; i < 8; i++) {
    for (var j = 3; j + 1; j--) {
      var b = (hash[i]>>(j*8))&255;
      result += ((b < 16) ? 0 : '') + b.toString(16);
    }
  }
  return result;
}
function unlock() {
  var gate = document.getElementById('pvgate');
  var input = document.getElementById('pw');
  if (sha256(input.value) === PASSWORD_HASH) {
    sessionStorage.setItem('private_ok', '1');
    gate.style.display = 'none';
    document.getElementById('main').style.display = 'block';
  } else {
    gate.classList.remove('err');
    void gate.offsetWidth;
    gate.classList.add('err');
    input.value = '';
    input.focus();
  }
}
document.addEventListener('DOMContentLoaded', function() {
  if (sessionStorage.getItem('private_ok') === '1') {
    document.getElementById('pvgate').style.display = 'none';
    document.getElementById('main').style.display = 'block';
  }
  document.getElementById('pw').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') unlock();
  });
  document.getElementById('btn').addEventListener('click', unlock);
});
"""


def page(title, breadcrumb, body_html, hide_meta=False):
    meta = "" if hide_meta else (
        '<meta name="robots" content="noindex,nofollow">'
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
{meta}
<link rel="stylesheet" href="../../zy-tech.css">
<style>{GATE_CSS}</style>
</head>
<body>
<div class="kb-bread">{breadcrumb}</div>
<div class="pvgate" id="pvgate">
  <div class="lock">🔐</div>
  <p>这是私人资料<br>输入密码后解锁查看</p>
  <input type="password" id="pw" placeholder="••••••" maxlength="16" autocomplete="off" inputmode="numeric">
  <button id="btn" type="button">解 锁</button>
  <div class="err-msg" id="err">密码不对, 再试一次</div>
</div>
<div id="main" style="display:none;max-width:960px;margin:0 auto;padding:0 20px 60px">
{body_html}
</div>
<script>{GATE_JS}</script>
</body>
</html>"""


def load_md(path):
    return (SRC / path).read_text(encoding="utf-8")


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    # ---- 首页：总纪要 ----
    overview = load_md(r"obsidian-vault\03-领域知识\个人档案\讯飞办公本笔记总纪要.md")
    body = publish.md_to_html(overview)
    nav = """<div style="margin:20px 0;padding:14px 18px;border:1px solid rgba(56,189,248,.16);border-radius:12px;background:rgba(10,20,38,.45)">
<span style="color:#7d92ad;font-size:12px">板块导航：</span>
<a href="2024.html" style="color:#22d3ee;margin:0 8px">2024 年明细</a>·
<a href="2025.html" style="color:#22d3ee;margin:0 8px">2025 年明细</a>·
<a href="2026.html" style="color:#22d3ee;margin:0 8px">2026 年明细</a>·
<a href="themes-1.html" style="color:#a5b4fc;margin:0 8px">主题线 2024-2025H1</a>·
<a href="themes-2.html" style="color:#a5b4fc;margin:0 8px">主题线 2025H2-2026</a>
</div>"""
    (OUT / "index.html").write_text(
        page("讯飞本文件 · 私人专区",
             '<a href="../../index.html">成果站</a> / <a href="../../private.html">私人专区</a> / 讯飞本文件',
             nav + body), encoding="utf-8")
    print("index.html 完成")

    # ---- 年度明细页 ----
    for year, groups in YEAR_GROUPS.items():
        parts = [f"<h1>讯飞办公本笔记 · {year} 年明细</h1>",
                 '<p style="color:#7d92ad;font-size:12px">来源：办公本云端笔记逐篇归纳（录音转写要点提炼），⚠️ 为转写存疑数字</p>']
        for g in groups:
            md = load_md(rf"doxent_summaries\{g}.md")
            parts.append(publish.md_to_html(md))
        body = "\n".join(parts) + nav.replace("2024.html", f"<a href='index.html' style='color:#22d3ee;margin:0 8px'>返回总纪要</a>")
        (OUT / f"{year}.html").write_text(
            page(f"讯飞本文件 · {year} 年明细",
                 '<a href="../../index.html">成果站</a> / <a href="../../private.html">私人专区</a> / <a href="index.html">讯飞本文件</a> / 明细',
                 body), encoding="utf-8")
        print(f"{year}.html 完成")

    # ---- 主题线页 ----
    themes = [("themes-1", "主题线-2024至2025上半年.md", "主题线 2024-10 ~ 2025-06"),
              ("themes-2", "主题线-2025下半年至2026.md", "主题线 2025-07 ~ 2026-09")]
    for slug, fname, label in themes:
        md = load_md(rf"obsidian-vault\03-领域知识\个人档案\讯飞办公本笔记明细\{fname}")
        body = publish.md_to_html(md)
        (OUT / f"{slug}.html").write_text(
            page(f"讯飞本文件 · {label}",
                 '<a href="../../index.html">成果站</a> / <a href="../../private.html">私人专区</a> / <a href="index.html">讯飞本文件</a> / 主题线',
                 body), encoding="utf-8")
        print(f"{slug}.html 完成")


if __name__ == "__main__":
    main()
