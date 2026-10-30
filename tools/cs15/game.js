/* ============================================================
   Counter-Strike 1.5 · 单机人机版（浏览器复刻）
   纯本地运行：three.min.js + 本文件，无需联网
   ============================================================ */
(function () {
'use strict';

// ---------------- 工具 ----------------
const $ = (id) => document.getElementById(id);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const lerp = (a, b, t) => a + (b - a) * t;
const rand = (a, b) => a + Math.random() * (b - a);
const irand = (a, b) => Math.floor(rand(a, b + 1));
const angleDiff = (a, b) => {
  let d = b - a;
  while (d > Math.PI) d -= Math.PI * 2;
  while (d < -Math.PI) d += Math.PI * 2;
  return d;
};
const nowS = () => performance.now() / 1000;
const schedule = (fn, ms) => setTimeout(fn, ms);

window.__errors = [];
window.addEventListener('error', (e) => {
  window.__errors.push(String((e && e.message) || e));
  if (window.__errors.length > 20) window.__errors.shift();
});

if (typeof THREE === 'undefined') {
  document.body.innerHTML =
    '<div style="color:#fff;font:16px Microsoft YaHei;padding:60px;line-height:2">' +
    'three.min.js 未能加载。请确认 index.html 与 three.min.js 在同一目录。' +
    '</div>';
  return;
}
if (THREE.ColorManagement) THREE.ColorManagement.legacyMode = false;

// ---------------- 私人密码门（本地自动跳过；站点与私人专区共用密码） ----------------
(function initGate() {
  const gate = document.getElementById('csgate');
  if (!gate) return;
  const host = location.hostname;
  const local = location.protocol === 'file:' || host === 'localhost' || host === '127.0.0.1' || host === '::1' || host === '';
  try {
    if (local || sessionStorage.getItem('private_ok') === '1') { gate.remove(); return; }
  } catch (e) {
    gate.remove();
    return;
  }
  const GATE_HASH = 'a68afcaa33dc88de7217371b041b422543aa16e2958365dde8112487475e37cd';
  const pw = document.getElementById('gatePw');
  const btn = document.getElementById('gateBtn');
  const err = document.getElementById('gateErr');
  async function sha256(text) {
    const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
    return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, '0')).join('');
  }
  let busy = false;
  async function submit() {
    if (busy) return;
    const v = pw.value.trim();
    if (!v) { pw.focus(); return; }
    busy = true;
    try {
      if (await sha256(v) === GATE_HASH) {
        sessionStorage.setItem('private_ok', '1');
        gate.remove();
        pw.value = '';
      } else {
        err.textContent = '密码不对，再试一次';
        pw.select();
      }
    } catch (e) {
      err.textContent = '当前环境无法校验密码';
    }
    busy = false;
  }
  btn.addEventListener('click', submit);
  pw.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); submit(); }
  });
  setTimeout(() => { try { pw.focus(); } catch (e) {} }, 80);
})();

// ---------------- 设置 ----------------
const SETTINGS_KEY = 'cs15.settings.v1';
const S = { team: 't', diff: 'vet', sens: 0.0022, vol: 0.7 };
try {
  const raw = localStorage.getItem(SETTINGS_KEY);
  if (raw) Object.assign(S, JSON.parse(raw));
} catch (e) { /* 忽略 */ }
function saveSettings() {
  try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(S)); } catch (e) {}
}

const DIFF = {
  rookie: { reaction: 0.7,  err: 3.2, burstMin: 2, burstMax: 3, fireCdMin: 1.6, fireCdMax: 2.4, speed: 3.0, dmgMin: 6,  dmgMax: 9 },
  vet:    { reaction: 0.5,  err: 2.2, burstMin: 3, burstMax: 4, fireCdMin: 1.25, fireCdMax: 1.95, speed: 3.5, dmgMin: 7,  dmgMax: 10 },
  elite:  { reaction: 0.3,  err: 1.4, burstMin: 4, burstMax: 5, fireCdMin: 0.95, fireCdMax: 1.55, speed: 3.9, dmgMin: 9, dmgMax: 12 }
};

// ---------------- 音效（Web Audio 合成，无外部资源） ----------------
const Sound = (() => {
  let ctx = null, master = null, noiseBuf = null;
  function init() {
    if (ctx) { if (ctx.state === 'suspended') ctx.resume(); return; }
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    ctx = new AC();
    master = ctx.createGain();
    master.gain.value = S.vol;
    master.connect(ctx.destination);
    const len = Math.floor(ctx.sampleRate * 1.0);
    noiseBuf = ctx.createBuffer(1, len, ctx.sampleRate);
    const data = noiseBuf.getChannelData(0);
    for (let i = 0; i < len; i++) data[i] = Math.random() * 2 - 1;
  }
  function noise(dur, freq, q, gain, type) {
    if (!ctx) return;
    const t = ctx.currentTime;
    const src = ctx.createBufferSource();
    src.buffer = noiseBuf;
    const f = ctx.createBiquadFilter();
    f.type = type || 'bandpass';
    f.frequency.value = freq;
    f.Q.value = q;
    const g = ctx.createGain();
    g.gain.setValueAtTime(Math.max(0.0001, gain), t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    src.connect(f); f.connect(g); g.connect(master);
    src.start(t); src.stop(t + dur + 0.05);
  }
  function tone(freq, dur, gain, type, slideTo) {
    if (!ctx) return;
    const t = ctx.currentTime;
    const o = ctx.createOscillator();
    o.type = type || 'sine';
    o.frequency.setValueAtTime(Math.max(10, freq), t);
    if (slideTo) o.frequency.exponentialRampToValueAtTime(Math.max(10, slideTo), t + dur);
    const g = ctx.createGain();
    g.gain.setValueAtTime(Math.max(0.0001, gain), t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g); g.connect(master);
    o.start(t); o.stop(t + dur + 0.05);
  }
  function shot(kind, scale) {
    const v = scale === undefined ? 1 : scale;
    if (kind === 'awp') {
      noise(0.42, 520, 0.6, 0.5 * v);
      noise(0.06, 2600, 1, 0.28 * v, 'highpass');
      tone(72, 0.36, 0.42 * v, 'triangle', 36);
    } else if (kind === 'deagle') {
      noise(0.2, 720, 0.7, 0.42 * v);
      tone(96, 0.17, 0.34 * v, 'triangle', 44);
    } else if (kind === 'pistol') {
      noise(0.12, 1200, 0.8, 0.3 * v);
      tone(120, 0.1, 0.24 * v, 'triangle', 55);
    } else {
      noise(0.15, kind === 'm4' ? 1150 : 880, 0.85, 0.4 * v);
      noise(0.03, 3000, 1, 0.16 * v, 'highpass');
      tone(104, 0.12, 0.28 * v, 'triangle', 46);
    }
  }
  return {
    init,
    setVol(v) {
      S.vol = v;
      saveSettings();
      if (master) master.gain.value = v;
    },
    shot,
    botShot(dist) { shot('rifle', clamp(0.62 - dist / 110, 0.06, 0.4)); },
    step(v) { noise(0.05, 330 + Math.random() * 160, 1.4, 0.05 * v); },
    hit() { tone(1450, 0.05, 0.16, 'square'); },
    headshot() { tone(2350, 0.09, 0.2, 'sine', 1700); tone(3200, 0.06, 0.09, 'sine'); },
    empty() { tone(1800, 0.02, 0.1, 'square'); noise(0.04, 2200, 2, 0.08); },
    reload() {
      noise(0.04, 1300, 2, 0.14);
      setTimeout(() => { if (ctx) { noise(0.05, 900, 2, 0.16); tone(500, 0.05, 0.08, 'square'); } }, 190);
    },
    buy() {
      tone(880, 0.06, 0.13, 'square');
      setTimeout(() => { if (ctx) { tone(1320, 0.09, 0.11, 'square'); } }, 70);
    },
    deny() { tone(170, 0.16, 0.16, 'sawtooth', 120); },
    death() { tone(110, 0.35, 0.24, 'sine', 42); noise(0.18, 250, 1, 0.14); },
    win() {
      tone(523, 0.12, 0.13, 'triangle');
      setTimeout(() => { if (ctx) tone(659, 0.12, 0.13, 'triangle'); }, 110);
      setTimeout(() => { if (ctx) tone(784, 0.22, 0.14, 'triangle'); }, 220);
    },
    lose() { tone(200, 0.4, 0.2, 'sawtooth', 90); tone(140, 0.5, 0.16, 'triangle', 60); },
    ui() { tone(600, 0.04, 0.06, 'square'); }
  };
})();

// ---------------- 渲染基础 ----------------
const canvas = $('game');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
if ('outputEncoding' in renderer && THREE.sRGBEncoding) renderer.outputEncoding = THREE.sRGBEncoding;
if ('toneMapping' in renderer) {
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 0.84;
}
if ('useLegacyLights' in renderer) renderer.useLegacyLights = true;

const scene = new THREE.Scene();
scene.fog = new THREE.Fog(0xd6cbaa, 45, 160);
const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.05, 400);
scene.add(camera);

// 天空
function skyTexture() {
  const cv = document.createElement('canvas');
  cv.width = 4; cv.height = 256;
  const g = cv.getContext('2d');
  const grd = g.createLinearGradient(0, 0, 0, 256);
  grd.addColorStop(0, '#5f93bd');
  grd.addColorStop(0.45, '#9fc0d8');
  grd.addColorStop(0.62, '#d8d3bd');
  grd.addColorStop(1, '#ecdfc2');
  g.fillStyle = grd; g.fillRect(0, 0, 4, 256);
  const t = new THREE.CanvasTexture(cv);
  if (THREE.sRGBEncoding) t.encoding = THREE.sRGBEncoding;
  return t;
}
const sky = new THREE.Mesh(
  new THREE.SphereGeometry(260, 24, 16),
  new THREE.MeshBasicMaterial({ map: skyTexture(), side: THREE.BackSide, fog: false, depthWrite: false, toneMapped: false })
);
scene.add(sky);

const hemi = new THREE.HemisphereLight(0xbfd6ea, 0x8b7452, 0.9);
scene.add(hemi);
const sun = new THREE.DirectionalLight(0xffeac2, 1.15);
sun.position.set(38, 58, 24);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.camera.left = -48;
sun.shadow.camera.right = 48;
sun.shadow.camera.top = 48;
sun.shadow.camera.bottom = -48;
sun.shadow.camera.near = 5;
sun.shadow.camera.far = 160;
sun.shadow.bias = -0.0006;
sun.shadow.camera.updateProjectionMatrix();
scene.add(sun);
const fillLight = new THREE.DirectionalLight(0xffd9b0, 0.35);
fillLight.position.set(-30, 20, -25);
scene.add(fillLight);

// ---------------- 程序化贴图 ----------------
function makeTex(w, h, draw, rx, ry) {
  const cv = document.createElement('canvas');
  cv.width = w; cv.height = h;
  const g = cv.getContext('2d');
  draw(g, w, h);
  const t = new THREE.CanvasTexture(cv);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(rx || 1, ry || 1);
  t.anisotropy = 4;
  if (THREE.sRGBEncoding) t.encoding = THREE.sRGBEncoding;
  return t;
}

const texWall = makeTex(256, 256, (g) => {
  g.fillStyle = '#bda578'; g.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 11000; i++) {
    const x = Math.random() * 256, y = Math.random() * 256;
    g.fillStyle = Math.random() < 0.5 ? 'rgba(88,70,46,0.13)' : 'rgba(255,246,216,0.10)';
    g.fillRect(x, y, 1.6, 1.6);
  }
  for (let i = 0; i < 12; i++) {
    g.fillStyle = 'rgba(120,98,64,0.06)';
    g.fillRect(0, Math.random() * 256, 256, 2 + Math.random() * 7);
  }
  for (let i = 0; i < 5; i++) {
    g.strokeStyle = 'rgba(96,78,50,0.16)';
    g.lineWidth = 1;
    g.beginPath();
    let x = Math.random() * 256, y = Math.random() * 256;
    g.moveTo(x, y);
    for (let k = 0; k < 4; k++) { x += rand(-14, 14); y += rand(4, 20); g.lineTo(x, y); }
    g.stroke();
  }
}, 8, 3);

