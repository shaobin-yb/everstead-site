# -*- coding: utf-8 -*-
"""
直接交易对手库 → 成果站工具箱页面生成器
数据源: D:\\工作文件\\初期项目\\方案等文件\\直接交易对手库汇总表20241223-更新地域.xlsx
输出:   counterparty.html (数据内嵌, 零外部依赖, 双击即可打开)

重新生成: py build_counterparty.py
Excel 更新后重跑本脚本即可刷新页面数据。
"""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import openpyxl

SRC = Path(r"D:\工作文件\初期项目\方案等文件\直接交易对手库汇总表20241223-更新地域.xlsx")
OUT = Path(__file__).parent / "counterparty.html"

# 汇总表 5 家缺注册省的企业, 按公开信息补全 (核实日期 2026-09-11)
PROV_FIX = {
    "国泰君安证券股份有限公司": "上海市",        # 601211.SH 注册地上海 (iFind)
    "绍兴市城市建设投资集团有限公司": "浙江省",
    "中航国际实业控股有限公司": "广东省",        # 注册地深圳市南山区 (简式权益变动报告书)
    "唐山冀东水泥股份有限公司": "河北省",        # 000401.SZ 注册地河北 (iFind)
    "宁波市北仑区国有资本运营有限公司": "浙江省",
}

RATING_ORDER = {"AAA": 12, "AA+": 11, "AA": 10, "AA-": 9, "A+": 8, "A": 7, "A-": 6,
                "BBB+": 5, "BBB": 4, "BBB-": 3, "BB+": 2, "BB": 1, "B+": 0}
RATING_SET = set(RATING_ORDER)


def excel_date(v):
    """Excel 序列日期 → YYYY-MM-DD"""
    if isinstance(v, (int, float)):
        return (datetime(1899, 12, 30) + timedelta(days=int(v))).strftime("%Y-%m-%d")
    return v or ""


def load():
    wb = openpyxl.load_workbook(SRC, data_only=True)

    # ---- 在库 468 家 ----
    ws = wb["汇总表"]
    active = []
    for row in ws.iter_rows(min_row=3, values_only=True):
        if row[0] is None:
            continue
        name = str(row[1]).strip()
        prov = str(row[2]).strip() if row[2] else ""
        prov = PROV_FIX.get(name, prov)
        active.append({
            "seq": int(row[0]),
            "name": name,
            "prov": prov,
            "ext": str(row[3] or "").strip(),
            "int": str(row[4] or "").strip(),
            "outlook": str(row[5] or "").strip(),
            "limit": row[6] if isinstance(row[6], (int, float)) else None,
            "date": excel_date(row[7]),
            "note": str(row[8]).strip() if row[8] else "",
            "analyst": str(row[9]).strip() if row[9] else "",
        })

    # ---- 历史出库 58 家 ----
    ws2 = wb["历史出库企业"]
    removed = []
    for row in ws2.iter_rows(min_row=2, values_only=True):
        if row[0] is None:
            continue
        # 该表有两家的"内部评级"列实为注销说明, 移到备注
        int_raw = str(row[3]).strip() if row[3] else ""
        note = str(row[6]).strip() if row[6] else ""
        if int_raw not in RATING_SET:
            note = (int_raw + ";" + note) if note else int_raw
            int_raw = ""
        removed.append({
            "seq": int(row[0]),
            "name": str(row[1]).strip(),
            "ext": str(row[2] or "").strip(),
            "int": int_raw,
            "limit": row[4] if isinstance(row[4], (int, float)) else None,
            "date": excel_date(row[5]),
            "note": note,
        })
    return active, removed


