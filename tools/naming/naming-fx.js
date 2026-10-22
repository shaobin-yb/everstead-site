(function(){
  if(window.__namingFx) return;
  window.__namingFx = true;
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  var css = [
    '.naming-fx-aurora{position:fixed;inset:-20%;z-index:50;pointer-events:none;opacity:.62;background:radial-gradient(circle at 22% 30%,rgba(199,154,43,.14),transparent 44%),radial-gradient(circle at 78% 70%,rgba(42,120,214,.10),transparent 46%);animation:namingFxAurora 26s ease-in-out infinite alternate}',
    '@keyframes namingFxAurora{from{transform:translate(-2%,-1%) scale(1)}to{transform:translate(2%,1%) scale(1.08)}}',
    '.naming-fx-dust{position:fixed;inset:0;z-index:51;pointer-events:none;opacity:.75}',
    '.naming-fx-progress{position:fixed;top:0;left:0;height:2px;width:0;z-index:60;pointer-events:none;background:linear-gradient(90deg,#b23a2b,#c79a2b)}',
    '.naming-fx-spot{position:relative}',
    '.naming-fx-spot::after{content:"";position:absolute;inset:0;border-radius:inherit;pointer-events:none;opacity:0;transition:opacity .3s;background:radial-gradient(circle at var(--fx-x,50%) var(--fx-y,50%),rgba(199,154,43,.2),transparent 46%)}',
    '.naming-fx-spot:hover::after{opacity:1}',
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
    var pts = [];
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
      }
      requestAnimationFrame(draw);
    }
    size();
    window.addEventListener('resize', size, {passive:true});
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