const texGround = makeTex(512, 512, (g) => {
  g.fillStyle = '#b79f6f'; g.fillRect(0, 0, 512, 512);
  for (let i = 0; i < 16000; i++) {
    const x = Math.random() * 512, y = Math.random() * 512;
    g.fillStyle = Math.random() < 0.5 ? 'rgba(92,74,48,0.10)' : 'rgba(255,244,208,0.09)';
    g.fillRect(x, y, 2, 2);
  }
  for (let i = 0; i < 26; i++) {
    g.fillStyle = 'rgba(128,104,66,' + rand(0.03, 0.09).toFixed(3) + ')';
    g.beginPath();
    g.ellipse(Math.random() * 512, Math.random() * 512, rand(18, 70), rand(10, 40), Math.random() * Math.PI, 0, Math.PI * 2);
    g.fill();
  }
  for (let i = 0; i < 220; i++) {
    g.fillStyle = Math.random() < 0.5 ? 'rgba(70,58,40,0.5)' : 'rgba(220,208,176,0.5)';
    g.fillRect(Math.random() * 512, Math.random() * 512, rand(1.5, 3.5), rand(1.5, 3));
  }
}, 16, 16);

const texCrate = makeTex(256, 256, (g) => {
  g.fillStyle = '#a87c46'; g.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 5; i++) {
    g.fillStyle = i % 2 ? '#9a7040' : '#b0854c';
    g.fillRect(0, i * 52, 256, 50);
  }
  g.strokeStyle = 'rgba(90,62,30,0.5)'; g.lineWidth = 1.5;
  for (let i = 0; i < 90; i++) {
    g.beginPath();
    const y = Math.random() * 256;
    g.moveTo(0, y); g.lineTo(256, y + rand(-3, 3));
    g.stroke();
  }
  g.strokeStyle = '#6f4c26'; g.lineWidth = 13;
  g.strokeRect(7, 7, 242, 242);
  g.strokeStyle = 'rgba(60,40,20,0.55)'; g.lineWidth = 2;
  g.strokeRect(15, 15, 226, 226);
  g.fillStyle = '#4c3418';
  [[25, 25], [231, 25], [25, 231], [231, 231], [128, 25], [25, 128], [231, 128]].forEach((p) => {
    g.beginPath(); g.arc(p[0], p[1], 3.2, 0, Math.PI * 2); g.fill();
  });
  for (let i = 0; i < 1800; i++) {
    g.fillStyle = Math.random() < 0.5 ? 'rgba(120,86,44,0.12)' : 'rgba(255,226,170,0.08)';
    g.fillRect(Math.random() * 256, Math.random() * 256, 1.4, 1.4);
  }
}, 1, 1);

const texDecal = makeTex(64, 64, (g) => {
  const grd = g.createRadialGradient(32, 32, 2, 32, 32, 30);
  grd.addColorStop(0, 'rgba(8,7,6,0.95)');
  grd.addColorStop(0.55, 'rgba(12,10,8,0.8)');
  grd.addColorStop(1, 'rgba(20,16,12,0)');
  g.fillStyle = grd; g.fillRect(0, 0, 64, 64);
});

const texBlood = makeTex(64, 64, (g) => {
  const grd = g.createRadialGradient(32, 32, 2, 32, 32, 30);
  grd.addColorStop(0, 'rgba(190,20,16,0.95)');
  grd.addColorStop(0.5, 'rgba(140,12,10,0.6)');
  grd.addColorStop(1, 'rgba(90,8,6,0)');
  g.fillStyle = grd; g.fillRect(0, 0, 64, 64);
});

const texFlash = makeTex(64, 64, (g) => {
  const grd = g.createRadialGradient(32, 32, 1, 32, 32, 30);
  grd.addColorStop(0, 'rgba(255,255,230,1)');
  grd.addColorStop(0.25, 'rgba(255,220,130,0.95)');
  grd.addColorStop(0.6, 'rgba(255,150,50,0.45)');
  grd.addColorStop(1, 'rgba(255,120,20,0)');
  g.fillStyle = grd; g.fillRect(0, 0, 64, 64);
});
texFlash.wrapS = texFlash.wrapT = THREE.ClampToEdgeWrapping;

// ---------------- 游戏状态 ----------------
const G = {
  state: 'menu', paused: false, dead: false, buyOpen: false, roundEnding: false,
  round: 0, roundId: 0, roundKills: 0,
  money: 800, kills: 0, deaths: 0, headshots: 0, shots: 0, hits: 0,
  bots: [], freezeUntil: 0, pendingRound: false
};

const WDEF = {
  ak47:   { name: 'AK-47',    slot: 'primary', dmg: 36,  rpm: 600, auto: true,  mag: 30, reserve: 90,  reload: 2.5, spread: 0.0075, moveSpread: 0.03,  recoilV: 0.0115, recoilH: 0.005, sound: 'rifle',  price: 2500 },
  m4:     { name: 'M4A1',     slot: 'primary', dmg: 33,  rpm: 666, auto: true,  mag: 30, reserve: 90,  reload: 3.0, spread: 0.0068, moveSpread: 0.028, recoilV: 0.0095, recoilH: 0.004, sound: 'm4',     price: 3100 },
  awp:    { name: 'AWP',      slot: 'primary', dmg: 115, rpm: 41,  auto: false, mag: 10, reserve: 30,  reload: 3.6, spread: 0.02,   moveSpread: 0.06,  recoilV: 0.05,   recoilH: 0.01,  sound: 'awp',    price: 4750 },
  deagle: { name: '沙漠之鹰', slot: 'pistol',  dmg: 54,  rpm: 267, auto: false, mag: 7,  reserve: 35,  reload: 2.2, spread: 0.009,  moveSpread: 0.035, recoilV: 0.026,  recoilH: 0.008, sound: 'deagle', price: 650 },
  usp:    { name: 'USP',      slot: 'pistol',  dmg: 34,  rpm: 400, auto: false, mag: 12, reserve: 100, reload: 2.2, spread: 0.011,  moveSpread: 0.03,  recoilV: 0.013,  recoilH: 0.005, sound: 'pistol', price: 200 },
  glock:  { name: 'GLOCK-18', slot: 'pistol',  dmg: 28,  rpm: 400, auto: false, mag: 20, reserve: 120, reload: 2.2, spread: 0.013,  moveSpread: 0.03,  recoilV: 0.011,  recoilH: 0.005, sound: 'pistol', price: 400 }
};

const loadout = { primary: null, pistol: null, current: 'pistol' };
function makeWeapon(id) {
  const d = WDEF[id];
  return { id, ammo: d.mag, reserve: d.reserve };
}
function currentWeapon() { return loadout[loadout.current]; }
function weaponDef() { const w = currentWeapon(); return w ? WDEF[w.id] : null; }

// ---------------- 玩家 ----------------
const player = {
  pos: new THREE.Vector3(0, 0, -23.2),
  vel: new THREE.Vector3(),
  yaw: Math.PI, pitch: 0,
  health: 100, armor: 0,
  grounded: true, crouch: false,
  height: 1.78, curEye: 1.63,
  dead: false, stepPhase: 0, stepT: 0
};

let reloading = false, reloadEnd = 0, nextFire = 0;
let mouseDown = false, scopeOn = false, switchT = 0, bloom = 0, vmKick = 0;
let flashUntil = 0, shake = 0, dmgFlashT = 0, hitmarkerTimer = null;
let lastGap = '';
const keys = {};

// ---------------- 世界 ----------------
const colliders = [];
const worldMeshes = [];

function addBox(x, y, z, w, h, d, mat, opt) {
  opt = opt || {};
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
  mesh.position.set(x, y + h / 2, z);
  mesh.castShadow = opt.shadow !== false;
  mesh.receiveShadow = true;
  scene.add(mesh);
  worldMeshes.push(mesh);
  if (opt.solid !== false) {
    colliders.push({ minX: x - w / 2, maxX: x + w / 2, minY: y, maxY: y + h, minZ: z - d / 2, maxZ: z + d / 2 });
  }
  return mesh;
}

const texSandbag = makeTex(256, 128, (g) => {
  g.fillStyle = '#8a7749'; g.fillRect(0, 0, 256, 128);
  for (let row = 0; row < 3; row++) {
    for (let col = -1; col < 5; col++) {
      const x = col * 64 + (row % 2 ? 32 : 0) + 32;
      const y = row * 40 + 22;
      g.fillStyle = row % 2 ? '#9d8a58' : '#94804f';
      g.beginPath();
      g.ellipse(x, y, 33, 18, 0, 0, Math.PI * 2);
      g.fill();
      g.strokeStyle = 'rgba(70,56,28,0.35)'; g.lineWidth = 1.5;
      g.stroke();
      g.strokeStyle = 'rgba(230,214,170,0.10)'; g.lineWidth = 1;
      g.beginPath();
      g.ellipse(x, y - 4, 26, 11, 0, Math.PI, Math.PI * 2);
      g.stroke();
    }
  }
}, 4, 1.5);

const MAT = {
  wall: new THREE.MeshStandardMaterial({ map: texWall, roughness: 0.95 }),
  wallDark: new THREE.MeshStandardMaterial({ color: 0xb59d70, roughness: 0.95 }),
  trim: new THREE.MeshStandardMaterial({ color: 0x8d7852, roughness: 0.95 }),
  crate: new THREE.MeshStandardMaterial({ map: texCrate, roughness: 0.85 }),
  sandbag: new THREE.MeshStandardMaterial({ map: texSandbag, roughness: 1 }),
  cloth: new THREE.MeshStandardMaterial({ color: 0xa8461f, roughness: 0.9, side: THREE.DoubleSide }),
  metal: new THREE.MeshStandardMaterial({ color: 0x4d5a4c, roughness: 0.6, metalness: 0.3 })
};

const SPAWNS = {
  t: [[-22, -22], [-8, -23], [0, -22.5], [8, -23], [22, -22], [18, -18], [-18, -18]],
  ct: [[-22, 22], [-8, 23], [0, 22.5], [8, 23], [22, 22], [18, 18], [-18, 18]]
};

