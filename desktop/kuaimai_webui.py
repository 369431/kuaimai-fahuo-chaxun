# -*- coding: utf-8 -*-
"""内置手机网页界面（打包进 exe，不需要 Node）。

由 kuaimai_scan.py 的内置 HTTP 服务直接返回。
"""

WEB_INDEX_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0b5394">
<title>快麦扫码查询</title>
<style>
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  body { margin:0; font-family:-apple-system,"Microsoft YaHei","PingFang SC",sans-serif; background:#f5f6f8; color:#222; }
  header { background:#0b5394; color:#fff; padding:10px 12px; font-size:16px; font-weight:600; display:flex; justify-content:space-between; align-items:center; }
  header small { font-weight:400; opacity:.85; font-size:12px; }
  .wrap { padding:10px; max-width:640px; margin:0 auto; }
  .card { background:#fff; border-radius:12px; padding:10px; margin-bottom:10px; box-shadow:0 1px 3px rgba(0,0,0,.08); }
  .row { display:flex; gap:8px; align-items:center; }
  input[type=text] { flex:1; font-size:20px; padding:12px; border:2px solid #ccd; border-radius:10px; min-width:0; }
  button { font-size:16px; padding:12px 16px; border:0; border-radius:10px; background:#0b5394; color:#fff; }
  button.ghost { background:#e8eef5; color:#0b5394; }
  button:active { opacity:.75; }
  #result { border-radius:12px; padding:14px; text-align:center; background:#eee; color:#555; margin-bottom:10px; }
  #rcode { font-size:20px; font-weight:800; color:#000; word-break:break-all; }
  #rmain { font-size:20px; font-weight:700; margin-top:6px; line-height:1.5; }
  #rdetail { font-size:14px; color:#333; line-height:1.7; white-space:pre-wrap; }
  .ok { background:#d6f5df; color:#1e9e4a; }
  .bad { background:#fde0e0; color:#c62828; }
  .muted { color:#666; font-size:12px; }
  select, input[type=number] { font-size:15px; padding:8px; border:1px solid #ccd; border-radius:8px; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th,td { padding:6px 4px; border-bottom:1px solid #eee; text-align:left; white-space:nowrap; }
  th { color:#666; font-weight:500; }
  .toolbar { display:flex; gap:8px; flex-wrap:wrap; margin-top:8px; }
  video { width:100%; border-radius:10px; background:#000; }
  .hidden { display:none; }
  .pitem { border:1px solid #e3e6ea; border-radius:10px; padding:10px; margin-bottom:8px; background:#fff; }
  .pitem.done { background:#eefaf1; border-color:#bfe8cd; }
  .pitem.short { background:#fdecec; border-color:#f3c3c3; }
  .pseq { font-size:13px; color:#666; }
  .pcode { font-size:21px; font-weight:800; color:#000; margin:2px 0; }
  .pbin { font-size:16px; }
  .pbtns { display:flex; gap:8px; margin-top:8px; }
  .pbtns button { flex:1; padding:11px 8px; font-size:15px; }
  button.pdone { background:#1e9e4a; }
  button.pshort { background:#c62828; }
  .pstate { font-size:12px; color:#666; margin-top:5px; }
  /* ================= macOS 风格（覆盖上面的基础样式） ================= */
  :root { --mac-blue:#007AFF; --mac-green:#34C759; --mac-red:#FF3B30; --mac-ink:#1d1d1f; --mac-sub:#6e6e73;
          --mac-line:rgba(60,60,67,.12); --mac-fill:rgba(120,120,128,.12); --mac-glass:rgba(255,255,255,.72); }
  html { -webkit-text-size-adjust:100%; }
  body { font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
         letter-spacing:-.01em; -webkit-font-smoothing:antialiased; color:var(--mac-ink);
         background:linear-gradient(170deg,#eef3fa 0%,#e6edf8 45%,#e1e8f4 100%) fixed; min-height:100vh; }
  header { background:var(--mac-glass); color:var(--mac-ink); backdrop-filter:saturate(180%) blur(20px);
           -webkit-backdrop-filter:saturate(180%) blur(20px); border-bottom:1px solid var(--mac-line);
           font-size:17px; font-weight:600; position:sticky; top:0; z-index:20; }
  header small { color:var(--mac-sub); }
  .card, #result, .pitem { background:var(--mac-glass); backdrop-filter:saturate(180%) blur(20px);
           -webkit-backdrop-filter:saturate(180%) blur(20px); border:1px solid rgba(255,255,255,.62);
           border-radius:18px; box-shadow:0 10px 30px rgba(24,39,75,.08), 0 1px 2px rgba(24,39,75,.05); }
  input[type=text], input, select, input[type=number] { background:rgba(255,255,255,.86);
           border:1px solid var(--mac-line); border-radius:12px; color:var(--mac-ink); }
  input[type=text]:focus, input:focus { outline:none; border-color:var(--mac-blue);
           box-shadow:0 0 0 3.5px rgba(0,122,255,.16); }
  button { font-family:inherit; font-weight:600; border-radius:12px; background:var(--mac-blue); color:#fff;
           box-shadow:0 1px 2px rgba(0,0,0,.10); transition:transform .08s ease, opacity .12s ease; }
  button.ghost { background:var(--mac-fill); color:var(--mac-blue); box-shadow:none; }
  button:active { transform:scale(.97); opacity:.9; }
  #rcode, .pcode { color:#000; letter-spacing:-.02em; }
  #rmain { letter-spacing:-.02em; }
  #rdetail { color:#3a3a3c; }
  .ok { background:rgba(52,199,89,.15); color:#1B7F35; }
  .bad { background:rgba(255,59,48,.12); color:#C7362E; }
  .muted { color:var(--mac-sub); }
  th,td { border-bottom:1px solid rgba(60,60,67,.08); }
  th { color:var(--mac-sub); }
  .pitem.done { background:rgba(52,199,89,.14); border-color:rgba(52,199,89,.35); }
  .pitem.short { background:rgba(255,59,48,.12); border-color:rgba(255,59,48,.32); }
  .pqty { color:var(--mac-red); letter-spacing:-.02em; }
  .pqty.done { color:var(--mac-green); }
  button.pdone { background:var(--mac-green); }
  button.pshort { background:var(--mac-red); }
  .pzone { background:var(--mac-blue); border-radius:7px; font-weight:600; }
  .zones, .filters { background:var(--mac-fill); border-radius:12px; padding:3px; gap:3px; border:0; }
  .zones button, .filters button { background:transparent; color:#3c3c43; box-shadow:none; border-radius:9px; font-weight:600; }
  .zones button:not(.ghost), .filters button:not(.ghost) { background:#fff; color:#000;
           box-shadow:0 1px 3px rgba(0,0,0,.14); }
  .bar { background:var(--mac-glass); backdrop-filter:saturate(180%) blur(20px);
         -webkit-backdrop-filter:saturate(180%) blur(20px); border-top:1px solid var(--mac-line); }
  .row4 button { border-radius:10px; }
  @media (prefers-color-scheme: dark) {
    body { background:linear-gradient(170deg,#1c1c1e,#151517 60%,#1a1a1c) fixed; color:#f2f2f7; }
    header { background:rgba(28,28,30,.72); color:#f2f2f7; border-bottom-color:rgba(255,255,255,.08); }
    .card, #result, .pitem, .bar { background:rgba(28,28,30,.72); border-color:rgba(255,255,255,.08); }
    #rcode, .pcode { color:#fff; }
    input, select, input[type=number] { background:rgba(118,118,128,.24); border-color:rgba(255,255,255,.12); color:#f2f2f7; }
    .zones button, .filters button { color:#ebebf5; }
    .zones button:not(.ghost), .filters button:not(.ghost) { background:rgba(255,255,255,.18); color:#fff; }
    #rdetail { color:#d1d1d6; }
  }
</style>
</head>
<body>
<header><span>快麦扫码查询</span><small id="hdr">连接中…</small></header>
<div class="wrap">
  <div class="card">
    <div class="row">
      <input id="code" type="text" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="扫商家编码…" autofocus>
      <button id="btnQuery" class="ghost">查询</button>
    </div>
    <div class="toolbar">
      <button id="btnCam" class="ghost">摄像头扫码</button>
      <button id="btnPick" class="ghost">拣货</button>
      <button id="btnSound" class="ghost">声音：开</button>
    </div>
    <div id="camBox" class="hidden" style="margin-top:8px">
      <video id="video" playsinline muted></video>
      <div class="toolbar"><button id="btnCamStop" class="ghost">关闭摄像头</button></div>
    </div>
  </div>
  <div id="result">
    <div id="rcode">就绪</div>
    <div id="rmain">扫码后显示</div>
    <div id="rdetail"></div>
  </div>
  <div class="card">
    <div class="row" style="flex-wrap:wrap">
      <span class="muted">订单商品数量筛选</span>
      <select id="rel"><option value="any">不限</option><option value="gt">大于</option><option value="lt">小于</option><option value="eq">等于</option></select>
      <input id="num" type="number" value="1" style="width:70px">
      <button id="btnApply" class="ghost">应用</button>
    </div>
    <div class="muted" id="stat" style="margin-top:6px">—</div>
  </div>
  <div class="card">
    <div class="row" style="justify-content:space-between">
      <b>扫码记录</b>
      <span><button id="btnCsv" class="ghost">导出CSV</button><button id="btnClear" class="ghost">清空</button></span>
    </div>
    <div style="max-height:44vh; overflow:auto; margin-top:6px">
      <table id="hist"><thead><tr><th>时间</th><th>商家编码</th><th>订单数</th><th>在架</th><th>件数</th><th>提示</th></tr></thead><tbody></tbody></table>
    </div>
  </div>
</div>
<script>
const $ = (id) => document.getElementById(id);
const K = new URLSearchParams(location.search).get('k') || localStorage.getItem('km_key') || '';
if (K) localStorage.setItem('km_key', K);
const KQ = '&k=' + encodeURIComponent(K);
let SOUND = true, hist = [];
try { hist = JSON.parse(localStorage.getItem('km_hist') || '[]'); } catch (e) { hist = []; }
function saveHist(){ try { localStorage.setItem('km_hist', JSON.stringify(hist.slice(-500))); } catch(e){} }
function fmtTime(d){ const p=x=>String(x).padStart(2,'0'); return `${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`; }
function beep(ok){
  if(!SOUND) return;
  try { const Ctx=window.AudioContext||window.webkitAudioContext, ctx=new Ctx();
    for (const [f,t] of (ok?[[880,0],[1250,.12]]:[[500,0],[500,.24],[500,.48]])) {
      const o=ctx.createOscillator(), g=ctx.createGain(); o.frequency.value=f; o.type='sine'; g.gain.value=.15;
      o.connect(g); g.connect(ctx.destination); o.start(ctx.currentTime+t); o.stop(ctx.currentTime+t+.1);
    } setTimeout(()=>ctx.close(),900);
  } catch(e){}
}
function renderHistory(){
  const tb=$('hist').querySelector('tbody'); tb.innerHTML='';
  for (const r of hist.slice().reverse()) {
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${r.t}</td><td>${r.code}</td><td>${r.orders}</td><td>${r.shelf}</td><td>${r.pieces}</td><td>${r.hint||''}</td>`;
    tb.appendChild(tr);
  }
}
async function loadStatus(){
  try {
    const s=await (await fetch('/api/status?k='+encodeURIComponent(K))).json();
    $('stat').textContent =
      `待发货口径 ${s.live_orders} 单（剔除 ${s.shipped_excluded}，按条件加载 ${s.included_orders}）；编码 ${s.codes} 个`
      + `\n数据时间 ${s.loaded_at}；货位 ${s.shelf_at}；锁定数 ${s.lock_at}`;
    $('hdr').textContent='数据 '+(s.loaded_at||'—').slice(5,16);
  } catch(e){ $('hdr').textContent='连接失败'; }
}
async function query(code){
  code=(code||'').trim(); if(!code) return;
  const rel=$('rel').value, n=Number($('num').value||0);
  $('rcode').textContent=code; $('rmain').textContent='查询中…';
  let d;
  try { d=await (await fetch(`/api/lookup?code=${encodeURIComponent(code)}&rel=${rel}&n=${n}${KQ}`)).json(); }
  catch(e){ $('rmain').textContent='网络错误：'+e.message; return; }
  if(d.error){ $('rmain').textContent=d.error; return; }
  if(d.series){
    $('result').className='';
    $('rcode').textContent = d.code + '（主编码）';
    $('rmain').textContent = '共 ' + d.items.length + ' 个规格';
    $('rdetail').innerHTML = d.items.map(function(it){
      return '<div>' + it.code + '　<b>' + it.bins + '</b>　在架 ' + it.shelf
           + '　待发 ' + it.qty + ' 件' + (it.lock ? ('　锁定 ' + it.lock) : '') + '</div>';
    }).join('');
    beep(true);
    $('code').value=''; $('code').focus();
    return;
  }
  const ok=d.orders>0;
  $('result').className = ok?'ok':'bad';
  // 一单一件：整单只有一件的单（每单正好 1 件）；剩下抵成一单多件
  const onePiece=Math.min(d.ones||0, d.pieces||0), multiPiece=Math.max(0, (d.pieces||0)-onePiece);
  const bins=(d.bins||[]).map(b=>`${b[0]}×${b[1]}`).join('、')||'无在架货位';
  const short=d.pieces>d.shelf;          // 在架少于待发货件数 → 需补货
  $('rcode').textContent = d.code;
  $('rmain').innerHTML = `待发货一单一件：${onePiece}<br>待发货一单多件：${multiPiece}`;
  $('rdetail').innerHTML = `货位：${bins}（在架 ${d.shelf}）`
    + (short ? '<br><span style="color:#c62828;font-weight:800;font-size:22px">需补货</span>' : '');
  const hint = d.orders===0 ? '没有待发货订单' : (short ? '需补货' : '可以拣货');
  hist.push({t:fmtTime(new Date()), code:d.code, orders:d.orders, shelf:d.shelf, pieces:d.pieces, hint});
  saveHist(); renderHistory(); beep(ok);
  $('code').value=''; $('code').focus();
}
// 扫码枪：自带回车 → 直接查询；手动打字时不自动查，点「查询」或按回车才查
$('code').addEventListener('keydown', e=>{ if(e.key==='Enter'){ e.preventDefault(); query($('code').value); } });
$('btnQuery').onclick=()=>query($('code').value);
$('btnApply').onclick=()=>{ loadStatus(); if(hist.length) query(hist[hist.length-1].code); };
$('btnSound').onclick=()=>{ SOUND=!SOUND; $('btnSound').textContent='声音：'+(SOUND?'开':'关'); };
$('btnClear').onclick=()=>{ if(confirm('清空本机扫码记录？')){ hist=[]; saveHist(); renderHistory(); } };
$('btnCsv').onclick=()=>{
  const head='时间,商家编码,待发货订单数,货架在架数,件数,提示\n';
  const body=hist.map(r=>[r.t,r.code,r.orders,r.shelf,r.pieces,(r.hint||'')].join(',')).join('\n');
  const blob=new Blob(['\ufeff'+head+body],{type:'text/csv;charset=utf-8'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='扫码记录_'+Date.now()+'.csv'; a.click();
};
let stream=null, scanTimer=null;
async function startCam(){
  if(!('BarcodeDetector' in window)){ alert('此浏览器不支持摄像头识别条码，请用扫码枪或手动输入'); return; }
  try { stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'environment'}}); }
  catch(e){ alert('无法打开摄像头：'+e.message); return; }
  $('camBox').classList.remove('hidden'); $('video').srcObject=stream; await $('video').play();
  const det=new window.BarcodeDetector();
  scanTimer=setInterval(async()=>{ try { const c=await det.detect($('video')); if(c&&c.length){ stopCam(); query(c[0].rawValue); } } catch(e){} },400);
}
function stopCam(){ clearInterval(scanTimer); if(stream){ stream.getTracks().forEach(t=>t.stop()); stream=null; } $('camBox').classList.add('hidden'); }
$('btnCam').onclick=startCam; $('btnCamStop').onclick=stopCam;
/* ---------------- 拣货：独立页面 /pick ---------------- */
$('btnPick').onclick = () => {
  const sid = (function(){ try { return localStorage.getItem('km_sid') || ''; } catch(e){ return ''; } })();
  const q = {k:K}; if(sid) q.sid = sid;
  location.href = '/pick?' + new URLSearchParams(q).toString();
};
/* 有未结束的批次时，按钮上直接显示可以继续 */
fetch('/api/pick/current?' + new URLSearchParams({k:K}).toString())
  .then(r => r.json())
  .then(d => {
    if(d && d.running){
      const b = $('btnPick');
      b.textContent = '拣货（继续 ' + d.batch + '）';
      b.classList.remove('ghost');
    }
  }).catch(() => {});

/* 会话：登录后从 URL 取一次 token，之后自动附加到所有请求；失效则回登录页 */
(function(){
  try { var q = new URLSearchParams(location.search).get('sid'); if(q) localStorage.setItem('km_sid', q); } catch(e){}
  var _f = window.fetch;
  window.fetch = function(u, o){
    try { var t = localStorage.getItem('km_sid');
      if(t && typeof u === 'string' && u.indexOf('sid=') < 0){ u += (u.indexOf('?') >= 0 ? '&' : '?') + 'sid=' + encodeURIComponent(t); }
    } catch(e){}
    return _f(u, o).then(function(r){ if(r.status === 401){ location.href = '/login'; } return r; });
  };
})();

renderHistory(); loadStatus(); setInterval(loadStatus,60000);
</script>
</body>
</html>
"""


# 独立的拣货页（手机端「拣货」按钮进入 /pick）
PICK_HTML = r"""<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>拣货 · 快麦发货查询</title>
<style>
  body { margin:0; font-family:system-ui,-apple-system,"Microsoft YaHei",sans-serif; background:#f5f6f8; padding:10px 10px 78px; }
  h1 { font-size:17px; margin:2px 0 8px; color:#0b5394; }
  .card { background:#fff; border-radius:12px; padding:10px; margin-bottom:10px; box-shadow:0 1px 3px rgba(0,0,0,.06); }
  .row { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
  input { flex:1; min-width:130px; padding:12px; font-size:18px; border:1px solid #cfd4da; border-radius:10px; }
  button { padding:12px 14px; font-size:16px; border:0; border-radius:10px; background:#0b5394; color:#fff; font-weight:600; }
  button.ghost { background:#eef1f4; color:#223; }
  .muted { color:#666; font-size:13px; }
  .pitem { border:1px solid #e3e6ea; border-radius:12px; padding:12px; margin-bottom:10px; background:#fff; }
  .pitem.done { background:#eefaf1; border-color:#bfe8cd; }
  .pitem.short { background:#fdecec; border-color:#f3c3c3; }
  .pseq { font-size:13px; color:#666; }
  .pcode { font-size:25px; font-weight:800; color:#000; margin:3px 0; }
  .pbin { font-size:19px; }
  .pmeta { font-size:13px; color:#555; margin-top:5px; line-height:1.7; }
  .pqty { font-size:24px; font-weight:800; color:#c62828; margin:4px 0 2px; }
  .pqty.done { color:#1e9e4a; }
  .pitem.one { padding:16px; border-width:2px; }
  .pitem.one .pcode { font-size:32px; }
  .pitem.one .pqty { font-size:31px; }
  .pitem.one .pbin { font-size:22px; }
  .pitem.one .pseq { font-size:14px; }
  .pitem.one .pbtns button { padding:19px 8px; font-size:20px; }
  .pbtns { display:flex; gap:8px; margin-top:9px; }
  .pbtns button { flex:1; padding:15px 8px; font-size:17px; }
  button.pdone { background:#1e9e4a; }
  button.pshort { background:#c62828; }
  .filters { display:flex; gap:6px; margin:8px 0; position:sticky; top:0; background:#f5f6f8; padding:6px 0; z-index:5; }
  .filters button { flex:1; padding:9px 4px; font-size:14px; }
  .bar { position:fixed; left:0; right:0; bottom:0; background:#fff; border-top:1px solid #e3e6ea; padding:8px 10px; display:flex; gap:8px; }
  .bar button { flex:1; }
  .row4 { display:flex; gap:6px; }
  .row4 button { flex:1; padding:8px 2px; font-size:13px; white-space:nowrap; }
  .pzone { display:inline-block; background:#0b5394; color:#fff; border-radius:6px; padding:1px 8px;
           font-size:14px; margin-left:8px; vertical-align:middle; }
  .zones { display:flex; gap:6px; margin:8px 0; flex-wrap:wrap; }
  .zones button { flex:1; padding:11px 6px; font-size:15px; white-space:nowrap; }
  .hidden { display:none; }
  pre { white-space:pre-wrap; font-family:ui-monospace,Consolas,"Microsoft YaHei",monospace; font-size:14px; margin:0; }
  /* ================= macOS 风格（覆盖上面的基础样式） ================= */
  :root { --mac-blue:#007AFF; --mac-green:#34C759; --mac-red:#FF3B30; --mac-ink:#1d1d1f; --mac-sub:#6e6e73;
          --mac-line:rgba(60,60,67,.12); --mac-fill:rgba(120,120,128,.12); --mac-glass:rgba(255,255,255,.72); }
  html { -webkit-text-size-adjust:100%; }
  body { font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
         letter-spacing:-.01em; -webkit-font-smoothing:antialiased; color:var(--mac-ink);
         background:linear-gradient(170deg,#eef3fa 0%,#e6edf8 45%,#e1e8f4 100%) fixed; min-height:100vh; }
  h1 { font-size:24px; font-weight:700; color:var(--mac-ink); letter-spacing:-.02em; margin:2px 2px 12px; }
  .card { background:var(--mac-glass); backdrop-filter:saturate(180%) blur(20px);
          -webkit-backdrop-filter:saturate(180%) blur(20px); border:1px solid rgba(255,255,255,.62);
          border-radius:18px; padding:14px; box-shadow:0 10px 30px rgba(24,39,75,.08), 0 1px 2px rgba(24,39,75,.05); }
  input { background:rgba(255,255,255,.86); border:1px solid var(--mac-line); border-radius:12px;
          color:var(--mac-ink); padding:13px 14px; font-size:19px; }
  input:focus { outline:none; border-color:var(--mac-blue); box-shadow:0 0 0 3.5px rgba(0,122,255,.16); }
  button { font-family:inherit; font-weight:600; border-radius:12px; background:var(--mac-blue); color:#fff;
           box-shadow:0 1px 2px rgba(0,0,0,.10); transition:transform .08s ease, opacity .12s ease; }
  button.ghost { background:var(--mac-fill); color:var(--mac-blue); box-shadow:none; }
  button:active { transform:scale(.97); opacity:.9; }
  .muted { color:var(--mac-sub); }
  .pitem { background:var(--mac-glass); backdrop-filter:saturate(180%) blur(20px);
           -webkit-backdrop-filter:saturate(180%) blur(20px); border:1px solid rgba(255,255,255,.62);
           border-radius:18px; padding:14px; box-shadow:0 10px 30px rgba(24,39,75,.08), 0 1px 2px rgba(24,39,75,.05); }
  .pitem.done { background:rgba(52,199,89,.14); border-color:rgba(52,199,89,.35); }
  .pitem.short { background:rgba(255,59,48,.12); border-color:rgba(255,59,48,.32); }
  .pitem.one { border-width:1px; padding:20px; box-shadow:0 14px 40px rgba(24,39,75,.12), 0 1px 2px rgba(24,39,75,.05); }
  .pitem.one .pcode { font-size:34px; }
  .pline { display:flex; align-items:center; gap:8px; padding:9px 10px; border-radius:11px;
           background:rgba(120,120,128,.10); margin:6px 0; font-size:15px; flex-wrap:wrap; }
  .pline.cur { background:rgba(0,122,255,.14); box-shadow:0 0 0 2px rgba(0,122,255,.35) inset; }
  .pline.done { background:rgba(52,199,89,.18); }
  .pline.short { background:rgba(255,59,48,.16); }
  .pno { min-width:18px; text-align:center; color:#6e6e73; font-size:13px; }
  .pcode2 { font-weight:800; font-size:17px; letter-spacing:-.01em; }
  .pqty2 { font-weight:800; color:#FF3B30; white-space:nowrap; }
  .pbin2 { color:#1d1d1f; white-space:nowrap; }
  .pst { color:#6e6e73; font-size:12.5px; white-space:nowrap; margin-left:auto; }
  .pprog { font-size:15px; color:#6e6e73; font-weight:600; }
  .pmeta2 { font-size:13.5px; color:#3a3a3c; margin-top:4px; line-height:1.6; }
  .pitem.one .pqty { font-size:33px; }
  .pitem.one .pbin { font-size:23px; }
  .pitem.one .pbtns button { padding:20px 8px; font-size:20px; border-radius:14px; }
  .pcode { color:#000; letter-spacing:-.02em; }
  .pqty { color:var(--mac-red); letter-spacing:-.02em; }
  .pqty.done { color:var(--mac-green); }
  button.pdone { background:var(--mac-green); }
  button.pshort { background:var(--mac-red); }
  .pzone { background:var(--mac-blue); border-radius:7px; font-weight:600; }
  .zones, .filters { background:var(--mac-fill); border-radius:12px; padding:3px; gap:3px; border:0; }
  .zones button, .filters button { background:transparent; color:#3c3c43; box-shadow:none; border-radius:9px; font-weight:600; }
  .zones button:not(.ghost), .filters button:not(.ghost) { background:#fff; color:#000;
           box-shadow:0 1px 3px rgba(0,0,0,.14); }
  .bar { background:var(--mac-glass); backdrop-filter:saturate(180%) blur(20px);
         -webkit-backdrop-filter:saturate(180%) blur(20px); border-top:1px solid var(--mac-line); }
  .row4 button { border-radius:10px; }
  @media (prefers-color-scheme: dark) {
    body { background:linear-gradient(170deg,#1c1c1e,#151517 60%,#1a1a1c) fixed; color:#f2f2f7; }
    h1 { color:#f2f2f7; }
    .card, .pitem, .bar { background:rgba(28,28,30,.72); border-color:rgba(255,255,255,.08); }
    .pcode { color:#fff; }
    input { background:rgba(118,118,128,.24); border-color:rgba(255,255,255,.12); color:#f2f2f7; }
    .zones button, .filters button { color:#ebebf5; }
    .zones button:not(.ghost), .filters button:not(.ghost) { background:rgba(255,255,255,.18); color:#fff; }
  }
</style></head><body>
<h1>拣货</h1>
<div class="card">
  <div class="row">
    <input id="pbatch" inputmode="numeric" autocomplete="off" placeholder="打印批次号">
    <button id="btnGo">开始拣货</button>
  </div>
  <div class="row row4" style="margin-top:8px">
    <button id="btnRefresh" class="ghost">重新拉取</button>
    <button id="btnEnd" class="ghost">结束批次</button>
    <button id="btnSpeak" class="ghost">播报：开</button>
    <button id="btnHome" class="ghost">返回扫码</button>
  </div>
  <div id="pinfo" class="muted" style="margin-top:8px">—</div>
</div>
<div class="zones" id="zones"></div>
<div class="filters" id="filters">
  <button data-f="one">单条</button>
  <button id="btnZone">按分区拣货</button>
  <button data-f="pending" class="ghost">待拣</button>
  <button data-f="all" class="ghost">全部</button>
  <button data-f="done" class="ghost">已完成</button>
  <button data-f="short" class="ghost">无货</button>
</div>
<div id="plist"></div>
<div id="psumbox" class="card hidden"><pre id="psum"></pre></div>
<div class="bar">
  <button id="btnSum" class="ghost">按货位汇总</button>
  <button id="btnEnd2">结束批次</button>
</div>
<script>
const K = new URLSearchParams(location.search).get('k') || '';
const $ = function(id){ return document.getElementById(id); };
let PICK = null, FILTER = 'pending', MODE = 'one', SUM_ON = false;
let SPOKE = false;
/* 按分区拣货：默认开，顺序 A → B → C → D（记在手机上） */
let ZONE = localStorage.getItem('pick_zone') !== '0';
function zoneOf(bins){
  const m = String(bins || '').match(/^\s*([A-Za-z])/);
  return m ? m[1].toUpperCase() : '';
}
function zoneRank(z){
  const i = 'ABCD'.indexOf(z);
  return i >= 0 ? i : 9;          // A/B/C/D 依次，其他分区排最后
}
/* 手动选一个分区先拣（''=全部）；记在手机上 */
let ZPICK = localStorage.getItem('pick_zone_only') || '';
function lineState(l){ return (l && l.state) || 'pending'; }
function orderState(o){
  const ls = (o && o.lines) || [];
  if(!ls.length) return 'done';
  if(ls.some(function(l){ return lineState(l) === 'pending'; })) return 'pending';
  if(ls.some(function(l){ return l.state === 'short'; })) return 'short';
  return 'done';
}
function nextLine(o){
  const ls = (o && o.lines) || [];
  for(let i = 0; i < ls.length; i++){ if(lineState(ls[i]) === 'pending') return { l: ls[i], i: i }; }
  return null;
}
function orderZone(o){
  const it = nextLine(o) || ((o && o.lines && o.lines.length) ? { l: o.lines[0] } : null);
  return it ? zoneOf(it.l.bins) : '';
}
/* 每个区还剩多少个待拣商品 */
function zoneCounts(){
  const out = {};
  (PICK && PICK.orders ? PICK.orders : []).forEach(function(o){
    (o.lines || []).forEach(function(l){
      if(lineState(l) !== 'pending') return;
      const z = zoneOf(l.bins) || '无货位';
      out[z] = (out[z] || 0) + 1;
    });
  });
  return out;
}
function renderZones(){
  const box = $('zones');
  if(!box) return;
  if(!PICK){ box.innerHTML = ''; return; }
  const cnt = zoneCounts();
  const zs = Object.keys(cnt).sort(function(a, b){ return zoneRank(a) - zoneRank(b); });
  let html = '<button data-z=""' + (ZPICK === '' ? '' : ' class="ghost"') + '>全部</button>';
  zs.forEach(function(z){
    const p = cnt[z];
    const label = (z === '无货位') ? '无货位' : (z + '区');
    html += '<button data-z="' + z + '"' + (ZPICK === z ? '' : ' class="ghost"')
         + (p === 0 ? ' style="opacity:.45"' : '') + '>' + label + (p ? (' ' + p) : ' ✓') + '</button>';
  });
  box.innerHTML = html;
  box.querySelectorAll('button').forEach(function(b){
    b.onclick = function(){
      ZPICK = b.dataset.z || '';
      localStorage.setItem('pick_zone_only', ZPICK);
      renderZones(); render(); speakCurrent();
    };
  });
}
/* 按分区排序的「单」列表（[{o:单,i:下标}]），分区内按打印序号 */
function orderedOrders(){
  let os = (PICK && PICK.orders ? PICK.orders : []).map(function(o, i){ return { o: o, i: i }; });
  if(ZPICK){
    os = os.filter(function(it){
      return (it.o.lines || []).some(function(l){ return (zoneOf(l.bins) || '无货位') === ZPICK; });
    });
  }
  if(!ZONE) return os;
  return os.sort(function(a, b){
    return (zoneRank(orderZone(a.o)) - zoneRank(orderZone(b.o)))
        || ((a.o.seq || 0) - (b.o.seq || 0));
  });
}
function url(p, obj){ return p + '?' + new URLSearchParams(Object.assign({k:K}, obj||{})).toString(); }
function beep(ok){ try { const c = new (window.AudioContext||window.webkitAudioContext)();
  const o = c.createOscillator(); o.frequency.value = ok?880:220; o.connect(c.destination); o.start();
  setTimeout(function(){ o.stop(); c.close(); }, ok?120:320); } catch(e){} }
/* 语音播报（Web Speech API；需先点一下页面，浏览器才允许发声） */
let SPEAK_ON = localStorage.getItem('pick_speak') !== '0';
function speakBtn(){
  const b = $('btnSpeak');
  b.textContent = '播报：' + (SPEAK_ON ? '开' : '关');
  b.className = SPEAK_ON ? '' : 'ghost';
}
function speak(text){
  if(!SPEAK_ON) return;
  try {
    if(!window.speechSynthesis) return;
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = 'zh-CN'; u.rate = 1.15;
    u.onstart = function(){ SPOKE = true; };
    speechSynthesis.speak(u);
  } catch(e){}
}
const CN_DIGIT = {'0':'零','1':'一','2':'二','3':'三','4':'四','5':'五','6':'六','7':'七','8':'八','9':'九'};
/* 编码里的数字逐位念：7275 → “七二七五”（不然 TTS 会念成七千二百七十五） */
function speakCode(code){
  return String(code||'')
    .replace(/[0-9]/g, function(d){ return CN_DIGIT[d] || d; })
    .replace(/[-_\/]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}
function currentOrder(){
  const os = orderedOrders();
  for(let i = 0; i < os.length; i++){ if(orderState(os[i].o) === 'pending') return os[i]; }
  return null;
}
/* 播报当前要拣的那一个商品：分区 + （第 k/L 个）+ 编码 数量 */
function speakCurrent(){
  const it = currentOrder();
  const nl = it ? nextLine(it.o) : null;
  if(!nl){
    if(ZPICK){
      const cnt = zoneCounts();
      const rest = Object.keys(cnt).filter(function(z){ return z !== ZPICK && cnt[z] > 0; });
      speak(rest.length ? (ZPICK + '拣完，还剩 ' + rest.join(' ')) : (ZPICK + '拣完'));
    } else {
      speak('全部拣完');
    }
    return;
  }
  const z = zoneOf(nl.l.bins);
  const total = (it.o.lines || []).length;
  const pre = (total > 1) ? ('第 ' + (nl.i + 1) + '/' + total + ' 个 ') : '';
  speak((z ? (z + '区 ') : '') + pre + speakCode(nl.l.code) + ' ' + nl.l.qty + ' 件');
}
/* 浏览器要求先点一下才允许发声：加载时的播报被拦了就在第一次点按时补播 */
function armFirstTapSpeak(){
  const once = function(){ if(!SPOKE) speakCurrent(); };
  document.addEventListener('touchend', once, {once:true});
  document.addEventListener('mouseup', once, {once:true});
}
$('btnSpeak').onclick = function(){
  SPEAK_ON = !SPEAK_ON;
  localStorage.setItem('pick_speak', SPEAK_ON ? '1' : '0');
  speakBtn();
  if(SPEAK_ON) speak('播报已开启');
};

async function loadCurrent(){
  try { const d = await (await fetch(url('/api/pick/current'))).json();
    if(d && d.running){ PICK = d; $('pbatch').value = d.batch || ''; render(); speakCurrent(); armFirstTapSpeak(); } } catch(e){}
}
async function go(batch, days, refresh){
  $('pinfo').textContent = '查询中…（拉打印记录 + 订单明细，十几秒）';
  $('plist').innerHTML = '';
  try {
    const d = await (await fetch(url('/api/pick/list', {batch:batch||'', days:days||3, refresh:refresh?'1':'0'}))).json();
    if(d.error){ $('pinfo').textContent = d.error; return; }
    PICK = d; $('pbatch').value = d.batch || ''; render(); speakCurrent(); armFirstTapSpeak();
  } catch(e){ $('pinfo').textContent = '网络错误：' + e.message; }
}
function render(){
  if(!PICK) return;
  const pr = PICK.progress || {};
  $('pinfo').innerHTML = '批次 <b>' + (PICK.batch||'') + '</b>（' + (PICK.status==='ended'?'已结束':'进行中') + '）'
    + ' · 待拣货 <b>' + (pr.orders_pending||0) + '</b> 单'
    + ' · 共 <b>' + (pr.lines||0) + '</b> 个商品'
    + ' · 已拣 <b>' + (pr.done||0) + '</b> 个商品'
    + ((pr.short||0) ? (' · 无货 ' + pr.short + ' 个') : '');
  renderZones();
  const box = $('plist'); box.innerHTML = '';
  let list = [];
  if(MODE === 'one'){
    const it = currentOrder();
    if(it) list.push(it);
  } else {
    orderedOrders().forEach(function(it){
      if(FILTER === 'all' || orderState(it.o) === FILTER) list.push(it);
    });
  }
  if(!list.length){
    let msg = (MODE === 'one' ? '本批次已全部拣完（含无货）' : '这个筛选下没有条目。');
    if(MODE === 'one' && ZPICK){
      const cnt = zoneCounts();
      const rest = Object.keys(cnt).filter(function(z){ return z !== ZPICK && cnt[z] > 0; });
      msg = rest.length
        ? (ZPICK + '已拣完；还有 ' + rest.map(function(z){ return z + ' ' + cnt[z]; }).join('、') + ' 个商品待拣')
        : (ZPICK + '已拣完，全批次也没了');
    }
    box.innerHTML = '<div class="card muted">' + msg + '</div>';
  }
  list.forEach(function(it){
    const o = it.o, oi = it.i;
    const st = orderState(o);
    const ls = o.lines || [];
    const pending = ls.filter(function(l){ return lineState(l) === 'pending'; }).length;
    const nl = nextLine(o);
    const div = document.createElement('div');
    div.className = 'pitem' + (MODE === 'one' ? ' one' : '')
      + (st === 'done' ? ' done' : (st === 'short' ? ' short' : ''));
    const rng = (o.seq_b && o.seq_b !== o.seq) ? ('第 ' + o.seq + '-' + o.seq_b + ' 张') : ('第 ' + o.seq + ' 张');
    let linesHtml = '';
    if(MODE === 'one'){
      ls.forEach(function(l, li){
        const lst = lineState(l);
        const cur = nl && nl.i === li;
        const nb = (!l.bins || l.bins === '无在架货位');
        linesHtml += '<div class="pline' + (lst==='done'?' done':(lst==='short'?' short':'')) + (cur?' cur':'') + '">'
          + '<span class="pno">' + (li+1) + '</span>'
          + '<span class="pcode2">' + (l.code||'（无明细）') + '</span>'
          + '<span class="pqty2">需 ' + l.qty + ' 件</span>'
          + '<span class="pbin2">' + (nb ? '<b style="color:#FF9500">无货位</b>' : ('货位 ' + l.bins)) + '</span>'
          + '<span class="pst">' + (lst==='done'?'✓ 已拣':(lst==='short'?(nb?'无货位':'无货'):'待拣')) + '</span>'
          + '</div>';
      });
    } else {
      linesHtml = '<div class="pmeta2">共 ' + ls.length + ' 个商品 · ' + ls.reduce(function(a, l){ return a + (l.qty||0); }, 0) + ' 件 · 已拣 ' + (ls.length - pending) + ' 个'
        + (nl ? ('　下一个：' + nl.l.code + ' ×' + nl.l.qty + ' → '
                + ((!nl.l.bins || nl.l.bins === '无在架货位') ? '无货位' : nl.l.bins)) : '')
        + '</div>';
    }
    const pieces = ls.reduce(function(a, l){ return a + (l.qty || 0); }, 0);
    div.innerHTML = '<div class="pseq">' + rng + (o.express ? (' · 快递单号 ' + o.express) : '') + '</div>'
      + '<div class="pqty' + (st==='done'?' done':'') + '">需拣 ' + pieces + ' 件'
      + '　<span class="pprog">共 ' + ls.length + ' 个商品 · 已拣 ' + (ls.length - pending) + '/' + ls.length + '</span></div>'
      + linesHtml
      + ((MODE === 'one' && nl)
          ? ('<div class="pbtns">'
             + '<button class="pdone" data-o="' + oi + '" data-l="' + nl.i + '" data-s="done">拣货完成</button>'
             + '<button class="pshort" data-o="' + oi + '" data-l="' + nl.i + '" data-s="short">'
             + ((!nl.l.bins || nl.l.bins === '无在架货位') ? '无货位' : '无货') + '</button>'
             + '</div>')
          : '');
    box.appendChild(div);
  });
  box.querySelectorAll('button[data-o]').forEach(function(b){
    b.onclick = function(){ mark(parseInt(b.dataset.o, 10), parseInt(b.dataset.l, 10), b.dataset.s); };
  });
  // 按货位汇总（只算待拣的）
  const sum = {};
  (PICK.orders||[]).forEach(function(o){
    (o.lines||[]).forEach(function(l){
      if(lineState(l) !== 'pending') return;
      const bs = (!l.bins || l.bins === '无在架货位') ? ['（无货位）'] : l.bins.split('、');
      bs.forEach(function(b){ const k2 = b + '|' + l.code; const a = sum[k2] || [0,0]; a[0] += (l.qty||0); a[1] += 1; sum[k2] = a; });
    });
  });
  const slines = ['批次 ' + PICK.batch + '：待拣 ' + (pr.pending||0) + ' 个商品 / ' + (pr.qty||0) + ' 件'];
  let cur = null;
  Object.keys(sum).sort().forEach(function(k2){
    const parts = k2.split('|');
    if(parts[0] !== cur){ slines.push(''); slines.push(parts[0] + '：'); cur = parts[0]; }
    slines.push('    ' + parts[1] + ' ×' + sum[k2][0] + '（' + sum[k2][1] + ' 个）');
  });
  $('psum').textContent = slines.join('\n');
}
async function mark(oi, li, state){
  if(!PICK) return;
  try {
    const d = await (await fetch(url('/api/pick/mark', {batch:PICK.batch, g:oi, line:li, state:state}))).json();
    if(d.error){ alert(d.error); return; }
    PICK = d; render();
    if(state === 'done'){ beep(true); } else if(state === 'short'){ beep(false); }
    speakCurrent();
  } catch(e){ alert('网络错误：' + e.message); }
}
$('btnGo').onclick = function(){ const b = ($('pbatch').value||'').trim(); if(!b){ alert('请输入打印批次号'); return; } go(b, 3, false); };
$('pbatch').addEventListener('keydown', function(e){ if(e.key === 'Enter'){ e.preventDefault(); $('btnGo').onclick(); } });
$('btnRefresh').onclick = function(){ if(PICK && confirm('重新从接口拉取批次 ' + PICK.batch + '？（会重置已拣状态）')) go(PICK.batch, PICK.days || 3, true); };
async function endBatch(){
  if(!PICK) return;
  if(!confirm('结束批次 ' + PICK.batch + ' 的拣货？结束后再打开页面不会自动续上。')) return;
  try { await fetch(url('/api/pick/end', {batch:PICK.batch})); PICK.status = 'ended'; render(); alert('已结束批次。'); }
  catch(e){ alert('网络错误：' + e.message); }
}
$('btnEnd').onclick = endBatch;
$('btnEnd2').onclick = endBatch;
$('btnHome').onclick = function(){ location.href = '/?' + new URLSearchParams({k:K}).toString(); };
$('btnSum').onclick = function(){ SUM_ON = !SUM_ON; $('psumbox').classList.toggle('hidden', !SUM_ON); };
$('filters').querySelectorAll('button').forEach(function(b){
  if(b.id === 'btnZone') return;
  b.onclick = function(){
    const f = b.dataset.f;
    if(f === 'one'){ MODE = 'one'; }
    else { MODE = 'list'; FILTER = f; }
    $('filters').querySelectorAll('button').forEach(function(x){
      if(x.id === 'btnZone') return;
      x.className = (x === b) ? '' : 'ghost';
    });
    render();
  };
});
function zoneBtn(){
  const b = $('btnZone');
  b.textContent = ZONE ? '按分区拣货' : '按打印顺序';
  b.className = ZONE ? '' : 'ghost';
}
$('btnZone').onclick = function(){
  ZONE = !ZONE;
  localStorage.setItem('pick_zone', ZONE ? '1' : '0');
  zoneBtn();
  render();
  speakCurrent();
};
/* 会话：登录后从 URL 取一次 token，之后自动附加到所有请求；失效则回登录页 */
(function(){
  try { var q = new URLSearchParams(location.search).get('sid'); if(q) localStorage.setItem('km_sid', q); } catch(e){}
  var _f = window.fetch;
  window.fetch = function(u, o){
    try { var t = localStorage.getItem('km_sid');
      if(t && typeof u === 'string' && u.indexOf('sid=') < 0){ u += (u.indexOf('?') >= 0 ? '&' : '?') + 'sid=' + encodeURIComponent(t); }
    } catch(e){}
    return _f(u, o).then(function(r){ if(r.status === 401){ location.href = '/login'; } return r; });
  };
})();

loadCurrent();
speakBtn();
zoneBtn();
</script></body></html>
"""