HTML_TPL = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>直接交易对手库 · EVERSTEAD</title>
<style>
:root{
  --bg:#03060c;
  --panel:rgba(10,20,38,.55);
  --panel-hover:rgba(14,28,52,.75);
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

/* 顶栏 */
.topbar{display:flex;align-items:center;gap:14px;padding:22px 0 16px}
.topbar .logo{width:40px;height:40px;border-radius:10px;flex-shrink:0;background:linear-gradient(135deg,var(--cyan),var(--violet));display:flex;align-items:center;justify-content:center;font-weight:800;font-size:19px;color:#03101f;box-shadow:var(--glow);font-family:var(--mono)}
.topbar .brand{font-family:var(--mono);font-weight:700;letter-spacing:.28em;font-size:15px}
.topbar .brand em{font-style:normal;background:linear-gradient(90deg,var(--cyan),var(--blue),var(--violet));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.topbar .back{margin-left:auto;font-family:var(--mono);font-size:11px;letter-spacing:.14em;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:6px 14px;background:rgba(10,20,38,.4);transition:border-color .25s,color .25s}
.topbar .back:hover{border-color:var(--line-strong);color:var(--cyan)}
.sub{font-family:var(--mono);font-size:12px;color:var(--muted);letter-spacing:.08em;padding:0 0 18px}

/* 统计条 */
.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:16px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;backdrop-filter:blur(6px)}
.stat .k{font-size:11px;color:var(--muted);letter-spacing:.12em;font-family:var(--mono)}
.stat .v{font-size:24px;font-weight:700;margin-top:4px;font-family:var(--mono)}
.stat .v small{font-size:12px;font-weight:400;color:var(--muted);margin-left:2px}
.stat .v.gold{color:var(--cyan)}
.stat .v.warn{color:var(--orange)}

/* Tab */
.tabs{display:flex;gap:8px;margin-bottom:14px}
.tab{padding:9px 22px;border-radius:999px;border:1px solid var(--line);background:rgba(10,20,38,.4);color:var(--muted);cursor:pointer;font-size:13px;transition:all .2s;font-family:var(--mono);letter-spacing:.08em}
.tab:hover{border-color:var(--line-strong);color:var(--text)}
.tab.on{background:linear-gradient(135deg,rgba(34,211,238,.18),rgba(59,130,246,.18));border-color:var(--line-strong);color:var(--cyan)}
.tab .n{font-family:var(--mono);opacity:.75;margin-left:4px}

/* 工具栏 */
.toolbar{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px;align-items:center}
.toolbar input,.toolbar select{background:rgba(7,16,33,.95);border:1px solid var(--line);border-radius:8px;color:var(--text);padding:8px 12px;font-size:13px;outline:none;transition:border-color .2s}
.toolbar input:focus,.toolbar select:focus{border-color:var(--line-strong)}
.toolbar input{flex:1;min-width:220px}
.toolbar select{cursor:pointer}
.toolbar select option{background:#0a1426}
.cnt{margin-left:auto;font-size:12px;color:var(--muted);font-family:var(--mono)}

/* 表格 */
.tbl-wrap{background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:auto;max-height:72vh;backdrop-filter:blur(6px)}
table{width:100%;border-collapse:collapse;font-size:13px;min-width:960px}
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
.b-ext{color:#7dd3fc;border-color:rgba(125,211,252,.3);background:rgba(125,211,252,.08)}
.b-int{color:#c4b5fd;border-color:rgba(196,181,253,.3);background:rgba(196,181,253,.08)}
.b-neg{color:var(--rose);border-color:rgba(244,63,94,.4);background:rgba(244,63,94,.1)}
.b-watch{color:var(--orange);border-color:rgba(251,146,60,.4);background:rgba(251,146,60,.1)}
.b-stable{color:#6ee7b7;border-color:rgba(110,231,183,.25);background:rgba(110,231,183,.07)}
.note{color:var(--muted);font-size:12px;white-space:normal;max-width:340px;line-height:1.5}
.empty{padding:48px;text-align:center;color:var(--muted);font-size:13px}
.foot{margin-top:22px;font-size:11px;color:var(--muted);line-height:1.8;font-family:var(--mono);letter-spacing:.05em}

/* 密码门 */
.gate{position:fixed;inset:0;z-index:99;background:rgba(3,6,12,.94);backdrop-filter:blur(10px);display:flex;align-items:center;justify-content:center}
.gate-panel{background:var(--panel);border:1px solid var(--line-strong);border-radius:16px;padding:38px 44px;box-shadow:0 12px 40px rgba(0,0,0,.25);width:min(400px,90vw);text-align:center}
.gate-panel .g-ico{font-size:34px;margin-bottom:12px}
.gate-panel h2{font-size:17px;letter-spacing:.2em;margin-bottom:6px}
.gate-panel p{font-size:12px;color:var(--muted);margin-bottom:20px}
.gate-panel input{width:100%;background:rgba(7,16,33,.95);border:1px solid var(--line);border-radius:8px;color:var(--text);padding:10px 14px;font-size:14px;outline:none;text-align:center;letter-spacing:.3em}
.gate-panel input:focus{border-color:var(--cyan)}
.gate-panel button{margin-top:14px;width:100%;padding:10px;border:none;border-radius:8px;background:linear-gradient(135deg,var(--cyan),var(--blue));color:#03101f;font-weight:700;font-size:14px;cursor:pointer;letter-spacing:.2em}
.gate-panel button:hover{filter:brightness(1.15)}
.gate.err .gate-panel{animation:shake .4s}
@keyframes shake{0%,100%{transform:translateX(0)}20%,60%{transform:translateX(-8px)}40%,80%{transform:translateX(8px)}}
@media (max-width:760px){.stats{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<div class="bg-grid"></div>

<!-- 密码门: 与CRM/客户名单同级密码, sessionStorage 记住本会话 -->
<div class="gate" id="gate">
  <div class="gate-panel">
    <div class="g-ico">🔒</div>
    <h2>直接交易对手库</h2>
    <p>内部授信评级数据 · 密码访问</p>
    <input type="password" id="pw" placeholder="请输入访问密码" autocomplete="off">
    <button id="btn">解 锁</button>
  </div>
</div>

<div class="wrap">
  <div class="topbar">
    <div class="logo">E</div>
    <div class="brand">EVERSTEAD <em>TOOLBOX</em></div>
    <a class="back" href="../../tools.html">← 工具箱</a>
  </div>
  <div class="sub">DIRECT COUNTERPARTY DATABASE · 中邮保险资产管理有限公司 · 更新于 2024-12-23</div>

  <div class="stats" id="stats"></div>

  <div class="tabs">
    <div class="tab on" id="tabActive" onclick="switchTab('active')">在库对手<span class="n" id="nActive"></span></div>
    <div class="tab" id="tabRemoved" onclick="switchTab('removed')">历史出库<span class="n" id="nRemoved"></span></div>
  </div>

  <div class="toolbar" id="toolbarActive">
    <input id="search" placeholder="🔍 搜索企业名称…">
    <select id="fProv"><option value="">全部省份</option></select>
    <select id="fExt"><option value="">全部外部评级</option></select>
    <select id="fInt"><option value="">全部内部评级</option></select>
    <select id="fOutlook"><option value="">全部展望</option></select>
    <select id="fAnalyst"><option value="">全部分析师</option></select>
    <span class="cnt" id="cnt"></span>
  </div>
  <div class="toolbar" id="toolbarRemoved" style="display:none">
    <input id="search2" placeholder="🔍 搜索出库企业名称…">
    <span class="cnt" id="cnt2"></span>
  </div>

  <div class="tbl-wrap" id="wrapActive"><table id="tblActive"></table></div>
  <div class="tbl-wrap" id="wrapRemoved" style="display:none"><table id="tblRemoved"></table></div>

  <div class="foot">
    数据源: 直接交易对手库汇总表20241223-更新地域.xlsx(汇总表 468 家 + 历史出库企业 58 家)<br>
    5 家缺注册省企业已按公开信息补全(国泰君安→上海、冀东水泥→河北、中航国际实业→广东、绍兴城投/宁波北仑国资→浙江)<br>
    授信额度单位: 亿元 · 评级日期为最新评审日期 · 内部评级 BB+ 及以下标橙、展望负面标红
  </div>
</div>

<script>
var ACTIVE = __ACTIVE__;
var REMOVED = __REMOVED__;
var RATING_ORDER = {"AAA":12,"AA+":11,"AA":10,"AA-":9,"A+":8,"A":7,"A-":6,"BBB+":5,"BBB":4,"BBB-":3,"BB+":2,"BB":1,"B+":0};
var LOW_INT = 2; /* BB+ 及以下视为低评级 */
var curTab = 'active';
var sortKey = 'seq', sortDir = 1;

/* ---- 密码门 ---- */
var PASSWORD_HASH = "62030069b40c02d1dd642d438194850f14d9e79a25abd1e53c02f7391f8242c8";
var GATE_KEY = 'cp_counterparty_ok';
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
if(sessionStorage.getItem(GATE_KEY)==='1'){document.getElementById('gate').style.display='none'}

/* ---- 统计 ---- */
function renderStats(){
  var total=0, aaa=0, warn=0, provs={};
  ACTIVE.forEach(function(c){total+=c.limit||0;if(c.ext==='AAA')aaa++;if(RATING_ORDER[c.int]!==undefined&&RATING_ORDER[c.int]<=LOW_INT)warn++;provs[c.prov]=(provs[c.prov]||0)+1});
  var nProv=Object.keys(provs).length;
  var neg=ACTIVE.filter(function(c){return c.outlook.indexOf('负面')>=0}).length;
  var obs=ACTIVE.filter(function(c){return c.outlook.indexOf('观察')>=0}).length;
  document.getElementById('stats').innerHTML=
    statBox('在库对手', ACTIVE.length, '家', '')+
    statBox('授信总额度', total, '亿元', 'gold')+
    statBox('外部评级 AAA', aaa, '家 / '+(ACTIVE.length?Math.round(aaa/ACTIVE.length*100):0)+'%', '')+
    statBox('覆盖省份', nProv, '个省市自治区', '')+
    statBox('风险提示', (neg+obs)+warn, '负面'+neg+' · 观察'+obs+' · 低内评'+warn, 'warn');
}
function statBox(k,v,unit,cls){return '<div class="stat"><div class="k">'+k+'</div><div class="v '+cls+'">'+v+'<small>'+unit+'</small></div></div>'}

/* ---- 表格渲染 ---- */
function outBadge(c){return c.outlook==='负面'?'<span class="badge b-neg">负面</span>':(c.outlook.indexOf('观察')>=0?'<span class="badge b-watch">'+c.outlook+'</span>':(c.outlook==='稳定'?'<span class="badge b-stable">稳定</span>':escapeHtml(c.outlook)))}
function intBadge(c){var r=c.int;if(!r)return'—';var low=RATING_ORDER[r]!==undefined&&RATING_ORDER[r]<=LOW_INT;return'<span class="badge '+(low?'b-watch':'b-int')+'">'+r+'</span>'}
function escapeHtml(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
function th(label,key,cls){var dir=sortKey===key?'<span class="dir">'+(sortDir>0?'▲':'▼')+'</span>':'';return'<th class="'+(cls||'')+'" '+(key?'data-sort="'+key+'" onclick="setSort(\''+key+'\')"':'')+'>'+label+dir+'</th>'}
function renderActive(){
  var q=document.getElementById('search').value.trim().toLowerCase();
  var fP=document.getElementById('fProv').value, fE=document.getElementById('fExt').value,
      fI=document.getElementById('fInt').value, fO=document.getElementById('fOutlook').value,
      fA=document.getElementById('fAnalyst').value;
  var rows=ACTIVE.filter(function(c){
    if(q&&c.name.toLowerCase().indexOf(q)<0)return false;
    if(fP&&c.prov!==fP)return false;
    if(fE&&c.ext!==fE)return false;
    if(fI&&c.int!==fI)return false;
    if(fO&&c.outlook!==fO)return false;
    if(fA&&c.analyst!==fA)return false;
    return true;
  });
  rows.sort(function(a,b){
    var va=sortKey==='seq'?a.seq:(sortKey==='name'?a.name:(sortKey==='limit'?(a.limit||0):(sortKey==='date'?a.date:(sortKey==='int'?RATING_ORDER[a.int]||0:(sortKey==='ext'?RATING_ORDER[a.ext]||0:a.analyst)))));
    var vb=sortKey==='seq'?b.seq:(sortKey==='name'?b.name:(sortKey==='limit'?(b.limit||0):(sortKey==='date'?b.date:(sortKey==='int'?RATING_ORDER[b.int]||0:(sortKey==='ext'?RATING_ORDER[b.ext]||0:b.analyst)))));
    if(va<vb)return -1*sortDir;if(va>vb)return 1*sortDir;return a.seq-b.seq;
  });
  var html='<thead><tr>'+
    th('序号','seq','sort')+th('名称','name','sort')+th('注册省','')+th('外部评级','ext','sort')+
    th('内部评级','int','sort')+th('展望','')+th('授信额度','limit','sort')+
    th('最新评级日期','date','sort')+th('备注','')+th('分析师','analyst','sort')+'</tr></thead><tbody>';
  if(!rows.length)html+='<tr><td colspan="10" class="empty">无匹配结果</td></tr>';
  rows.forEach(function(c){
    html+='<tr><td class="mono">'+c.seq+'</td><td class="name">'+escapeHtml(c.name)+'</td><td>'+escapeHtml(c.prov||'—')+'</td>'+
      '<td><span class="badge b-ext">'+escapeHtml(c.ext)+'</span></td><td>'+intBadge(c)+'</td><td>'+outBadge(c)+'</td>'+
      '<td class="num">'+(c.limit==null?'—':c.limit)+'</td><td class="mono">'+escapeHtml(c.date)+'</td>'+
      '<td class="note">'+escapeHtml(c.note||'—')+'</td><td>'+escapeHtml(c.analyst||'—')+'</td></tr>';
  });
  html+='</tbody>';
  document.getElementById('tblActive').innerHTML=html;
  document.getElementById('cnt').textContent='显示 '+rows.length+' / '+ACTIVE.length+' 家';
}
function renderRemoved(){
  var q=document.getElementById('search2').value.trim().toLowerCase();
  var rows=REMOVED.filter(function(c){return!q||c.name.toLowerCase().indexOf(q)>=0});
  var html='<thead><tr>'+
    th('序号','')+th('名称','')+th('外部评级','')+th('内部评级','')+th('原授信额度','')+th('最新评审日期','')+th('出库原因/备注','')+'</tr></thead><tbody>';
  if(!rows.length)html+='<tr><td colspan="7" class="empty">无匹配结果</td></tr>';
  rows.forEach(function(c){
    html+='<tr><td class="mono">'+c.seq+'</td><td class="name">'+escapeHtml(c.name)+'</td>'+
      '<td><span class="badge b-ext">'+escapeHtml(c.ext)+'</span></td><td>'+(c.int?'<span class="badge b-int">'+escapeHtml(c.int)+'</span>':'—')+'</td>'+
      '<td class="num">'+(c.limit==null?'—':c.limit)+'</td><td class="mono">'+escapeHtml(c.date)+'</td>'+
      '<td class="note">'+escapeHtml(c.note||'—')+'</td></tr>';
  });
  html+='</tbody>';
  document.getElementById('tblRemoved').innerHTML=html;
  document.getElementById('cnt2').textContent='显示 '+rows.length+' / '+REMOVED.length+' 家';
}
function setSort(key){if(sortKey===key){sortDir*=-1}else{sortKey=key;sortDir=1}renderActive()}
function switchTab(t){
  curTab=t;
  document.getElementById('tabActive').className='tab'+(t==='active'?' on':'');
  document.getElementById('tabRemoved').className='tab'+(t==='removed'?' on':'');
  document.getElementById('toolbarActive').style.display=t==='active'?'':'none';
  document.getElementById('toolbarRemoved').style.display=t==='removed'?'':'none';
  document.getElementById('wrapActive').style.display=t==='active'?'':'none';
  document.getElementById('wrapRemoved').style.display=t==='removed'?'':'none';
}

/* ---- 初始化 ---- */
function fillSelect(id,vals){var sel=document.getElementById(id),cur=sel.value;sel.innerHTML='<option value="">全部'+(id==='fAnalyst'?'分析师':(id==='fOutlook'?'展望':(id==='fExt'?'外部评级':(id==='fInt'?'内部评级':'省份'))))+'</option>';
  vals.forEach(function(v){sel.innerHTML+='<option value="'+escapeHtml(v)+'">'+escapeHtml(v)+'</option>'});
  sel.value=cur||''}
(function init(){
  document.getElementById('nActive').textContent=ACTIVE.length;
  document.getElementById('nRemoved').textContent=REMOVED.length;
  document.getElementById('btn').addEventListener('click',unlock);
  document.getElementById('pw').addEventListener('keydown',function(e){if(e.key==='Enter')unlock()});
  var provs=[],exts=[],ints=[],outs=[],anas=[];
  ACTIVE.forEach(function(c){
    if(c.prov&&provs.indexOf(c.prov)<0)provs.push(c.prov);
    if(c.ext&&exts.indexOf(c.ext)<0)exts.push(c.ext);
    if(c.int&&ints.indexOf(c.int)<0)ints.push(c.int);
    if(c.outlook&&outs.indexOf(c.outlook)<0)outs.push(c.outlook);
    if(c.analyst&&anas.indexOf(c.analyst)<0)anas.push(c.analyst);
  });
  ints.sort(function(a,b){return(RATING_ORDER[b]||0)-(RATING_ORDER[a]||0)});
  exts.sort(function(a,b){return(RATING_ORDER[b]||0)-(RATING_ORDER[a]||0)});
  provs.sort();anas.sort();
  fillSelect('fProv',provs);fillSelect('fExt',exts);fillSelect('fInt',ints);fillSelect('fOutlook',outs);fillSelect('fAnalyst',anas);
  ['search','fProv','fExt','fInt','fOutlook','fAnalyst'].forEach(function(id){document.getElementById(id).addEventListener('input',renderActive)});
  document.getElementById('search2').addEventListener('input',renderRemoved);
  renderStats();renderActive();renderRemoved();
})();
</script>
</body>
</html>
"""


def main():
    active, removed = load()
    print(f"在库 {len(active)} 家 | 出库 {len(removed)} 家")
    total = sum(c["limit"] for c in active if c["limit"] is not None)
    print(f"授信总额 {total} 亿元")
    missing = [c["name"] for c in active if not c["prov"]]
    if missing:
        print("⚠️ 仍有缺省份:", missing)
    html = (HTML_TPL
            .replace("__ACTIVE__", json.dumps(active, ensure_ascii=False))
            .replace("__REMOVED__", json.dumps(removed, ensure_ascii=False)))
    OUT.write_text(html, encoding="utf-8")
    print("已生成", OUT)


if __name__ == "__main__":
    main()