function buildMap() {
  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(150, 150),
    new THREE.MeshStandardMaterial({ map: texGround, roughness: 1 })
  );
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  scene.add(ground);
  worldMeshes.push(ground);

  const H = 7.5;
  // 边界墙
  addBox(0, 0, -27.5, 70, H, 1.6, MAT.wall);
  addBox(0, 0, 27.5, 70, H, 1.6, MAT.wall);
  addBox(-34, 0, 0, 1.6, H, 56.6, MAT.wall);
  addBox(34, 0, 0, 1.6, H, 56.6, MAT.wall);
  // 墙顶压边（装饰）
  addBox(0, H, -27.5, 70.8, 0.4, 2.1, MAT.trim, { solid: false });
  addBox(0, H, 27.5, 70.8, 0.4, 2.1, MAT.trim, { solid: false });
  addBox(-34, H, 0, 2.1, 0.4, 57.2, MAT.trim, { solid: false });
  addBox(34, H, 0, 2.1, 0.4, 57.2, MAT.trim, { solid: false });
  // 墙基踢脚线（装饰）
  addBox(0, 0, -26.55, 70, 0.55, 0.3, MAT.trim, { solid: false });
  addBox(0, 0, 26.55, 70, 0.55, 0.3, MAT.trim, { solid: false });
  addBox(-33.05, 0, 0, 0.3, 0.55, 56.6, MAT.trim, { solid: false });
  addBox(33.05, 0, 0, 0.3, 0.55, 56.6, MAT.trim, { solid: false });
  // 墙垛（装饰，增加层次）
  for (let x = -30; x <= 30; x += 10) {
    addBox(x, 0, -26.7, 1.0, 6.0, 0.55, MAT.wallDark, { solid: false });
    addBox(x, 0, 26.7, 1.0, 6.0, 0.55, MAT.wallDark, { solid: false });
    addBox(x, 6.0, -26.7, 1.25, 0.3, 0.8, MAT.trim, { solid: false });
    addBox(x, 6.0, 26.7, 1.25, 0.3, 0.8, MAT.trim, { solid: false });
  }
  for (let z = -20; z <= 20; z += 10) {
    addBox(-33.2, 0, z, 0.55, 6.0, 1.0, MAT.wallDark, { solid: false });
    addBox(33.2, 0, z, 0.55, 6.0, 1.0, MAT.wallDark, { solid: false });
    addBox(-33.2, 6.0, z, 0.8, 0.3, 1.25, MAT.trim, { solid: false });
    addBox(33.2, 6.0, z, 0.8, 0.3, 1.25, MAT.trim, { solid: false });
  }

  const crate = (x, z, s, y) => addBox(x, y || 0, z, s, s, s, MAT.crate);
  const stack = (x, z, s1, s2) => { crate(x, z, s1); crate(x + 0.08, z - 0.06, s2, s1); };
  const sandbag = (x, z, w, d) => addBox(x, 0, z, w, 1.0, d, MAT.sandbag);
  const barrel = (x, z) => {
    const m = new THREE.Mesh(new THREE.CylinderGeometry(0.42, 0.42, 1.05, 14), MAT.metal);
    m.position.set(x, 0.525, z);
    m.castShadow = true; m.receiveShadow = true;
    scene.add(m); worldMeshes.push(m);
    colliders.push({ minX: x - 0.36, maxX: x + 0.36, minY: 0, maxY: 1.05, minZ: z - 0.36, maxZ: z + 0.36 });
  };
  const awning = (x, y, z, w, rotY) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, 4.4), MAT.cloth);
    m.position.set(x, y, z);
    m.rotation.set(-1.22, rotY || 0, 0);
    m.receiveShadow = true;
    scene.add(m);
  };

  // 北侧（T 出生点附近）
  crate(-14, -21, 1.8);
  crate(14, -21, 1.8);
  sandbag(-5.5, -18, 4.2, 0.95);
  sandbag(5.5, -18, 4.2, 0.95);

  // 中路
  stack(0, -3.2, 2.0, 1.3);
  crate(2.7, -5.4, 1.6);
  stack(-2.7, -5.9, 1.8, 1.1);
  crate(7.6, -1.0, 1.8);

  // 拱门
  addBox(-9.5, 0, 2.2, 1.25, 4.3, 1.25, MAT.wall);
  addBox(-4.5, 0, 2.2, 1.25, 4.3, 1.25, MAT.wall);
  addBox(-7.0, 4.3, 2.2, 6.4, 0.95, 1.45, MAT.wallDark);
  addBox(-7.0, 5.25, 2.2, 6.9, 0.35, 1.7, MAT.trim, { solid: false });

  // 西巷墙（留门洞）
  addBox(-15.5, 0, -8, 1.4, 5.2, 9, MAT.wall);
  addBox(-15.5, 0, 3.2, 1.4, 5.2, 7.2, MAT.wall);
  crate(-20.6, -4.2, 1.8);
  crate(-21.0, -5.8, 1.2, 1.8);
  barrel(-24, 1.0);
  barrel(-22.8, 1.7);
  awning(-25, 4.6, 4, 7.5, 0.3);

  // 东巷墙
  addBox(16.6, 0, -4, 1.4, 5.2, 9, MAT.wall);
  addBox(16.6, 0, 9.2, 1.4, 5.2, 7.2, MAT.wall);

  // 东侧 A 点
  stack(24.2, -1.5, 1.8, 1.5);
  crate(26.6, 2.6, 1.7);
  crate(21.0, 3.0, 1.3);
  sandbag(22.0, 6.6, 6.2, 0.95);
  crate(28.6, -7.0, 1.8);

  // 南侧（CT 出生点附近）
  sandbag(-5.0, 16.6, 5.2, 0.95);
  crate(12.0, 20.2, 1.8);
  crate(-12.6, 19.6, 1.8);
  crate(-8.2, 11.0, 1.6);
  crate(6.0, 10.2, 1.75);

  // 中南部
  crate(0.4, 9.0, 1.9);
  crate(-2.2, 7.0, 1.2);
  crate(3.4, 6.6, 1.05);
  barrel(13.2, 8.2);
  awning(21.5, 4.4, -17.5, 6.5, -0.4);

  // 远景小物
  crate(-28.5, -14.5, 1.6);
  crate(-29.6, -13.0, 1.1, 1.6);
}

buildMap();

// 雷达底图
const radarImg = (() => {
  const cv = document.createElement('canvas');
  cv.width = 168; cv.height = 140;
  const g = cv.getContext('2d');
  g.fillStyle = '#10150e'; g.fillRect(0, 0, 168, 140);
  const sx = 168 / 72, sz = 140 / 60;
  for (const c of colliders) {
    const x = (c.minX + 36) * sx;
    const y = (c.minZ + 30) * sz;
    const w = Math.max(1, (c.maxX - c.minX) * sx);
    const h = Math.max(1, (c.maxZ - c.minZ) * sz);
    const tall = (c.maxY - c.minY) > 4;
    g.fillStyle = tall ? 'rgba(138,120,82,0.85)' : 'rgba(178,148,96,0.82)';
    g.fillRect(x, y, w, h);
  }
  g.strokeStyle = 'rgba(255,255,255,0.12)';
  g.strokeRect(1, 1, 166, 138);
  return cv;
})();

function drawRadar() {
  const g = $('radar').getContext('2d');
  g.clearRect(0, 0, 168, 140);
  g.drawImage(radarImg, 0, 0);
  const sx = 168 / 72, sz = 140 / 60;
  for (const b of G.bots) {
    if (!b.alive) continue;
    if (Math.hypot(b.pos.x - player.pos.x, b.pos.z - player.pos.z) > 45) continue;
    const x = (b.pos.x + 36) * sx;
    const y = (b.pos.z + 30) * sz;
    g.fillStyle = b.canSee ? '#ff4b4b' : 'rgba(255,75,75,0.42)';
    g.beginPath();
    g.arc(x, y, b.canSee ? 3.2 : 2.4, 0, Math.PI * 2);
    g.fill();
  }
  const px = (player.pos.x + 36) * sx;
  const py = (player.pos.z + 30) * sz;
  g.save();
  g.translate(px, py);
  g.rotate(-player.yaw);
  g.fillStyle = '#f4f1e8';
  g.beginPath();
  g.moveTo(0, -5.5); g.lineTo(3.6, 4); g.lineTo(0, 1.8); g.lineTo(-3.6, 4);
  g.closePath(); g.fill();
  g.restore();
}

// ---------------- 第一人称武器模型 ----------------
function makeVMMat(color, rough, metal) {
  return new THREE.MeshStandardMaterial({
    color,
    roughness: rough === undefined ? 0.6 : rough,
    metalness: metal === undefined ? 0.35 : metal,
    depthTest: false, depthWrite: false, fog: false
  });
}
function vbox(parent, w, h, d, x, y, z, mat, rx, ry, rz) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
  m.position.set(x, y, z);
  m.rotation.set(rx || 0, ry || 0, rz || 0);
  m.renderOrder = 995;
  parent.add(m);
  return m;
}
function vcyl(parent, r, len, x, y, z, mat) {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, len, 10), mat);
  m.rotation.x = Math.PI / 2;
  m.position.set(x, y, z);
  m.renderOrder = 995;
  parent.add(m);
  return m;
}

const vmRoot = new THREE.Group();
vmRoot.position.set(0.25, -0.25, -0.5);
camera.add(vmRoot);

const vmLight = new THREE.PointLight(0xffe6bd, 0.4, 5);
vmLight.position.set(0.3, 0.3, 0.2);
camera.add(vmLight);

const flashSprite = new THREE.Sprite(new THREE.SpriteMaterial({
  map: texFlash, transparent: true, depthTest: false, depthWrite: false,
  blending: THREE.AdditiveBlending
}));
flashSprite.scale.set(0.26, 0.26, 1);
flashSprite.visible = false;
flashSprite.renderOrder = 1001;
vmRoot.add(flashSprite);

const muzzleLight = new THREE.PointLight(0xffc06a, 0, 8, 2);
muzzleLight.position.set(0.2, -0.1, -0.7);
camera.add(muzzleLight);

let vmGun = null;
let vmBase = new THREE.Vector3(0.25, -0.25, -0.5);
let vmMuzzle = new THREE.Vector3(0, 0.03, -0.55);

function buildGun(id) {
  const group = new THREE.Group();
  const metal = makeVMMat(0x24262a, 0.38, 0.6);
  const black = makeVMMat(0x15161a, 0.5, 0.45);
  const wood = makeVMMat(0x5c3a1e, 0.82, 0.05);
  const olive = makeVMMat(0x39422f, 0.8, 0.1);
  const silver = makeVMMat(0x8f949c, 0.32, 0.8);
  const glove = makeVMMat(0x1d1e20, 0.85, 0.05);
  const muzzle = new THREE.Vector3(0, 0.03, -0.5);

  if (id === 'ak47') {
    vbox(group, 0.07, 0.085, 0.42, 0, 0.015, 0, metal);
    vcyl(group, 0.013, 0.34, 0, 0.035, -0.36, metal);
    vbox(group, 0.05, 0.05, 0.1, 0, 0.06, -0.26, metal);
    vbox(group, 0.062, 0.07, 0.2, 0, 0.005, -0.22, wood);
    vbox(group, 0.055, 0.08, 0.25, 0, -0.02, 0.33, wood, 0.06);
    vbox(group, 0.05, 0.15, 0.085, 0, -0.09, 0.06, metal, 0.3);
    vbox(group, 0.045, 0.12, 0.055, 0, -0.085, 0.17, wood, -0.32);
    vbox(group, 0.02, 0.05, 0.02, 0, 0.09, -0.42, metal);
    vbox(group, 0.03, 0.018, 0.06, 0, 0.072, 0.1, metal);
    vbox(group, 0.075, 0.07, 0.11, 0.012, -0.115, 0.15, glove, 0.15);
    muzzle.set(0, 0.035, -0.55);
  } else if (id === 'm4') {
    vbox(group, 0.07, 0.085, 0.4, 0, 0.01, 0, metal);
    vcyl(group, 0.012, 0.32, 0, 0.03, -0.34, metal);
    vbox(group, 0.06, 0.075, 0.24, 0, 0.01, -0.22, black);
    vbox(group, 0.05, 0.05, 0.22, 0, 0.075, 0.02, black);
    vbox(group, 0.03, 0.03, 0.03, 0, 0.11, 0.06, black);
    vbox(group, 0.05, 0.16, 0.08, 0, -0.095, 0.07, metal, 0.28);
    vbox(group, 0.045, 0.1, 0.05, 0, -0.055, 0.2, black, -0.25);
    vbox(group, 0.055, 0.08, 0.24, 0, -0.02, 0.34, black, 0.04);
    vbox(group, 0.075, 0.07, 0.11, 0.012, -0.11, 0.15, glove, 0.12);
    muzzle.set(0, 0.03, -0.52);
  } else if (id === 'awp') {
    vbox(group, 0.07, 0.09, 0.5, 0, 0.01, 0.02, olive);
    vcyl(group, 0.016, 0.5, 0, 0.035, -0.5, metal);
    vbox(group, 0.06, 0.07, 0.3, 0, 0.02, -0.3, olive);
    vcyl(group, 0.045, 0.24, 0, 0.135, 0.02, black);
    vcyl(group, 0.052, 0.05, 0, 0.135, -0.1, black);
    vbox(group, 0.08, 0.05, 0.12, 0, 0.1, 0.02, black);
    vbox(group, 0.055, 0.08, 0.24, 0, -0.02, 0.38, olive, 0.05);
    vbox(group, 0.05, 0.13, 0.08, 0, -0.09, 0.08, metal, 0.25);
    vbox(group, 0.075, 0.07, 0.11, 0.012, -0.11, 0.17, glove);
    muzzle.set(0, 0.035, -0.77);
  } else if (id === 'deagle') {
    vbox(group, 0.06, 0.07, 0.3, 0, 0.02, -0.05, silver);
    vbox(group, 0.055, 0.05, 0.26, 0, -0.02, -0.03, black);
    vbox(group, 0.05, 0.1, 0.07, 0, -0.08, 0.1, black, -0.25);
    vbox(group, 0.02, 0.02, 0.03, 0, 0.062, -0.18, black);
    vbox(group, 0.07, 0.06, 0.09, 0.012, -0.07, 0.12, glove);
    muzzle.set(0, 0.02, -0.21);
  } else {
    const body = id === 'glock' ? black : metal;
    vbox(group, 0.055, 0.06, 0.26, 0, 0.02, -0.02, body);
    vbox(group, 0.05, 0.045, 0.2, 0, -0.015, 0, black);
    vbox(group, 0.045, 0.1, 0.065, 0, -0.07, 0.09, black, -0.2);
    vbox(group, 0.06, 0.055, 0.08, 0.01, -0.06, 0.1, glove);
    muzzle.set(0, 0.02, -0.17);
  }

  group.traverse((o) => { if (o.isMesh) o.renderOrder = 995; });
  return { group, muzzle };
}

