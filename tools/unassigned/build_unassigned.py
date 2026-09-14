# -*- coding: utf-8 -*-
"""生成 CRM 未分配团队客户可视化页 -> tools/unassigned/unassigned.html
数据源: D:/cloude code/client_list_page/crm_customers.json (从 CRM API 拉取)
密码门与 client-list-lite / counterparty 同级(同一哈希)
"""
import json, sys
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).parent
SRC = Path(r"D:/cloude code/client_list_page/crm_customers.json")

data = json.load(open(SRC, encoding="utf-8"))
# 只保留必要字段, 控制体积
FIELDS = ["name", "shortName", "type", "province", "status", "tier",
          "investedSize", "firstContact", "lastContact"]
rows = [{k: c.get(k, "") for k in FIELDS} for c in data]
rows.sort(key=lambda r: (r["type"], r["province"], r["name"]))

generated = date.today().isoformat()
total = len(rows)
type_count = len({r["type"] for r in rows})
prov_count = len({r["province"] for r in rows})
tier_a = sum(1 for r in rows if r["tier"] == "A")
done_cnt = sum(1 for r in rows if r["status"] == "done")

TYPE_ORDER = ["证券公司", "保险公司", "信托公司", "城商行", "农商行", "其他银行",
              "保险资产管理公司", "民营银行", "理财子公司", "国有银行"]
TYPE_COLORS = ["#22d3ee", "#3b82f6", "#8b5cf6", "#34d399", "#a3e635", "#fb923c",
               "#f472b6", "#facc15", "#60a5fa", "#94a3b8"]

payload = json.dumps({"generated": generated, "total": total, "rows": rows},
                     ensure_ascii=False)

html = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CRM 未分配团队客户 · EVERSTEAD</title>
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
h1{font-size:21px;font-weight:700;margin:2px 0 2px}
.sub{font-family:var(--mono);font-size:12px;color:var(--muted);letter-spacing:.08em;padding:0 0 18px}
.sub b{color:var(--cyan)}

.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:16px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;backdrop-filter:blur(6px)}
.stat .k{font-size:11px;color:var(--muted);letter-spacing:.12em;font-family:var(--mono)}
.stat .v{font-size:24px;font-weight:700;margin-top:4px;font-family:var(--mono)}
.stat .v small{font-size:12px;font-weight:400;color:var(--muted);margin-left:2px}
.stat .v.gold{color:var(--cyan)}
.stat .v.warn{color:var(--orange)}

