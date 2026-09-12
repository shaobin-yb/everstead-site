/* ============================================================
   全站悬浮导航 FAB · 2026-09-12
   每个页面右下角: ← 返回上一步(history.back, 无历史时回首页) + 🏠 返回首页
   首页本身不显示; 由 inject_nav.py 自动注入到所有 html
   ============================================================ */
(function () {
  if (window.__fabNavInjected) return;
  window.__fabNavInjected = true;

  var p = location.pathname;
  if (p === '/' || p === '' || /^\/index\.html$/i.test(p)) return; // 已在首页

  // 按页面深度计算回到站点根目录的相对前缀
  var segs = p.split('/').filter(Boolean);
  var rel = new Array(segs.length).join('../'); // n 段 → n-1 层 ../
  var home = rel + 'index.html';

  var css = document.createElement('style');
  css.textContent =
    '#fab-nav{position:fixed;right:14px;bottom:16px;z-index:99999;display:flex;gap:8px;' +
    'font-family:"Microsoft YaHei","PingFang SC","Helvetica Neue",sans-serif}' +
    '#fab-nav button{display:flex;align-items:center;gap:6px;padding:8px 14px;border-radius:999px;' +
    'border:1px solid rgba(56,189,248,.45);background:rgba(7,16,33,.92);color:#e2ecf7;font-size:13px;' +
    'cursor:pointer;box-shadow:0 4px 18px rgba(0,0,0,.45),0 0 12px rgba(34,211,238,.12);' +
    'backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);transition:all .2s}' +
    '#fab-nav button:hover{border-color:#22d3ee;color:#22d3ee;box-shadow:0 4px 20px rgba(0,0,0,.5),0 0 16px rgba(34,211,238,.3)}' +
    '#fab-nav button:active{transform:scale(.96)}' +
    '#fab-nav .i{font-size:14px;font-weight:700;font-family:"JetBrains Mono","Cascadia Mono","Consolas",monospace}' +
    '#fab-nav .t{letter-spacing:.06em}';
  document.head.appendChild(css);

  var el = document.createElement('div');
  el.id = 'fab-nav';
  el.innerHTML =
    '<button id="fab-back" title="返回上一步">' +
      '<span class="i">←</span><span class="t">返回</span></button>' +
    '<button id="fab-home" title="返回首页">' +
      '<span class="i">🏠</span><span class="t">首页</span></button>';
  document.body.appendChild(el);

  document.getElementById('fab-back').addEventListener('click', function () {
    if (window.history.length > 1) { history.back(); }
    else { location.href = home; } // 新标签页直开, 无历史可退 → 回首页
  });
  document.getElementById('fab-home').addEventListener('click', function () {
    location.href = home;
  });
})();