function disposeGroup(g) {
  g.traverse((o) => {
    if (o.isMesh) {
      o.geometry.dispose();
      if (Array.isArray(o.material)) o.material.forEach((m) => m.dispose());
      else if (o.material) o.material.dispose();
    } else if (o.isSprite && o.material) {
      o.material.dispose();
    }
  });
}

function setViewmodel() {
  if (vmGun) { vmRoot.remove(vmGun); disposeGroup(vmGun); vmGun = null; }
  const w = currentWeapon();
  if (!w) return;
  const info = buildGun(w.id);
  vmGun = info.group;
  vmRoot.add(vmGun);
  vmMuzzle.copy(info.muzzle);
  flashSprite.position.copy(vmMuzzle);
  flashSprite.visible = false;
  const isPistol = WDEF[w.id].slot === 'pistol';
  vmBase.set(isPistol ? 0.30 : 0.29, isPistol ? -0.30 : -0.28, isPistol ? -0.68 : -0.66);
  vmRoot.position.copy(vmBase);
  vmGun.scale.setScalar(isPistol ? 0.85 : 0.92);
}

// ---------------- 命中特效 ----------------
const tracers = [];
function spawnTracer(a, b) {
  const geo = new THREE.BufferGeometry().setFromPoints([a, b]);
  const mat = new THREE.LineBasicMaterial({ color: 0xffe2a8, transparent: true, opacity: 0.8 });
  const line = new THREE.Line(geo, mat);
  scene.add(line);
  tracers.push({ line, life: 0.07, max: 0.07 });
  while (tracers.length > 26) {
    const old = tracers.shift();
    scene.remove(old.line);
    old.line.geometry.dispose();
    old.line.material.dispose();
  }
}

const decals = [];
function addDecal(point, normal) {
  const mat = new THREE.MeshBasicMaterial({
    map: texDecal, transparent: true, depthWrite: false,
    polygonOffset: true, polygonOffsetFactor: -2, opacity: 0.9
  });
  const m = new THREE.Mesh(new THREE.PlaneGeometry(0.16, 0.16), mat);
  m.position.copy(point).addScaledVector(normal, 0.012);
  m.lookAt(point.clone().add(normal));
  m.rotateZ(Math.random() * Math.PI);
  scene.add(m);
  decals.push({ m, life: 12 });
  while (decals.length > 50) {
    const old = decals.shift();
    scene.remove(old.m);
    old.m.geometry.dispose();
    old.m.material.dispose();
  }
}

const bloods = [];
function spawnBlood(point) {
  const mat = new THREE.SpriteMaterial({
    map: texBlood, transparent: true, depthWrite: false, depthTest: true, color: 0xff6655
  });
  const s = new THREE.Sprite(mat);
  s.position.copy(point);
  s.scale.set(0.3, 0.3, 1);
  scene.add(s);
  bloods.push({ s, life: 0.3, max: 0.3, vy: rand(0.4, 1.4) });
}

function hitmarker(kill) {
  const el = $('hitmarker');
  el.classList.add('show');
  el.classList.toggle('kill', !!kill);
  clearTimeout(hitmarkerTimer);
  hitmarkerTimer = setTimeout(() => el.classList.remove('show'), 130);
}
function flashDamage() {
  dmgFlashT = 0.4;
  $('dmgflash').style.opacity = '0.75';
}
function reward(txt) {
  const d = document.createElement('div');
  d.className = 'reward';
  d.textContent = txt;
  $('rewards').appendChild(d);
  setTimeout(() => d.remove(), 1050);
}
let bannerTimer = null;
function banner(main, color, sub) {
  const el = $('banner');
  el.innerHTML = '<div class="b-main" style="color:' + (color || '#ffd27a') + '">' + main + '</div>' +
    (sub ? '<div class="b-sub">' + sub + '</div>' : '');
  el.classList.remove('show');
  void el.offsetWidth;
  el.classList.add('show');
  clearTimeout(bannerTimer);
  bannerTimer = setTimeout(() => el.classList.remove('show'), 2700);
}
function killfeed(killer, weapon, victim) {
  const el = document.createElement('div');
  el.className = 'kf';
  const vCls = victim === '你' ? 'you' : (S.team === 't' ? 'ct' : '');
  el.innerHTML = '<b class="k">' + killer + '</b><span class="w">' + weapon +
    '</span><b class="v ' + vCls + '">' + victim + '</b>';
  const feed = $('killfeed');
  feed.prepend(el);
  while (feed.children.length > 5) feed.lastChild.remove();
  setTimeout(() => el.classList.add('fade'), 4200);
  setTimeout(() => el.remove(), 5100);
}

// ---------------- HUD ----------------
const hudCache = {};
function setTxt(id, v) {
  if (hudCache[id] === v) return;
  hudCache[id] = v;
  const el = $(id);
  if (el) el.textContent = v;
}
let radarAcc = 0;

function updateHud() {
  setTxt('hpVal', String(Math.max(0, Math.round(player.health))));
  setTxt('arVal', String(Math.max(0, Math.round(player.armor))));
  setTxt('moneyVal', '$' + G.money);
  setTxt('roundTitle', '回合 ' + Math.max(1, G.round));
  const t = nowS();
  let sub;
  if (G.roundEnding) sub = G.dead ? '回合结束' : '回合结束';
  else if (t < G.freezeUntil) sub = '购买时间 ' + Math.ceil(G.freezeUntil - t) + ' 秒';
  else sub = '剩余敌人 ' + G.bots.filter((b) => b.alive).length;
  setTxt('roundSub', sub);
  const w = currentWeapon(), d = weaponDef();
  if (w && d) {
    setTxt('wName', d.name);
    setTxt('ammoMag', String(w.ammo));
    setTxt('ammoRes', String(w.reserve));
  }
  const speed = Math.hypot(player.vel.x, player.vel.z);
  let gap = 4 + (d ? d.spread * 900 : 4) + bloom * 2.2 + speed * 1.1;
  if (!player.grounded) gap += 8;
  if (player.crouch) gap *= 0.75;
  if (scopeOn) gap = 0;
  const gapStr = gap.toFixed(1) + 'px';
  if (gapStr !== lastGap) {
    lastGap = gapStr;
    $('crosshair').style.setProperty('--gap', gapStr);
  }
  radarAcc++;
  if (radarAcc % 5 === 0) drawRadar();
}

// ---------------- 视角模型动画 / 开镜 ----------------
function setScope(on) {
  const w = currentWeapon();
  if (on && (!w || w.id !== 'awp')) on = false;
  if (scopeOn === on) return;
  scopeOn = on;
  document.body.classList.toggle('scoped', on);
  camera.fov = on ? 34 : 75;
  camera.updateProjectionMatrix();
  vmRoot.visible = !on && G.state === 'playing';
  Sound.ui();
}

// ---------------- 射击 ----------------
function botPartMeshes() {
  const arr = [];
  for (const b of G.bots) if (b.alive) arr.push.apply(arr, b.hitMeshes);
  return arr;
}
function muzzleWorld() {
  const forward = new THREE.Vector3(0, 0, -1).applyQuaternion(camera.quaternion);
  const right = new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion);
  const up = new THREE.Vector3(0, 1, 0).applyQuaternion(camera.quaternion);
  return camera.getWorldPosition(new THREE.Vector3())
    .addScaledVector(forward, 0.55)
    .addScaledVector(right, 0.17)
    .addScaledVector(up, -0.12);
}

function tryFire() {
  if (G.state !== 'playing' || G.paused || G.dead || G.buyOpen) return;
  const w = currentWeapon(), d = weaponDef();
  if (!w || !d) return;
  const t = nowS();
  if (reloading || t < switchT) return;
  if (t < nextFire) return;
  if (w.ammo <= 0) {
    Sound.empty();
    nextFire = t + 0.25;
    startReload();
    return;
  }
  nextFire = t + 60 / d.rpm;
  w.ammo--;
  G.shots++;
  Sound.shot(d.sound, d.slot === 'primary' ? 1 : 0.8);
  vmKick = Math.min(vmKick + (d.recoilV > 0.03 ? 1.8 : 1.1), 2.4);
  flashUntil = t + 0.055;
  flashSprite.visible = true;
  flashSprite.material.rotation = Math.random() * Math.PI * 2;
  const fs = rand(0.2, 0.34);
  flashSprite.scale.set(fs, fs, 1);
  muzzleLight.intensity = 2.4;

  const kickScale = scopeOn ? 0.45 : 1;
  player.pitch = clamp(player.pitch + d.recoilV * kickScale, -1.52, 1.52);
  player.yaw += rand(-1, 1) * d.recoilH * kickScale;

  const speed = Math.hypot(player.vel.x, player.vel.z);
  let spread = d.spread + d.moveSpread * clamp(speed / 4.9, 0, 1);
  if (!player.grounded) spread += 0.06;
  if (player.crouch) spread *= 0.6;
  if (scopeOn) spread = 0.0008;
  spread += bloom * 0.003;
  bloom = Math.min(bloom + 0.55, 3);

  const dir = new THREE.Vector3(0, 0, -1).applyQuaternion(camera.quaternion);
  const rightV = new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion);
  const upV = new THREE.Vector3(0, 1, 0).applyQuaternion(camera.quaternion);
  const gauss = () => (Math.random() + Math.random() + Math.random() - 1.5) * 0.9;
  dir.addScaledVector(rightV, gauss() * spread).addScaledVector(upV, gauss() * spread).normalize();

  const origin = camera.getWorldPosition(new THREE.Vector3());
  const ray = new THREE.Raycaster(origin, dir, 0, 300);
  const targets = worldMeshes.concat(botPartMeshes());
  const hits = ray.intersectObjects(targets, false);
  let hit = null;
  for (let i = 0; i < hits.length; i++) {
    const h = hits[i];
    if (h.object.userData && h.object.userData.bot) {
      if (!h.object.userData.bot.alive) continue;
      hit = h;
      break;
    }
    hit = h;
    break;
  }
  const end = hit ? hit.point.clone() : origin.clone().addScaledVector(dir, 120);
  spawnTracer(muzzleWorld(), end);

  if (hit && hit.object.userData && hit.object.userData.bot) {
    const bot = hit.object.userData.bot;
    const part = hit.object.userData.part || 'body';
    let dmg = d.dmg * (part === 'head' ? 4 : part === 'legs' ? 0.72 : 1);
    if (part !== 'head') dmg *= clamp(1 - origin.distanceTo(end) / 130, 0.55, 1);
    G.hits++;
    damageBot(bot, dmg, part, hit.point);
  } else if (hit) {
    let n = new THREE.Vector3(0, 1, 0);
    if (hit.face) {
      n.copy(hit.face.normal).transformDirection(hit.object.matrixWorld).normalize();
    }
    addDecal(hit.point, n);
  }
  alertBotsNear(origin, 30);
}