/* 可视化区 */
.viz{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 18px;backdrop-filter:blur(6px)}
.panel .p-title{font-size:11px;color:var(--muted);letter-spacing:.12em;font-family:var(--mono);margin-bottom:12px}
.bar-row{display:flex;align-items:center;gap:10px;margin-bottom:8px;cursor:pointer;border-radius:6px;padding:2px 6px;transition:background .15s}
.bar-row:hover{background:rgba(34,211,238,.06)}
.bar-row.on{background:rgba(34,211,238,.12)}
.bar-row .lbl{width:96px;font-size:12px;color:var(--muted);text-align:right;flex-shrink:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar-row .track{flex:1;height:16px;background:rgba(56,189,248,.07);border-radius:999px;overflow:hidden}
.bar-row .fill{height:100%;border-radius:999px;transition:width .5s cubic-bezier(.2,.8,.2,1);min-width:2px}
.bar-row .n{width:44px;font-family:var(--mono);font-size:12px;color:var(--text);text-align:left;flex-shrink:0}
.bar-row.off{opacity:.32}
.bar-row.off:hover{opacity:.6}

.toolbar{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px;align-items:center}
.toolbar input,.toolbar select{background:rgba(7,16,33,.95);border:1px solid var(--line);border-radius:8px;color:var(--text);padding:8px 12px;font-size:13px;outline:none;transition:border-color .2s}
.toolbar input:focus,.toolbar select:focus{border-color:var(--line-strong)}
.toolbar input{flex:1;min-width:220px}
.toolbar select{cursor:pointer}
.toolbar select option{background:#0a1426}
.toolbar .btn{background:rgba(10,20,38,.4);border:1px solid var(--line);border-radius:8px;color:var(--muted);padding:8px 14px;font-size:13px;cursor:pointer;font-family:var(--mono);transition:all .2s}
.toolbar .btn:hover{border-color:var(--line-strong);color:var(--cyan)}
.cnt{margin-left:auto;font-size:12px;color:var(--muted);font-family:var(--mono)}
.cnt b{color:var(--cyan)}

.tbl-wrap{background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:auto;max-height:68vh;backdrop-filter:blur(6px)}
table{width:100%;border-collapse:collapse;font-size:13px;min-width:760px}
thead th{position:sticky;top:0;background:rgba(7,16,33,.97);color:var(--muted);font-size:11px;font-weight:600;letter-spacing:.1em;padding:11px 12px;text-align:left;border-bottom:1px solid var(--line-strong);white-space:nowrap;font-family:var(--mono);z-index:2}
thead th.sort{cursor:pointer;user-select:none}
thead th.sort:hover{color:var(--cyan)}
thead th .dir{color:var(--cyan);margin-left:3px}
tbody td{padding:9px 12px;border-bottom:1px solid rgba(56,189,248,.07);white-space:nowrap}
tbody tr:hover{background:rgba(34,211,238,.05)}
tbody tr:nth-child(even){background:rgba(56,189,248,.025)}
td.name{font-weight:600}
td.mono{font-family:var(--mono)}
td.num{font-family:var(--mono);text-align:right}
.badge{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11px;font-family:var(--mono);border:1px solid}
.b-A{color:#f0abfc;border-color:rgba(240,171,252,.4);background:rgba(240,171,252,.1)}
.b-C{color:var(--muted);border-color:rgba(125,146,173,.3);background:rgba(125,146,173,.08)}
.b-done{color:#6ee7b7;border-color:rgba(110,231,183,.35);background:rgba(110,231,183,.1)}
.b-pending{color:var(--orange);border-color:rgba(251,146,60,.35);background:rgba(251,146,60,.08)}
.empty{padding:48px;text-align:center;color:var(--muted);font-size:13px}
.foot{margin-top:16px;font-size:11px;color:var(--muted);font-family:var(--mono);line-height:1.8}
.foot b{color:var(--text);font-weight:600}

/* 密码门 */
.gate{position:fixed;inset:0;z-index:50;display:flex;align-items:center;justify-content:center;background:#03060c}
.gate-card{text-align:center;padding:44px 48px;border:1px solid var(--line);border-radius:18px;background:rgba(10,20,38,.85);backdrop-filter:blur(10px);max-width:400px}
.gate-card h2{font-size:17px;letter-spacing:.15em;font-family:var(--mono);color:var(--cyan)}
.gate-card p{font-size:12px;color:var(--muted);margin:10px 0 20px;line-height:1.8}
.gate-card input{width:100%;padding:11px 14px;border:1px solid var(--line-strong);border-radius:10px;background:rgba(7,16,33,.95);color:var(--text);font-size:15px;text-align:center;letter-spacing:.3em;outline:none}
.gate-card input:focus{border-color:var(--cyan)}
.gate-card button{margin-top:14px;padding:10px 34px;border-radius:999px;border:none;background:linear-gradient(135deg,var(--cyan),var(--blue));color:#03101f;font-weight:700;font-size:14px;cursor:pointer;font-family:var(--mono)}
.gate-card .err-msg{display:none;color:var(--rose);font-size:12px;margin-top:12px;font-family:var(--mono)}
@media(max-width:900px){
  .stats{grid-template-columns:repeat(3,1fr)}
  .viz{grid-template-columns:1fr}
  .bar-row .lbl{width:76px}
}
</style>
</head>
<body>
<div class="bg-grid"></div>

<div class="gate" id="gate">
  <div class="gate-card">
    <h2>🔒 未分配客户池</h2>
    <p>CRM 内部客户数据 · 与内网 CRM 同级管理<br>输入密码后解锁</p>
    <input type="password" id="pw" placeholder="••••" maxlength="16" autocomplete="off">
    <button id="btn">解锁</button>
    <div class="err-msg" id="err">密码不对, 再试一次</div>
  </div>
</div>

<div class="wrap">
  <div class="topbar">
    <div class="logo">👥</div>
    <div>
      <div class="brand">UNASSIGNED <em>·</em> CRM</div>
      <h1>未分配团队客户</h1>
    </div>
    <a class="back" href="../../index.html">← 返回成果站</a>
  </div>
  <div class="sub">数据来源: 金融市场中心 CRM <b>192.168.100.148:3000</b> · 筛选条件 team 为空 · 更新于 <b id="gen"></b> · 点击条形图可联动筛选</div>

  <div class="stats" id="stats"></div>

  <div class="viz">
    <div class="panel">
      <div class="p-title">机构类型分布 · 点击筛选</div>
      <div id="typeBars"></div>
    </div>
    <div class="panel">
      <div class="p-title">地域分布 TOP15 · 点击筛选</div>
      <div id="provBars"></div>
    </div>
  </div>

  <div class="toolbar">
    <input id="q" type="search" placeholder="🔍 搜索机构名称 / 简称 …">
    <select id="typeSel"><option value="">全部类型</option></select>
    <select id="provSel"><option value="">全部地域</option></select>
    <select id="tierSel">
      <option value="">全部层级</option>
      <option value="A">A 级</option>
      <option value="C">C 级</option>
    </select>
    <select id="sortSel">
      <option value="name">按名称</option>
      <option value="type">按类型</option>
      <option value="province">按地域</option>
      <option value="investedSize">按投资规模</option>
      <option value="firstContact">按首次接触</option>
    </select>
    <button class="btn" id="export">⬇ 导出 CSV</button>
    <span class="cnt">显示 <b id="cnt">0</b> / <span id="total"></span> 家</span>
  </div>

  <div class="tbl-wrap">
    <table>
      <thead>
        <tr>
          <th>机构名称</th>
          <th>简称</th>
          <th class="sort" data-k="type">类型<span class="dir"></span></th>
          <th class="sort" data-k="province">地域<span class="dir"></span></th>
          <th>层级</th>
          <th>状态</th>
          <th class="sort" data-k="firstContact">首次接触<span class="dir"></span></th>
          <th class="sort" data-k="investedSize">投资规模(亿)<span class="dir"></span></th>
        </tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
    <div class="empty" id="empty" style="display:none">没有符合条件的客户</div>
  </div>

  <div class="foot">
    内部数据 · 密码访问 · 与 CRM 同级管理<br>
    数据快照 <b id="gen2"></b> · 共 <b id="tot2"></b> 家 · 全部 team 为空(未分配) · 客户经理 wangshaobin 账号导出
  </div>
</div>

<script>
/* ---- 密码门: 纯 JS SHA-256(与 client-list-lite 同源验证版) 只存哈希不存明文; sessionStorage 记住本会话 ---- */
var PASSWORD_HASH = "62030069b40c02d1dd642d438194850f14d9e79a25abd1e53c02f7391f8242c8";
var GATE_KEY = 'unassigned_ok';
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
  ascii += '\x80';
  while (ascii.length%64 - 56) ascii += '\x00';
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
  var gate = document.getElementById('gate');
  var input = document.getElementById('pw');
  if (sha256(input.value) === PASSWORD_HASH) {
    sessionStorage.setItem(GATE_KEY, '1');
    gate.style.display = 'none';
  } else {
    gate.classList.remove('err');
    void gate.offsetWidth;
    gate.classList.add('err');
    input.value = '';
    input.focus();
  }
}
document.getElementById('pw').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') unlock();
});
document.getElementById('btn').addEventListener('click', unlock);
if (sessionStorage.getItem(GATE_KEY) === '1') {
  document.getElementById('gate').style.display = 'none';
}

/* ---- 数据与视图 ---- */
var DATA = __DATA__;
var rows = DATA.rows;
var sel = {q:'', type:'', prov:'', tier:'', sort:'name', sortDir:1};
var TYPE_COLORS = __TYPE_COLORS__;

document.getElementById('gen').textContent = DATA.generated;
document.getElementById('gen2').textContent = DATA.generated;
document.getElementById('total').textContent = rows.length;
document.getElementById('tot2').textContent = rows.length;

function counts(rs){
  var types={}, provs={}, tierA=0, done=0;
  rs.forEach(function(r){
    types[r.type]=(types[r.type]||0)+1;
    provs[r.province]=(provs[r.province]||0)+1;
    if(r.tier==='A')tierA++;
    if(r.status==='done')done++;
  });
  return {types:types, provs:provs, tierA:tierA, done:done};
}

function renderStats(rs){
  var c=counts(rs);
  document.getElementById('stats').innerHTML =
    '<div class="stat"><div class="k">未分配客户</div><div class="v gold">'+rs.length+'<small>家</small></div></div>'+
    '<div class="stat"><div class="k">机构类型</div><div class="v">'+Object.keys(c.types).length+'<small>类</small></div></div>'+
    '<div class="stat"><div class="k">覆盖地域</div><div class="v">'+Object.keys(c.provs).length+'<small>省/市</small></div></div>'+
    '<div class="stat"><div class="k">A 级客户</div><div class="v warn">'+c.tierA+'<small>家</small></div></div>'+
    '<div class="stat"><div class="k">已投资</div><div class="v">'+c.done+'<small>家</small></div></div>';
}

function barPanel(el, map, colors, totalRows){
  var max = 1;
  Object.keys(map).forEach(function(k){if(map[k]>max)max=map[k]});
  var items = Object.keys(map).sort(function(a,b){return map[b]-map[a]});
  var h = '<div class="bar-row" data-k="" style="cursor:default">'+
          '<span class="lbl">全部</span><span class="track"></span>'+
          '<span class="n">'+totalRows+'</span></div>';
  items.forEach(function(k){
    var color = colors[k] || '#7dd3fc';
    var on = (el.id==='typeBars'?sel.type===k:sel.prov===k) ? ' on' : '';
    var off = (el.id==='typeBars'?(sel.type!==''&&sel.type!==k):(sel.prov!==''&&sel.prov!==k)) ? ' off' : '';
    h += '<div class="bar-row'+on+off+'" data-k="'+k+'">'+
         '<span class="lbl">'+k+'</span>'+
         '<span class="track"><span class="fill" style="width:'+(map[k]/max*100).toFixed(1)+'%;background:'+color+'"></span></span>'+
         '<span class="n">'+map[k]+'</span></div>';
  });
  el.innerHTML = h;
  el.querySelectorAll('.bar-row[data-k]').forEach(function(row){
    row.addEventListener('click', function(){
      var k = row.getAttribute('data-k');
      if(el.id==='typeBars'){ sel.type = (sel.type===k?'':k); }
      else { sel.prov = (sel.prov===k?'':k); }
      document.getElementById('typeSel').value = sel.type;
      document.getElementById('provSel').value = sel.prov;
      apply();
    });
  });
}

function filtered(){
  return rows.filter(function(r){
    if(sel.q){
      var q = sel.q.toLowerCase();
      if(!(r.name||'').toLowerCase().includes(q) && !(r.shortName||'').toLowerCase().includes(q)) return false;
    }
    if(sel.type && r.type!==sel.type) return false;
    if(sel.prov && r.province!==sel.prov) return false;
    if(sel.tier && r.tier!==sel.tier) return false;
    return true;
  });
}

function renderTable(){
  var rs = filtered().slice().sort(function(a,b){
    var k = sel.sort;
    var va = a[k]||'', vb = b[k]||'';
    if(k==='investedSize') return (va-vb)*sel.sortDir;
    return String(va).localeCompare(String(vb),'zh')*sel.sortDir;
  });
  var tb = document.getElementById('tbody');
  tb.innerHTML = rs.map(function(r){
    var sz = r.investedSize>0 ? r.investedSize.toFixed(1) : '—';
    var tier = r.tier==='A' ? '<span class="badge b-A">A</span>' : '<span class="badge b-C">C</span>';
    var st = r.status==='done' ? '<span class="badge b-done">已投资</span>' : '<span class="badge b-pending">待落地</span>';
    return '<tr><td class="name">'+(r.name||'')+'</td>'+
           '<td class="mono">'+(r.shortName||'—')+'</td>'+
           '<td>'+(r.type||'')+'</td>'+
           '<td>'+(r.province||'')+'</td>'+
           '<td>'+tier+'</td><td>'+st+'</td>'+
           '<td class="mono">'+(r.firstContact||'—')+'</td>'+
           '<td class="num">'+sz+'</td></tr>';
  }).join('');
  document.getElementById('cnt').textContent = rs.length;
  document.getElementById('empty').style.display = rs.length ? 'none' : 'block';
  document.querySelectorAll('thead th.sort .dir').forEach(function(d){d.textContent=''});
  var th = document.querySelector('thead th.sort[data-k="'+sel.sort+'"] .dir');
  if(th) th.textContent = sel.sortDir===1 ? '↑' : '↓';
}

function apply(){
  var rs = filtered();
  renderStats(rs);
  barPanel(document.getElementById('typeBars'), counts(rs).types, TYPE_COLORS, rows.length);
  barPanel(document.getElementById('provBars'), counts(rs).provs, {}, rows.length);
  renderTable();
}

/* 初始化筛选器 */
(function(){
  var all = rows;
  var types = {}, provs = {};
  all.forEach(function(r){types[r.type]=1; provs[r.province]=1});
  var tSel = document.getElementById('typeSel');
  Object.keys(types).sort(function(a,b){return counts(rows).types[b]-counts(rows).types[a]}).forEach(function(k){
    tSel.innerHTML += '<option value="'+k+'">'+k+'</option>';
  });
  var pSel = document.getElementById('provSel');
  Object.keys(provs).sort(function(a,b){return counts(rows).provs[b]-counts(rows).provs[a]}).forEach(function(k){
    pSel.innerHTML += '<option value="'+k+'">'+k+'</option>';
  });
})();

document.getElementById('q').addEventListener('input', function(e){ sel.q=e.target.value.trim(); apply(); });
document.getElementById('typeSel').addEventListener('change', function(e){ sel.type=e.target.value; apply(); });
document.getElementById('provSel').addEventListener('change', function(e){ sel.prov=e.target.value; apply(); });
document.getElementById('tierSel').addEventListener('change', function(e){ sel.tier=e.target.value; apply(); });
document.getElementById('sortSel').addEventListener('change', function(e){ sel.sort=e.target.value; apply(); });
document.querySelectorAll('thead th.sort').forEach(function(th){
  th.addEventListener('click', function(){
    var k = th.getAttribute('data-k');
    if(sel.sort===k){ sel.sortDir*=-1; } else { sel.sort=k; sel.sortDir=1; }
    apply();
  });
});
document.getElementById('export').addEventListener('click', function(){
  var rs = filtered();
  var lines = ['名称,简称,类型,地域,层级,状态,首次接触,投资规模(亿)'];
  rs.forEach(function(r){
    lines.push(['"'+r.name+'"','"'+r.shortName+'"','"'+r.type+'"','"'+r.province+'"',
      r.tier, r.status==='done'?'已投资':'待落地', r.firstContact, r.investedSize||''].join(','));
  });
  var blob = new Blob(['\\ufeff'+lines.join('\\n')], {type:'text/csv;charset=utf-8'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = '未分配客户_' + DATA.generated + '.csv';
  a.click();
});

apply();
</script>
</body>
</html>"""

html = (html.replace("__DATA__", payload)
            .replace("__TYPE_COLORS__", json.dumps({t: TYPE_COLORS[i % len(TYPE_COLORS)]
                      for i, t in enumerate(TYPE_ORDER)}, ensure_ascii=False)))

out = HERE / "unassigned.html"
out.write_text(html, encoding="utf-8")
print(f"生成 {out} · {len(rows)} 家 · {len(html)//1024}KB")
