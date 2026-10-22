(function(){
  if(window.__namingFx) return;
  window.__namingFx = true;
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  var css = [
    ':root{--bg:#0b1118;--page:#0b1118;--paper:#0b1118;--paper2:#101720;--paper3:#151d26;--surf:#151d26;--panel:#151d26;--panel-hover:#1b2530;--card:#151d26;--ink:#f7f2e6;--ink2:#c9bfa8;--muted:#a99a78;--line:rgba(199,154,43,.22);--line-strong:rgba(199,154,43,.5);--jiang:#b23a2b;--red:#b23a2b;--gold:#c79a2b;--gold2:#e8c66a;--tai:#2d8f5f;--warn:#c07a1a;--blue:#2d5f8f;--cyan:#c79a2b;--violet:#e8c66a}',
    'html,body{background:#0d1218!important;color:#e9dfc8!important}',
    'body{background-image:radial-gradient(circle at 18% 18%,rgba(199,154,43,.10),transparent 38%),radial-gradient(circle at 82% 72%,rgba(178,58,43,.13),transparent 44%),radial-gradient(circle at 50% 110%,rgba(42,120,214,.08),transparent 50%)!important;background-attachment:fixed!important}',
    'header,main,section,.wrap,.page,.container,.content,.shell,.layout{background:transparent!important}',
    'h1,h2,h3,h4,h5,h6{color:#f7f2e6!important}',
    '.sub,.lede,.note,.muted,.hint,.desc,small,.meta,.foot,.footer p,.footnote{color:#a99a78!important}',
    'a{color:#e8c66a!important}',
    '.card,.quote-card,.topcard,.fcard,.panel,.stat,.chart-card,.chart,.chart-wrap,.tile,.egg,.name-card,.step,.scatter-wrap,.scatter-table,.glossary,.letter,.pillar,.mao-card,.bro-card,.link-card,.birth-grid div,.readout,.metric,.box,.item,.entry,.work,.archive-item,.result,.block,.summary,.intro,.gate,.node,.cell{background:#151d26!important;border-color:rgba(199,154,43,.22)!important;color:#c9bfa8!important;box-shadow:0 14px 36px rgba(0,0,0,.28)!important}',
    '.card h3,.quote-card .q,.topcard .n,.name-card h3,.mao-card h3,.bro-card h3,.stat b,.readout b,.step b{color:#f7f2e6!important}',
    'table{background:transparent!important;color:#c9bfa8!important}thead,tbody,tr{background:transparent!important}',
    'th,td{border-color:rgba(199,154,43,.18)!important;color:#c9bfa8!important}th{color:#f7f2e6!important}',
    '.tab{background:#151d26!important;color:#c9bfa8!important;border-color:rgba(199,154,43,.25)!important}.tab.on{background:#b23a2b!important;color:#fff!important;border-color:#b23a2b!important}',
    'button,.btn{background:#151d26!important;color:#e8c66a!important;border-color:rgba(199,154,43,.3)!important}',
    'input,select,textarea{background:#0f151c!important;color:#f7f2e6!important;border-color:rgba(199,154,43,.25)!important}',
    'svg text{fill:#c9bfa8!important}',
    '.section-head,.anchors,.topbar,.head{border-color:rgba(199,154,43,.2)!important}',
    '.brand em{background:linear-gradient(90deg,#c79a2b,#e8c66a)!important;-webkit-background-clip:text!important;background-clip:text!important;color:transparent!important}',
    '.logo{background:linear-gradient(135deg,#c79a2b,#e8c66a)!important;color:#1a1204!important;box-shadow:0 0 24px rgba(199,154,43,.25)!important}',
    '.bg-grid{opacity:.25!important;filter:sepia(1) saturate(.5)!important;z-index:-2!important}',
    '.naming-fx-glow{position:fixed;width:520px;height:520px;border-radius:50%;pointer-events:none;z-index:-1;opacity:0;transform:translate(-50%,-50%);transition:opacity .4s;background:radial-gradient(circle,rgba(232,198,106,.13),rgba(232,198,106,.04) 42%,transparent 68%);mix-blend-mode:screen}',
    '@media(hover:none){.naming-fx-glow{display:none}}',
    '.naming-fx-shoot{position:fixed;top:16%;right:12%;width:140px;height:1px;z-index:-1;pointer-events:none;background:linear-gradient(90deg,transparent,rgba(232,198,106,.9));opacity:0;transform:rotate(-32deg);animation:namingFxShoot 11s ease-in-out infinite}',
    '@keyframes namingFxShoot{0%,86%,100%{opacity:0;transform:translate(0,0) rotate(-32deg)}88%{opacity:.85}94%{opacity:0;transform:translate(-240px,150px) rotate(-32deg)}}',
    '.naming-fx-aurora{display:none!important}',
    '@keyframes namingFxAurora{from{transform:translate(-2%,-1%) scale(1)}to{transform:translate(2%,1%) scale(1.08)}}',
    '.naming-fx-dust{position:fixed;inset:0;z-index:-1;pointer-events:none;opacity:.75}',
    '.naming-fx-progress{position:fixed;top:0;left:0;height:2px;width:0;z-index:60;pointer-events:none;background:linear-gradient(90deg,#b23a2b,#c79a2b)}',
    '.naming-fx-spot{position:relative}',
    '.naming-fx-spot::after{content:"";position:absolute;inset:0;border-radius:inherit;pointer-events:none;opacity:.16;animation:namingFxBreath 7s ease-in-out infinite;transition:opacity .3s;background:radial-gradient(circle at var(--fx-x,50%) var(--fx-y,50%),rgba(199,154,43,.2),transparent 46%)}',
    '@keyframes namingFxBreath{0%,100%{opacity:.1}50%{opacity:.35}}',
    '.naming-fx-spot:hover::after{opacity:1;animation:none}',
    '@media(prefers-reduced-motion:reduce){.naming-fx-aurora{animation:none}.naming-fx-dust{display:none}}'
  ].join('\n');
  var st = document.createElement('style');
  st.textContent = css;
  document.head.appendChild(st);

  var aurora = document.createElement('div');
  aurora.className = 'naming-fx-aurora';
  document.body.appendChild(aurora);

  var bar = document.createElement('div');
  bar.className = 'naming-fx-progress';
  document.body.appendChild(bar);

  var glow = document.createElement('div');
  glow.className = 'naming-fx-glow';
  document.body.appendChild(glow);
  var shoot = document.createElement('span');
  shoot.className = 'naming-fx-shoot';
  document.body.appendChild(shoot);
  if(window.matchMedia && window.matchMedia('(hover:hover) and (pointer:fine)').matches){
    document.addEventListener('pointermove', function(e){
      glow.style.left = e.clientX + 'px';
      glow.style.top = e.clientY + 'px';
      glow.style.opacity = '1';
    }, {passive:true});
    document.addEventListener('mouseleave', function(){ glow.style.opacity = '0'; });
  }
  function onScroll(){
    var h = document.documentElement;
    var max = h.scrollHeight - h.clientHeight;
    var p = max > 0 ? (h.scrollTop || document.body.scrollTop) / max * 100 : 0;
    bar.style.width = p + '%';
  }
  window.addEventListener('scroll', onScroll, {passive:true});
  onScroll();

  if(!reduce){
    var canvas = document.createElement('canvas');
    canvas.className = 'naming-fx-dust';
    document.body.appendChild(canvas);
    var ctx = canvas.getContext('2d');
    var dpr = Math.min(2, window.devicePixelRatio || 1);
    var pts = [], dmx = -9999, dmy = -9999;
    function size(){
      var w = innerWidth, h = innerHeight;
      canvas.width = Math.max(1, Math.round(w * dpr));
      canvas.height = Math.max(1, Math.round(h * dpr));
      canvas.style.width = w + 'px';
      canvas.style.height = h + 'px';
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      var n = w < 700 ? 22 : 42;
      pts = [];
      for(var i=0;i<n;i++){
        pts.push({x:Math.random()*w, y:Math.random()*h,
          vy:0.07+Math.random()*0.16, vx:(Math.random()-.5)*0.04,
          r:Math.random()*1.8+0.5, a:0.18+Math.random()*0.34,
          ph:Math.random()*6.28});
      }
    }
    function draw(t){
      var w = innerWidth, h = innerHeight;
      ctx.clearRect(0,0,w,h);
      for(var i=0;i<pts.length;i++){
        var p = pts[i];
        p.y -= p.vy;
        p.x += p.vx + Math.sin(t/3200 + p.ph) * 0.07;
        if(p.y < -10){ p.y = h + 10; p.x = Math.random()*w; }
        if(p.x < -10){ p.x = w + 10; }
        if(p.x > w + 10){ p.x = -10; }
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI*2);
        ctx.fillStyle = 'rgba(199,154,43,' + p.a + ')';
        ctx.fill();
        for(var j=i+1;j<pts.length;j++){
          var q = pts[j], qx = p.x-q.x, qy = p.y-q.y, qd = qx*qx+qy*qy;
          if(qd < 120*120){
            ctx.beginPath(); ctx.moveTo(p.x,p.y); ctx.lineTo(q.x,q.y);
            ctx.strokeStyle = 'rgba(199,154,43,' + (0.08*(1-qd/(120*120))) + ')';
            ctx.lineWidth = .6; ctx.stroke();
          }
        }
        var mx = p.x-dmx, my = p.y-dmy, md = mx*mx+my*my;
        if(md < 170*170){
          ctx.beginPath(); ctx.moveTo(p.x,p.y); ctx.lineTo(dmx,dmy);
          ctx.strokeStyle = 'rgba(232,198,106,.08)'; ctx.lineWidth = .5; ctx.stroke();
        }
      }
      requestAnimationFrame(draw);
    }
    size();
    window.addEventListener('resize', size, {passive:true});
    document.addEventListener('pointermove', function(e){ dmx = e.clientX; dmy = e.clientY; }, {passive:true});
    document.addEventListener('pointerleave', function(){ dmx = -9999; dmy = -9999; });
    requestAnimationFrame(draw);
  }

  var fine = window.matchMedia && window.matchMedia('(hover:hover) and (pointer:fine)').matches;
  var els = document.querySelectorAll('.card, .quote-card, .topcard, .fcard, .stat, .chart-card, .tile');
  for(var i=0;i<els.length;i++){
    els[i].classList.add('naming-fx-spot');
    if(fine && !reduce){
      els[i].addEventListener('pointermove', function(e){
        var r = this.getBoundingClientRect();
        this.style.setProperty('--fx-x', ((e.clientX - r.left) / r.width * 100) + '%');
        this.style.setProperty('--fx-y', ((e.clientY - r.top) / r.height * 100) + '%');
      }, {passive:true});
    }
  }
})();