function startReload() {
  const w = currentWeapon(), d = weaponDef();
  if (!w || !d || reloading) return;
  if (w.ammo >= d.mag || w.reserve <= 0) return;
  reloading = true;
  reloadEnd = nowS() + d.reload;
  Sound.reload();
  if (scopeOn) setScope(false);
  $('reloadTip').textContent = '换弹中…';
}

function switchSlot(slot) {
  if (slot === loadout.current) return;
  if (!loadout[slot]) return;
  if (reloading) {
    reloading = false;
    $('reloadTip').textContent = '';
  }
  loadout.current = slot;
  switchT = nowS() + 0.45;
  if (scopeOn) setScope(false);
  setViewmodel();
  Sound.ui();
  updateHud();
}

function alertBotsNear(origin, radius) {
  for (const b of G.bots) {
    if (!b.alive) continue;
    if (b.pos.distanceTo(origin) < radius) {
      b.mode = 'fight';
      b.lastSeen.copy(player.pos);
      b.lastSeenAge = 0;
      b.reactT = Math.max(b.reactT, 0.25);
    }
  }
}

// ---------------- 伤害结算 ----------------
function damageBot(bot, dmg, part, point) {
  if (!bot.alive) return;
  bot.hp -= dmg;
  spawnBlood(point);
  if (bot.hp <= 0) {
    bot.alive = false;
    bot.deathT = 0;
    G.kills++;
    G.roundKills++;
    if (part === 'head') G.headshots++;
    G.money = Math.min(16000, G.money + 300);
    reward('+$300');
    Sound.death();
    killfeed('你', weaponDef() ? weaponDef().name : '—', bot.name);
    hitmarker(true);
    if (part === 'head') Sound.headshot();
    updateHud();
    if (!G.bots.some((b) => b.alive)) winRound();
  } else {
    bot.aggro();
    hitmarker(false);
    if (part === 'head') Sound.headshot();
    else Sound.hit();
  }
}

function damagePlayer(dmg, fromName) {
  if (player.dead || G.dead) return;
  let d = dmg;
  if (player.armor > 0) {
    d *= 0.55;
    player.armor = Math.max(0, player.armor - dmg * 0.55);
  }
  player.health -= d;
  shake = Math.max(shake, 0.55);
  flashDamage();
  updateHud();
  if (player.health <= 0) {
    player.health = 0;
    diePlayer(fromName);
  }
}

function diePlayer(killer) {
  if (player.dead) return;
  player.dead = true;
  G.dead = true;
  G.deaths++;
  G.roundEnding = true;
  if (G.buyOpen) closeBuy(true);
  setScope(false);
  Sound.lose();
  const enemyTeam = S.team === 't' ? 'ct' : 't';
  killfeed(killer, enemyTeam === 't' ? 'AK-47' : 'M4A1', '你');
  if (document.pointerLockElement) document.exitPointerLock();
  const acc = G.shots ? Math.round(G.hits / G.shots * 100) : 0;
  $('deathSub').textContent = '被 ' + killer + ' 击杀';
  $('deathStats').innerHTML =
    '本回合击杀 <b>' + G.roundKills + '</b> · 总击杀 <b>' + G.kills + '</b><br>' +
    '命中率 ' + acc + '% · 爆头 ' + G.headshots + ' 次';
  schedule(() => { if (G.dead) $('death').classList.remove('hidden'); }, 900);
}

// ---------------- 人机 ----------------
const BOT_NAMES = ['铁头', '老六', '阿豹', '黑皮', '独狼', '大壮', '秃鹫', '响尾蛇', '老K', '眼镜', '沙鹰', '瘸子'];
function shuffle(a) {
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    const t = a[i]; a[i] = a[j]; a[j] = t;
  }
  return a;
}

class Bot {
  constructor(name, team, x, z) {
    this.name = name;
    this.team = team;
    this.weaponName = team === 't' ? 'AK-47' : 'M4A1';
    this.pos = new THREE.Vector3(x, 0, z);
    this.hp = 100;
    this.alive = true;
    this.deathT = 0;
    this.yaw = Math.atan2(-(player.pos.x - x), -(player.pos.z - z));
    this.mode = 'patrol';
    this.target = new THREE.Vector3();
    this.canSee = false;
    this.seeT = Math.random() * 0.2;
    this.lastSeen = new THREE.Vector3();
    this.lastSeenAge = 99;
    this.reactT = DIFF[S.diff].reaction;
    this.fireCd = rand(0.4, 1.2);
    this.burstLeft = 0;
    this.burstT = 0;
    this.strafeDir = Math.random() < 0.5 ? -1 : 1;
    this.strafeT = rand(1, 2.4);
    this.stuckT = 0;
    this.phase = Math.random() * 10;
    this.moveSpeed = DIFF[S.diff].speed;
    this.flashT = 0;
    this.build();
    this.pickPatrol();
  }

  build() {
    const isT = this.team === 't';
    const shirtMat = new THREE.MeshStandardMaterial({ color: isT ? 0x86633c : 0x2f4259, roughness: 0.9 });
    const pantsMat = new THREE.MeshStandardMaterial({ color: isT ? 0x4a3826 : 0x1f2937, roughness: 0.95 });
    const gearMat = new THREE.MeshStandardMaterial({ color: isT ? 0x5a4326 : 0x17212e, roughness: 0.8 });
    const skinMat = new THREE.MeshStandardMaterial({ color: 0xc3946c, roughness: 0.85 });
    const darkMat = new THREE.MeshStandardMaterial({ color: 0x141517, roughness: 0.9 });
    const gunMat = new THREE.MeshStandardMaterial({ color: 0x1b1d21, roughness: 0.45, metalness: 0.55 });

    const g = new THREE.Group();
    g.position.set(this.pos.x, 0, this.pos.z);
    g.rotation.y = this.yaw;
    this.group = g;
    scene.add(g);

    const legL = new THREE.Group();
    legL.position.set(0.14, 0.88, 0);
    const legLM = new THREE.Mesh(new THREE.BoxGeometry(0.17, 0.88, 0.2), pantsMat);
    legLM.position.y = -0.44;
    legL.add(legLM);

    const legR = new THREE.Group();
    legR.position.set(-0.14, 0.88, 0);
    const legRM = new THREE.Mesh(new THREE.BoxGeometry(0.17, 0.88, 0.2), pantsMat);
    legRM.position.y = -0.44;
    legR.add(legRM);
    g.add(legL, legR);

    const torso = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.62, 0.3), shirtMat);
    torso.position.y = 1.19;
    g.add(torso);

    const vest = new THREE.Mesh(new THREE.BoxGeometry(0.54, 0.36, 0.33), gearMat);
    vest.position.y = 1.2;
    g.add(vest);

    const head = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.3, 0.3), isT ? darkMat : skinMat);
    head.position.y = 1.66;
    g.add(head);

    if (isT) {
      const cap = new THREE.Mesh(new THREE.BoxGeometry(0.33, 0.13, 0.33), darkMat);
      cap.position.y = 1.795;
      g.add(cap);
    } else {
      const helmet = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.16, 0.34), gearMat);
      helmet.position.y = 1.79;
      g.add(helmet);
      const goggles = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.06, 0.03), darkMat);
      goggles.position.set(0, 1.68, -0.16);
      g.add(goggles);
    }

    const armL = new THREE.Mesh(new THREE.BoxGeometry(0.13, 0.42, 0.16), shirtMat);
    armL.position.set(0.29, 1.3, -0.12);
    armL.rotation.x = -1.1;
    armL.rotation.z = -0.12;
    g.add(armL);

    const armR = new THREE.Mesh(new THREE.BoxGeometry(0.13, 0.42, 0.16), shirtMat);
    armR.position.set(-0.29, 1.3, -0.1);
    armR.rotation.x = -1.15;
    armR.rotation.z = 0.12;
    g.add(armR);

    const gun = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.09, 0.46), gunMat);
    gun.position.set(0.13, 1.3, -0.34);
    g.add(gun);

    const mag = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.14, 0.07), gunMat);
    mag.position.set(0.13, 1.2, -0.3);
    g.add(mag);

    const handR = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.08, 0.09), skinMat);
    handR.position.set(0.13, 1.25, -0.19);
    g.add(handR);

    this.legL = legL;
    this.legR = legR;

    this.flashSprite = new THREE.Sprite(new THREE.SpriteMaterial({
      map: texFlash, transparent: true, depthWrite: false,
      blending: THREE.AdditiveBlending, opacity: 0.95
    }));
    this.flashSprite.position.set(0.13, 1.31, -0.6);
    this.flashSprite.scale.set(0.3, 0.3, 1);
    this.flashSprite.visible = false;
    g.add(this.flashSprite);

    head.userData = { bot: this, part: 'head' };
    torso.userData = { bot: this, part: 'body' };
    vest.userData = { bot: this, part: 'body' };
    armL.userData = { bot: this, part: 'body' };
    armR.userData = { bot: this, part: 'body' };
    legLM.userData = { bot: this, part: 'legs' };
    legRM.userData = { bot: this, part: 'legs' };
    this.hitMeshes = [head, torso, vest, armL, armR, legLM, legRM];

    g.traverse((o) => {
      if (o.isMesh) {
        o.castShadow = true;
        o.receiveShadow = true;
      }
    });
  }

  pickPatrol() {
    const ang = Math.random() * Math.PI * 2;
    const r = rand(6, 20);
    this.target.set(
      clamp(player.pos.x + Math.cos(ang) * r, -30, 30),
      0,
      clamp(player.pos.z + Math.sin(ang) * r, -24, 24)
    );
  }

  aggro() {
    this.mode = 'fight';
    this.lastSeen.copy(player.pos);
    this.lastSeenAge = 0;
    this.canSee = false;
    this.seeT = 0.02;
    this.reactT = Math.max(this.reactT, 0.2);
    this.burstLeft = 0;
  }

  checkSee() {
    if (player.dead) return false;
    const eye = this.pos.clone();
    eye.y = 1.6;
    const target = player.pos.clone();
    target.y += player.curEye;
    const dv = target.clone().sub(eye);
    const dist = dv.length();
    if (dist > 65) return false;
    const fwd = new THREE.Vector3(-Math.sin(this.yaw), 0, -Math.cos(this.yaw));
    const flat = new THREE.Vector3(dv.x, 0, dv.z);
    if (flat.lengthSq() < 0.0001) return true;
    flat.normalize();
    if (fwd.dot(flat) < 0.15) return false;
    const ray = new THREE.Raycaster(eye, dv.clone().normalize(), 0, Math.max(0.2, dist - 0.25));
    const hits = ray.intersectObjects(worldMeshes, false);
    return hits.length === 0;
  }

  turnTowards(tx, tz, dt, rate) {
    const want = Math.atan2(-(tx - this.pos.x), -(tz - this.pos.z));
    const d = angleDiff(this.yaw, want);
    this.yaw += clamp(d, -rate * dt, rate * dt);
  }

  move(dx, dz) {
    const half = 0.32;
    const p = this.pos;
    p.x += dx;
    for (const c of colliders) {
      if (p.x + half > c.minX && p.x - half < c.maxX && p.z + half > c.minZ && p.z - half < c.maxZ) {
        if (dx > 0) p.x = c.minX - half - 0.001;
        else if (dx < 0) p.x = c.maxX + half + 0.001;
      }
    }
    p.z += dz;
    for (const c of colliders) {
      if (p.x + half > c.minX && p.x - half < c.maxX && p.z + half > c.minZ && p.z - half < c.maxZ) {
        if (dz > 0) p.z = c.minZ - half - 0.001;
        else if (dz < 0) p.z = c.maxZ + half + 0.001;
      }
    }
    p.x = clamp(p.x, -32.8, 32.8);
    p.z = clamp(p.z, -26.3, 26.3);
  }

  shoot() {
    const d = DIFF[S.diff];
    const origin = this.group.localToWorld(new THREE.Vector3(0.13, 1.31, -0.62));
    const eye = player.pos.clone();
    eye.y += player.curEye;
    const dist = origin.distanceTo(eye);
    const playerSpeed = Math.hypot(player.vel.x, player.vel.z);
    const errRad = (d.err * Math.PI / 180) * rand(0.45, 1.5) * (1 + playerSpeed * 0.18);
    const dir = eye.clone().sub(origin).normalize();
    const axis = new THREE.Vector3(rand(-1, 1), rand(-1, 1), rand(-1, 1));
    if (axis.lengthSq() < 0.001) axis.set(0, 1, 0);
    axis.normalize();
    dir.applyAxisAngle(axis, errRad);

    const ray = new THREE.Raycaster(origin, dir, 0, 120);
    const wallHits = ray.intersectObjects(worldMeshes, false);
    const wallDist = wallHits.length ? wallHits[0].distance : Infinity;
    const pRay = new THREE.Ray(origin, dir);
    const headC = player.pos.clone(); headC.y += player.curEye;
    const bodyC = player.pos.clone(); bodyC.y += 1.0;
    const dHead = pRay.distanceToPoint(headC);
    const dBody = pRay.distanceToPoint(bodyC);

    this.flashT = 0.06;
    Sound.botShot(dist);

    if (wallDist > dist - 0.2) {
      if (dHead < 0.27) {
        damagePlayer(rand(d.dmgMin, d.dmgMax) * 2.4, this.name);
        spawnBlood(headC);
        spawnTracer(origin, headC);
        return;
      }
      if (dBody < 0.5) {
        damagePlayer(rand(d.dmgMin, d.dmgMax), this.name);
        spawnBlood(bodyC);
        spawnTracer(origin, bodyC);
        return;
      }
    }
    let end;
    if (wallDist < 110) end = origin.clone().addScaledVector(dir, wallDist);
    else end = origin.clone().addScaledVector(dir, 60);
    spawnTracer(origin, end);
    if (wallDist < 110 && wallHits.length) {
      let n = new THREE.Vector3(0, 1, 0);
      if (wallHits[0].face) n.copy(wallHits[0].face.normal).transformDirection(wallHits[0].object.matrixWorld).normalize();
      addDecal(wallHits[0].point, n);
    }
  }

  animate(dt, moving) {
    this.phase += dt * (moving ? this.moveSpeed * 2.2 : 1.4);
    const swing = Math.sin(this.phase) * (moving ? 0.52 : 0.02);
    this.legL.rotation.x = swing;
    this.legR.rotation.x = -swing;
  }

  think(dt, t) {
    if (!this.alive) {
      this.deathT += dt;
      const p = Math.min(1, this.deathT / 0.5);
      this.group.rotation.x = p * Math.PI / 2;
      return;
    }
    this.flashT = Math.max(0, this.flashT - dt);
    this.flashSprite.visible = this.flashT > 0;

    const frozen = t < G.freezeUntil || G.dead || G.state !== 'playing';
    this.seeT -= dt;
    if (this.seeT <= 0 && !frozen) {
      this.seeT = 0.12 + Math.random() * 0.07;
      const was = this.canSee;
      this.canSee = this.checkSee();
      if (this.canSee) {
        this.lastSeen.copy(player.pos);
        this.lastSeenAge = 0;
        this.mode = 'fight';
        if (!was) {
          this.reactT = DIFF[S.diff].reaction;
          this.burstLeft = 0;
        }
      }
    } else if (frozen) {
      this.canSee = false;
    }
    if (!this.canSee) this.lastSeenAge = Math.min(99, this.lastSeenAge + dt);

    if (frozen) {
      this.animate(dt, false);
      this.group.position.set(this.pos.x, 0, this.pos.z);
      this.group.rotation.y = this.yaw;
      return;
    }

    const dx = player.pos.x - this.pos.x;
    const dz = player.pos.z - this.pos.z;
    const dist = Math.hypot(dx, dz);
    let moveX = 0, moveZ = 0;
    let moving = false;

    if (this.mode === 'fight') {
      if (this.canSee) {
        this.turnTowards(player.pos.x, player.pos.z, dt, 7);
        this.strafeT -= dt;
        if (this.strafeT <= 0) {
          this.strafeT = rand(1.0, 2.2);
          this.strafeDir *= -1;
        }
        const nx = dx / (dist || 1), nz = dz / (dist || 1);
        const rx = -nz, rz = nx;
        let mx = 0, mz = 0;
        if (dist > 15) { mx = nx; mz = nz; }
        else if (dist < 5) { mx = -nx; mz = -nz; }
        else { mx = rx * this.strafeDir; mz = rz * this.strafeDir; }
        moveX = mx * this.moveSpeed;
        moveZ = mz * this.moveSpeed;
        moving = true;

        this.reactT -= dt;
        const wantYaw = Math.atan2(-dx, -dz);
        const aligned = Math.abs(angleDiff(this.yaw, wantYaw)) < 0.16;
        if (this.reactT <= 0 && aligned) {
          if (this.burstLeft > 0) {
            this.burstT -= dt;
            if (this.burstT <= 0) {
              this.burstT = 0.135;
              this.burstLeft--;
              this.shoot();
            }
          } else {
            this.fireCd -= dt;
            if (this.fireCd <= 0) {
              const dd = DIFF[S.diff];
              this.burstLeft = irand(dd.burstMin, dd.burstMax);
              this.burstT = 0;
              this.fireCd = rand(dd.fireCdMin, dd.fireCdMax);
            }
          }
        }
      } else if (this.lastSeenAge <= 4) {
        const tx = this.lastSeen.x - this.pos.x;
        const tz = this.lastSeen.z - this.pos.z;
        const td = Math.hypot(tx, tz);
        if (td < 1.6) {
          this.mode = 'patrol';
          this.pickPatrol();
        } else {
          this.turnTowards(this.lastSeen.x, this.lastSeen.z, dt, 6);
          moveX = (tx / td) * this.moveSpeed;
          moveZ = (tz / td) * this.moveSpeed;
          moving = true;
        }
      } else {
        this.mode = 'patrol';
        this.pickPatrol();
      }
    } else {
      const tx = this.target.x - this.pos.x;
      const tz = this.target.z - this.pos.z;
      const td = Math.hypot(tx, tz);
      if (td < 1.5) {
        this.pickPatrol();
      } else {
        this.turnTowards(this.target.x, this.target.z, dt, 4);
        moveX = (tx / td) * this.moveSpeed * 0.8;
        moveZ = (tz / td) * this.moveSpeed * 0.8;
        moving = true;
      }
    }

    for (const other of G.bots) {
      if (other === this || !other.alive) continue;
      const sx = this.pos.x - other.pos.x;
      const sz = this.pos.z - other.pos.z;
      const sd = Math.hypot(sx, sz);
      if (sd > 0.001 && sd < 1.0) {
        moveX += (sx / sd) * 1.6;
        moveZ += (sz / sd) * 1.6;
      }
    }

    if (moveX !== 0 || moveZ !== 0) {
      const bx = this.pos.x, bz = this.pos.z;
      this.move(moveX * dt, moveZ * dt);
      const moved = Math.hypot(this.pos.x - bx, this.pos.z - bz);
      const want = Math.hypot(moveX, moveZ) * dt;
      if (want > 0.0001 && moved < want * 0.3) {
        this.stuckT += dt;
        if (this.stuckT > 0.7) {
          this.stuckT = 0;
          this.strafeDir *= -1;
          this.pickPatrol();
        }
      } else {
        this.stuckT = 0;
      }
    }

    this.group.position.set(this.pos.x, 0, this.pos.z);
    this.group.rotation.y = this.yaw;
    this.animate(dt, moving);
  }
}

function clearBots() {
  for (const b of G.bots) {
    if (b.group) {
      scene.remove(b.group);
      disposeGroup(b.group);
    }
  }
  G.bots.length = 0;
}

// ---------------- 回合 ----------------
function playerSpawnPoint() {
  return S.team === 't' ? { x: 0, z: -23.2, yaw: Math.PI } : { x: 0, z: 23.2, yaw: 0 };
}

function beginRound() {
  G.round++;
  G.roundId++;
  G.roundEnding = false;
  G.dead = false;
  G.pendingRound = false;
  G.roundKills = 0;
  player.dead = false;
  $('death').classList.add('hidden');
  $('pause').classList.add('hidden');
  G.paused = false;
  closeBuy(true);
  clearBots();

  const sp = playerSpawnPoint();
  player.pos.set(sp.x, 0, sp.z);
  player.vel.set(0, 0, 0);
  player.yaw = sp.yaw;
  player.pitch = 0;
  player.health = 100;
  player.crouch = false;
  player.height = 1.78;
  player.curEye = 1.63;
  player.grounded = true;
  reloading = false;
  reloadEnd = 0;
  nextFire = 0;
  switchT = 0;
  bloom = 0;
  setScope(false);
  $('reloadTip').textContent = '';

  if (loadout.primary) {
    const d = WDEF[loadout.primary.id];
    loadout.primary.ammo = d.mag;
    loadout.primary.reserve = d.reserve;
  }
  if (loadout.pistol) {
    const d = WDEF[loadout.pistol.id];
    loadout.pistol.ammo = d.mag;
    loadout.pistol.reserve = d.reserve;
  }
  if (loadout.current === 'primary' && !loadout.primary) loadout.current = 'pistol';
  setViewmodel();

  const enemy = S.team === 't' ? 'ct' : 't';
  const count = Math.min(1 + G.round, 7);
  const slots = shuffle(SPAWNS[enemy].slice());
  const names = shuffle(BOT_NAMES.slice());
  for (let i = 0; i < count; i++) {
    const p = slots[i % slots.length];
    const bot = new Bot(names[i % names.length], enemy, p[0] + rand(-0.9, 0.9), p[1] + rand(-0.9, 0.9));
    G.bots.push(bot);
  }

  G.freezeUntil = nowS() + 8;
  banner('回合 ' + G.round, '#ffd27a', (S.team === 't' ? '匪徒' : '特警') + ' · 购买时间 8 秒');
  $('hint').classList.remove('off');
  clearTimeout(hintTimer);
  hintTimer = setTimeout(() => $('hint').classList.add('off'), 12000);
  updateHud();
}

let hintTimer = null;

function winRound() {
  if (G.roundEnding) return;
  G.roundEnding = true;
  G.money = Math.min(16000, G.money + 3250);
  reward('+$3250');
  banner('回合胜利', '#9dff5e', '奖励 $3250 · 准备下一回合');
  Sound.win();
  updateHud();
  schedule(() => {
    if (G.state !== 'playing' || G.dead) return;
    if (G.paused) { G.pendingRound = true; return; }
    beginRound();
  }, 3600);
}

// ---------------- 购买 ----------------
function buyItems() {
  const t = S.team === 't';
  const primaryId = t ? 'ak47' : 'm4';
  const pistolId = t ? 'glock' : 'usp';
  const pd = WDEF[primaryId], sd = WDEF[pistolId];
  return [
    { key: '1', id: primaryId, kind: 'primary', name: pd.name, price: pd.price },
    { key: '2', id: 'awp', kind: 'primary', name: 'AWP', price: WDEF.awp.price },
    { key: '3', id: 'deagle', kind: 'pistol', name: '沙漠之鹰', price: WDEF.deagle.price },
    { key: '4', id: pistolId, kind: 'pistol', name: sd.name, price: sd.price },
    { key: '5', id: 'armor', kind: 'armor', name: '防弹衣 (100)', price: 650 },
    { key: '6', id: 'ammo', kind: 'ammo', name: '补满弹药', price: 100 }
  ];
}

function renderBuyList() {
  const box = $('buyList');
  box.innerHTML = '';
  buyItems().forEach((item, i) => {
    const btn = document.createElement('button');
    btn.className = 'buy-row' + (item.price > G.money ? ' cant' : '');
    btn.dataset.i = String(i);
    btn.innerHTML = '<span class="bk">' + item.key + '</span><span class="bn">' + item.name +
      '</span><span class="bp">$' + item.price + '</span>';
    btn.addEventListener('click', () => buyByIndex(i));
    box.appendChild(btn);
  });
  $('buyMoney').textContent = '$' + G.money;
}

function buyByIndex(i) {
  if (!G.buyOpen) return;
  const item = buyItems()[i];
  if (!item) return;
  if (item.price > G.money) {
    Sound.deny();
    const row = document.querySelector('.buy-row[data-i="' + i + '"]');
    if (row) {
      row.classList.remove('deny');
      void row.offsetWidth;
      row.classList.add('deny');
    }
    return;
  }
  if (item.kind === 'primary') {
    loadout.primary = makeWeapon(item.id);
    loadout.current = 'primary';
    switchT = nowS() + 0.4;
    setViewmodel();
  } else if (item.kind === 'pistol') {
    loadout.pistol = makeWeapon(item.id);
    loadout.current = 'pistol';
    switchT = nowS() + 0.35;
    setViewmodel();
  } else if (item.kind === 'armor') {
    player.armor = 100;
  } else if (item.kind === 'ammo') {
    if (loadout.primary) {
      const d = WDEF[loadout.primary.id];
      loadout.primary.ammo = d.mag;
      loadout.primary.reserve = d.reserve;
    }
    if (loadout.pistol) {
      const d = WDEF[loadout.pistol.id];
      loadout.pistol.ammo = d.mag;
      loadout.pistol.reserve = d.reserve;
    }
  }
  G.money -= item.price;
  Sound.buy();
  updateHud();
  renderBuyList();
}

let buyOpenedAt = 0, pausedAt = 0;

function openBuy() {
  if (G.state !== 'playing' || G.dead) return;
  G.buyOpen = true;
  buyOpenedAt = nowS();
  document.body.classList.add('buyopen');
  $('buy').classList.remove('hidden');
  renderBuyList();
  if (document.pointerLockElement) document.exitPointerLock();
}
function closeBuy(silent) {
  if (!G.buyOpen) return;
  G.buyOpen = false;
  document.body.classList.remove('buyopen');
  $('buy').classList.add('hidden');
  const t = nowS();
  if (G.freezeUntil > buyOpenedAt) G.freezeUntil += t - buyOpenedAt;
  if (!silent) requestLock();
}
function toggleBuy() {
  if (G.buyOpen) closeBuy();
  else openBuy();
}

// ---------------- 指针锁 ----------------
function requestLock() {
  if (G.state !== 'playing' || G.paused || G.buyOpen) return;
  try {
    const p = canvas.requestPointerLock();
    if (p && p.then) p.then(() => {}).catch(() => {});
  } catch (e) { /* 忽略 */ }
}
function pauseGame() {
  if (G.paused || G.state !== 'playing') return;
  pausedAt = nowS();
  G.paused = true;
  closeBuy(true);
  showScore(false);
  $('pause').classList.remove('hidden');
  if (document.pointerLockElement) document.exitPointerLock();
}
function resumeGame() {
  const t = nowS();
  if (G.freezeUntil > pausedAt) G.freezeUntil += t - pausedAt;
  G.paused = false;
  $('pause').classList.add('hidden');
  if (G.pendingRound) {
    G.pendingRound = false;
    beginRound();
    return;
  }
  requestLock();
}

// ---------------- 战绩 UI ----------------
function showScore(show) {
  const el = $('score');
  if (show) {
    fillScore();
    el.classList.remove('hidden');
  } else {
    el.classList.add('hidden');
  }
}
function fillScore() {
  const acc = G.shots ? Math.round(G.hits / G.shots * 100) : 0;
  const teamTag = S.team === 't'
    ? '<span class="team-tag">匪</span>'
    : '<span class="team-tag ct">警</span>';
  $('scoreBody').innerHTML =
    '<tr><td>你 ' + teamTag + '</td><td>' + G.round + '</td><td>' + G.kills + '</td><td>' +
    G.deaths + '</td><td>' + G.headshots + '</td><td>' + acc + '%</td><td>$' + G.money + '</td></tr>';
}

// ---------------- 玩家更新 ----------------
function headBlocked(pos, newHeight) {
  const half = 0.36;
  for (const c of colliders) {
    if (pos.x + half > c.minX && pos.x - half < c.maxX &&
        pos.z + half > c.minZ && pos.z - half < c.maxZ &&
        pos.y + newHeight > c.minY && pos.y < c.maxY) return true;
  }
  return false;
}

function movePlayerAxis(axis, amount) {
  const pos = player.pos, half = 0.36, h = player.height;
  pos[axis] += amount;
  let hit = false;
  for (let i = 0; i < colliders.length; i++) {
    const c = colliders[i];
    if (pos.x + half > c.minX && pos.x - half < c.maxX &&
        pos.z + half > c.minZ && pos.z - half < c.maxZ &&
        pos.y + h > c.minY && pos.y < c.maxY) {
      if (axis === 'x') {
        if (amount > 0) pos.x = c.minX - half - 0.0001;
        else pos.x = c.maxX + half + 0.0001;
      } else {
        if (amount > 0) pos.z = c.minZ - half - 0.0001;
        else pos.z = c.maxZ + half + 0.0001;
      }
      hit = true;
    }
  }
  return hit;
}

function movePlayerYAxis(amount) {
  const pos = player.pos, half = 0.36, h = player.height;
  pos.y += amount;
  player.grounded = false;
  for (let i = 0; i < colliders.length; i++) {
    const c = colliders[i];
    if (pos.x + half > c.minX && pos.x - half < c.maxX &&
        pos.z + half > c.minZ && pos.z - half < c.maxZ &&
        pos.y + h > c.minY && pos.y < c.maxY) {
      if (amount > 0) {
        pos.y = c.minY - h - 0.0001;
        player.vel.y = Math.min(0, player.vel.y);
      } else {
        pos.y = c.maxY;
        player.vel.y = Math.max(0, player.vel.y);
        player.grounded = true;
      }
    }
  }
  if (pos.y <= 0) {
    pos.y = 0;
    player.vel.y = Math.max(0, player.vel.y);
    player.grounded = true;
  }
}

function updatePlayer(dt, t) {
  if (player.dead) {
    player.curEye = lerp(player.curEye, 0.22, dt * 4);
    camera.position.set(player.pos.x, player.pos.y + player.curEye, player.pos.z);
    camera.rotation.set(lerp(player.pitch, -0.2, dt * 3), player.yaw, 0, 'YXZ');
    if (vmRoot.visible) vmRoot.visible = false;
    return;
  }

  if (reloading && t >= reloadEnd) {
    const w = currentWeapon(), d = weaponDef();
    if (w && d) {
      const need = d.mag - w.ammo;
      const take = Math.min(need, w.reserve);
      w.ammo += take;
      w.reserve -= take;
    }
    reloading = false;
    $('reloadTip').textContent = '';
  }

  // 下蹲
  const wantCrouch = !!(keys.ControlLeft || keys.ControlRight);
  if (wantCrouch && !player.crouch) {
    player.crouch = true;
    player.height = 1.3;
  } else if (!wantCrouch && player.crouch) {
    if (!headBlocked(player.pos, 1.78)) {
      player.crouch = false;
      player.height = 1.78;
    }
  }

  // 移动输入
  const fwdX = -Math.sin(player.yaw), fwdZ = -Math.cos(player.yaw);
  const rightX = Math.cos(player.yaw), rightZ = -Math.sin(player.yaw);
  let wx = 0, wz = 0;
  if (keys.KeyW) wz += 1;
  if (keys.KeyS) wz -= 1;
  if (keys.KeyD) wx += 1;
  if (keys.KeyA) wx -= 1;
  let dirX = fwdX * wz + rightX * wx;
  let dirZ = fwdZ * wz + rightZ * wx;
  const dirLen = Math.hypot(dirX, dirZ);
  if (dirLen > 0.001) { dirX /= dirLen; dirZ /= dirLen; }

  const walk = !!(keys.ShiftLeft || keys.ShiftRight);
  const maxSpeed = player.crouch ? 2.0 : (walk ? 2.5 : 4.9);
  const accel = player.grounded ? 55 : 11;
  const targetVX = dirX * maxSpeed;
  const targetVZ = dirZ * maxSpeed;
  player.vel.x += clamp(targetVX - player.vel.x, -accel * dt, accel * dt);
  player.vel.z += clamp(targetVZ - player.vel.z, -accel * dt, accel * dt);

  if (player.grounded && dirLen < 0.001) {
    const fr = Math.max(0, 1 - dt * 11);
    player.vel.x *= fr;
    player.vel.z *= fr;
  }

  if (keys.Space && player.grounded) {
    player.vel.y = 5.9;
    player.grounded = false;
  }

  player.vel.y -= 17 * dt;
  if (player.vel.y < -30) player.vel.y = -30;

  const hitX = movePlayerAxis('x', player.vel.x * dt);
  if (hitX) player.vel.x = 0;
  const hitZ = movePlayerAxis('z', player.vel.z * dt);
  if (hitZ) player.vel.z = 0;
  movePlayerYAxis(player.vel.y * dt);

  // 眼高
  const targetEye = player.crouch ? 1.06 : 1.63;
  player.curEye = lerp(player.curEye, targetEye, Math.min(1, dt * 12));

  // 连发
  const d = weaponDef();
  if (mouseDown && d && d.auto && !G.buyOpen) tryFire();

  bloom = Math.max(0, bloom - dt * 3.2);
  vmKick = Math.max(0, vmKick - dt * 9);
  shake = Math.max(0, shake - dt * 3.2);
  dmgFlashT = Math.max(0, dmgFlashT - dt);
  $('dmgflash').style.opacity = dmgFlashT > 0 ? String(clamp(dmgFlashT * 1.8, 0, 0.75)) : '0';

  // 脚步 + 摆动
  const speed = Math.hypot(player.vel.x, player.vel.z);
  const moving = speed > 0.6 && player.grounded;
  if (moving) {
    player.stepPhase += dt * (speed * 2.0 + 1.2);
    player.stepT -= dt;
    if (player.stepT <= 0) {
      player.stepT = clamp(0.55 - speed * 0.055, 0.3, 0.55);
      Sound.step(walk ? 0.22 : 1);
    }
  } else {
    player.stepPhase += dt * 1.2;
    player.stepT = 0.1;
  }

  // 相机
  const bobCam = moving ? Math.sin(player.stepPhase) * 0.02 : 0;
  camera.position.set(player.pos.x, player.pos.y + player.curEye + bobCam, player.pos.z);
  const sh = shake * 0.02;
  camera.rotation.set(
    clamp(player.pitch + rand(-1, 1) * sh, -1.55, 1.55),
    player.yaw + rand(-1, 1) * sh,
    0, 'YXZ'
  );

  // 武器视图
  vmRoot.visible = !scopeOn && !G.buyOpen;
  if (vmRoot.visible) {
    const bobX = Math.sin(player.stepPhase) * (moving ? 0.011 : 0.0018);
    const bobY = Math.abs(Math.cos(player.stepPhase)) * (moving ? 0.009 : 0.0012);
    vmRoot.position.set(
      vmBase.x + bobX,
      vmBase.y - bobY - vmKick * 0.012,
      vmBase.z + vmKick * 0.055
    );
    vmRoot.rotation.set(-vmKick * 0.07 + bobY * 0.5, 0.12, -0.02 + bobX * 0.6);
    if (flashSprite.visible && t > flashUntil) flashSprite.visible = false;
  }

  // 视野
  const wantFov = scopeOn ? 34 : 75;
  if (Math.abs(camera.fov - wantFov) > 0.1) {
    camera.fov = lerp(camera.fov, wantFov, Math.min(1, dt * 14));
    camera.updateProjectionMatrix();
  }

  updateHud();
}

function updateEffects(dt) {
  for (let i = tracers.length - 1; i >= 0; i--) {
    const tr = tracers[i];
    tr.life -= dt;
    if (tr.life <= 0) {
      scene.remove(tr.line);
      tr.line.geometry.dispose();
      tr.line.material.dispose();
      tracers.splice(i, 1);
    } else {
      tr.line.material.opacity = 0.85 * (tr.life / tr.max);
    }
  }
  for (let i = bloods.length - 1; i >= 0; i--) {
    const bl = bloods[i];
    bl.life -= dt;
    bl.s.position.y += bl.vy * dt;
    bl.s.material.opacity = Math.max(0, bl.life / bl.max);
    const k = 1 + (1 - bl.life / bl.max) * 0.8;
    bl.s.scale.set(0.3 * k, 0.3 * k, 1);
    if (bl.life <= 0) {
      scene.remove(bl.s);
      bl.s.material.dispose();
      bloods.splice(i, 1);
    }
  }
  for (let i = decals.length - 1; i >= 0; i--) {
    const dc = decals[i];
    dc.life -= dt;
    if (dc.life <= 0) {
      scene.remove(dc.m);
      dc.m.geometry.dispose();
      dc.m.material.dispose();
      decals.splice(i, 1);
    } else if (dc.life < 2) {
      dc.m.material.opacity = 0.9 * dc.life / 2;
    }
  }
  muzzleLight.intensity = Math.max(0, muzzleLight.intensity - dt * 45);
}

// ---------------- 主循环 ----------------
let lastT = performance.now() / 1000;
let fpsAvg = 60;

function menuOrbit(t) {
  const a = t * 0.055 + 1.1;
  camera.fov = 68;
  camera.updateProjectionMatrix();
  camera.position.set(Math.sin(a) * 30, 11.5 + Math.sin(t * 0.16) * 1.4, Math.cos(a) * 26);
  camera.lookAt(0, 1.4, 3);
  vmRoot.visible = false;
}

function tick() {
  requestAnimationFrame(tick);
  const t = performance.now() / 1000;
  let dt = t - lastT;
  lastT = t;
  if (dt > 0.05) dt = 0.05;
  if (dt <= 0) dt = 0.001;
  fpsAvg = fpsAvg * 0.95 + (1 / dt) * 0.05;

  if (G.state === 'menu') {
    menuOrbit(t);
    updateEffects(dt);
    renderer.render(scene, camera);
    return;
  }

  if (!G.paused && !G.buyOpen) {
    updatePlayer(dt, t);
    for (const b of G.bots) b.think(dt, t);
  }
  updateEffects(dt);
  renderer.render(scene, camera);
}

// ---------------- UI 绑定 ----------------
function applySettingsToUI() {
  document.querySelectorAll('.team-card').forEach((b) => {
    b.classList.toggle('active', b.dataset.team === S.team);
  });
  document.querySelectorAll('#diffSegs button').forEach((b) => {
    b.classList.toggle('active', b.dataset.diff === S.diff);
  });
  const sensVal = Math.round(S.sens / 0.0022 * 100);
  $('sens').value = String(clamp(sensVal, 20, 300));
  $('sensVal').textContent = (sensVal / 100).toFixed(2);
  $('vol').value = String(Math.round(S.vol * 100));
  $('volVal').textContent = String(Math.round(S.vol * 100));
}

function bindUI() {
  document.querySelectorAll('.team-card').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.team-card').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      S.team = btn.dataset.team;
      saveSettings();
      Sound.ui();
    });
  });
  document.querySelectorAll('#diffSegs button').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#diffSegs button').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      S.diff = btn.dataset.diff;
      saveSettings();
      Sound.ui();
    });
  });
  $('sens').addEventListener('input', () => {
    const v = +$('sens').value;
    S.sens = 0.0022 * v / 100;
    $('sensVal').textContent = (v / 100).toFixed(2);
    saveSettings();
  });
  $('vol').addEventListener('input', () => {
    const v = +$('vol').value;
    $('volVal').textContent = String(v);
    Sound.init();
    Sound.setVol(v / 100);
  });
  $('startBtn').addEventListener('click', () => {
    Sound.init();
    Sound.ui();
    startGame();
  });
  $('resumeBtn').addEventListener('click', resumeGame);
  $('quitBtn').addEventListener('click', () => location.reload());
  $('respawnBtn').addEventListener('click', () => {
    $('death').classList.add('hidden');
    beginRound();
    requestLock();
  });
  $('deathMenuBtn').addEventListener('click', () => location.reload());

  window.addEventListener('resize', () => {
    renderer.setSize(window.innerWidth, window.innerHeight);
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
  });

  document.addEventListener('keydown', (e) => {
    const code = e.code;
    if (G.state === 'menu' && (code === 'Enter' || code === 'NumpadEnter')) {
      if (document.getElementById('csgate')) return;
      e.preventDefault();
      Sound.init();
      startGame();
      return;
    }
    if (code === 'Tab') {
      e.preventDefault();
      if (G.state === 'playing' && !G.paused) showScore(true);
      return;
    }
    if (code === 'Escape') {
      if (G.buyOpen) { closeBuy(); return; }
      if (G.state === 'playing' && !G.paused && !G.dead) pauseGame();
      return;
    }
    if (G.state !== 'playing') return;
    if (code === 'KeyB') {
      e.preventDefault();
      if (!G.paused && !G.dead) toggleBuy();
      return;
    }
    if (G.paused || G.dead) return;
    if (G.buyOpen && /^Digit[1-6]$/.test(code)) {
      e.preventDefault();
      buyByIndex(+code.slice(5) - 1);
      return;
    }
    keys[code] = true;
    if (code === 'KeyR') startReload();
    if (code === 'Digit1') switchSlot('primary');
    if (code === 'Digit2') switchSlot('pistol');
  });

  document.addEventListener('keyup', (e) => {
    keys[e.code] = false;
    if (e.code === 'Tab') showScore(false);
  });

  canvas.addEventListener('mousedown', (e) => {
    if (G.state !== 'playing' || G.paused || G.dead || G.buyOpen) return;
    if (e.button === 0) {
      if (!document.pointerLockElement) requestLock();
      mouseDown = true;
      tryFire();
    } else if (e.button === 2) {
      const w = currentWeapon();
      if (w && w.id === 'awp') setScope(!scopeOn);
    }
  });
  window.addEventListener('mouseup', (e) => {
    if (e.button === 0) mouseDown = false;
  });
  window.addEventListener('contextmenu', (e) => e.preventDefault());
  document.addEventListener('mousemove', (e) => {
    if (G.state !== 'playing' || G.paused || G.dead || G.buyOpen) return;
    const mx = e.movementX || 0;
    const my = e.movementY || 0;
    const sens = S.sens * (scopeOn ? 0.55 : 1);
    player.yaw -= mx * sens;
    player.pitch = clamp(player.pitch - my * sens, -1.52, 1.52);
  });

  document.addEventListener('pointerlockchange', () => {
    const locked = document.pointerLockElement === canvas;
    if (locked) {
      if (G.paused) {
        G.paused = false;
        $('pause').classList.add('hidden');
      }
    } else if (G.state === 'playing' && !G.paused && !G.dead && !G.roundEnding && !G.buyOpen) {
      pauseGame();
    }
  });

  document.addEventListener('visibilitychange', () => {
    if (document.hidden && G.state === 'playing' && !G.paused && !G.dead) pauseGame();
  });
}

function startGame() {
  Sound.init();
  G.state = 'playing';
  G.paused = false;
  G.dead = false;
  G.roundEnding = false;
  G.buyOpen = false;
  G.pendingRound = false;
  G.round = 0;
  G.roundId = 0;
  G.money = 800;
  G.kills = 0;
  G.deaths = 0;
  G.headshots = 0;
  G.shots = 0;
  G.hits = 0;
  G.roundKills = 0;
  player.health = 100;
  player.armor = 0;
  player.dead = false;
  player.pos.set(0, 0, -23.2);
  player.pitch = 0;
  player.fov = 75;
  loadout.primary = null;
  const pistolId = S.team === 't' ? 'glock' : 'usp';
  loadout.pistol = makeWeapon(pistolId);
  loadout.current = 'pistol';
  setViewmodel();
  document.body.classList.add('playing');
  document.body.classList.remove('buyopen', 'scoped');
  $('menu').classList.add('hidden');
  $('score').classList.add('hidden');
  $('death').classList.add('hidden');
  $('pause').classList.add('hidden');
  $('killfeed').innerHTML = '';
  camera.fov = 75;
  camera.updateProjectionMatrix();
  vmRoot.visible = true;
  beginRound();
  requestLock();
  updateHud();
}

// ---------------- 调试/验证接口 ----------------
window.__game = {
  start: (team, diff) => {
    if (team) S.team = team;
    if (diff) S.diff = diff;
    startGame();
  },
  state: () => ({
    state: G.state, paused: G.paused, dead: G.dead, round: G.round, money: G.money,
    health: +player.health.toFixed(1), armor: Math.round(player.armor),
    pos: { x: +player.pos.x.toFixed(2), y: +player.pos.y.toFixed(2), z: +player.pos.z.toFixed(2) },
    yaw: +player.yaw.toFixed(3), pitch: +player.pitch.toFixed(3),
    weapon: currentWeapon() ? currentWeapon().id : null,
    ammo: currentWeapon() ? currentWeapon().ammo : 0,
    reserve: currentWeapon() ? currentWeapon().reserve : 0,
    reloading, scopeOn, roundEnding: G.roundEnding,
    freeze: Math.max(0, +(G.freezeUntil - nowS()).toFixed(1)),
    bots: G.bots.map((b) => ({
      name: b.name, hp: Math.round(b.hp), alive: b.alive,
      x: +b.pos.x.toFixed(1), z: +b.pos.z.toFixed(1), canSee: b.canSee, mode: b.mode
    })),
    kills: G.kills, deaths: G.deaths, shots: G.shots, hits: G.hits,
    locked: document.pointerLockElement === canvas,
    fps: Math.round(fpsAvg),
    errors: window.__errors.slice(0, 6)
  }),
  look: (dx, dy) => {
    player.yaw -= (dx || 0) * S.sens;
    player.pitch = clamp(player.pitch - (dy || 0) * S.sens, -1.5, 1.5);
  },
  aimAt: (i) => {
    const b = G.bots[i];
    if (!b) return;
    const eyeY = player.pos.y + player.curEye;
    const dx = b.pos.x - player.pos.x;
    const dz = b.pos.z - player.pos.z;
    const dy = 1.55 - eyeY;
    const hd = Math.hypot(dx, dz);
    player.yaw = Math.atan2(-dx, -dz);
    player.pitch = Math.atan2(dy, hd);
  },
  aimPoint: (x, y, z) => {
    const dx = x - player.pos.x;
    const dy = y - (player.pos.y + player.curEye);
    const dz = z - player.pos.z;
    player.yaw = Math.atan2(-dx, -dz);
    player.pitch = Math.atan2(dy, Math.hypot(dx, dz));
  },
  fire: () => tryFire(),
  reload: () => startReload(),
  buy: (i) => buyByIndex(i),
  teleport: (x, z, yaw) => {
    player.pos.set(x, player.pos.y, z);
    if (yaw !== undefined) player.yaw = yaw;
  },
  hurtMe: (n) => damagePlayer(n, '测试'),
  killAll: () => {
    for (const b of G.bots) {
      if (b.alive) damageBot(b, 9999, 'body', b.pos.clone().setY(1.2));
    }
  },
  respawn: () => {
    $('death').classList.add('hidden');
    beginRound();
  },
  pause: () => pauseGame(),
  resume: () => resumeGame(),
  setMoney: (n) => { G.money = clamp(n, 0, 16000); updateHud(); if (G.buyOpen) renderBuyList(); },
  give: (id) => {
    const d = WDEF[id];
    if (!d) return;
    if (d.slot === 'primary') { loadout.primary = makeWeapon(id); loadout.current = 'primary'; }
    else { loadout.pistol = makeWeapon(id); loadout.current = 'pistol'; }
    setViewmodel();
    updateHud();
  },
  openBuy: () => openBuy(),
  closeBuy: () => closeBuy(true)
};

// ---------------- 启动 ----------------
applySettingsToUI();
bindUI();
requestAnimationFrame(tick);

})();
