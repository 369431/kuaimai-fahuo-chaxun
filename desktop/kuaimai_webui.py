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
  /* 首页四个功能按钮挤在一行：摄像头扫码 / 拣货 / 订单查询 / 声音 */
  .toolbar.nav4 { flex-wrap:nowrap; gap:6px; }
  .toolbar.nav4 button { flex:1 1 0; min-width:0; padding:9px 2px; font-size:12px;
                         white-space:nowrap; letter-spacing:-.03em; }
  video { width:100%; border-radius:10px; background:#000; }
  .hidden { display:none; }
  .pitem { border:1px solid #e3e6ea; border-radius:10px; padding:10px; margin-bottom:8px; background:#fff; }
  .pitem.done { background:#eefaf1; border-color:#bfe8cd; }
  .pitem.short { background:#fdecec; border-color:#f3c3c3; }
  .pseq { font-size:13px; color:#666; }
  .pexp { font-weight:800; font-size:16.5px; color:#111; letter-spacing:.02em; }
  .pcode { font-size:21px; font-weight:800; color:#000; margin:2px 0; }
  .pbin { font-size:16px; }
  .pbtns { display:flex; gap:8px; margin-top:8px; }
  .pbtns button { flex:1; padding:9px 8px; font-size:14px; }
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
    <div class="toolbar nav4">
      <button id="btnCam" class="ghost">摄像头扫码</button>
      <button id="btnOrder" class="ghost">订单查询</button>
      <button id="btnStock" class="ghost">现货可发</button>
      <button id="btnTake" class="ghost">库存盘点</button>
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
  <!-- 扫码记录已移除：手机/网页扫码会直接写进电脑版「扫码记录」（带扫码账号） -->
</div>
<script>
const $ = (id) => document.getElementById(id);
const K = new URLSearchParams(location.search).get('k') || localStorage.getItem('km_key') || '';
if (K) localStorage.setItem('km_key', K);
const KQ = '&k=' + encodeURIComponent(K);
let SOUND = true, hist = [], CUR = '';
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
  const _h=$('hist'); if(!_h) return;
  const tb=_h.querySelector('tbody'); tb.innerHTML='';
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
  CUR = code;
  const rel=$('rel').value, n=Number($('num').value||0);
  $('rcode').textContent=code; $('rmain').textContent='查询中…';
  let d;
  try { d=await (await fetch(`/api/lookup?code=${encodeURIComponent(code)}&rel=${rel}&n=${n}${KQ}`)).json(); }
  catch(e){ $('rmain').textContent='网络错误：'+e.message; return; }
  if(d.error){ $('rmain').textContent=d.error; return; }
  if(d.series){
    $('result').className='';
    CUR = d.code;
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
  CUR = d.code;
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
$('btnApply').onclick=()=>{
  // 只做筛选：保存条件 + 刷新数据时间；当前显示了哪个编码就按新条件重查它，
  // 不去历史里挑最后一条（那条可能是别的东西，看着像“乱查一个数字”）
  try { localStorage.setItem('km_rel', $('rel').value); localStorage.setItem('km_num', $('num').value||'1'); } catch(e){}
  loadStatus();
  if(CUR){ query(CUR); }
  else { $('rmain').textContent='筛选条件已保存，下次扫码按此条件统计'; }
};
$('btnSound').onclick=()=>{ SOUND=!SOUND; $('btnSound').textContent='声音：'+(SOUND?'开':'关'); };
const _btnClear=$('btnClear'), _btnCsv=$('btnCsv');   // 扫码记录卡已移除，保留兼容判断
if(_btnClear) _btnClear.onclick=()=>{ if(confirm('清空本机扫码记录？')){ hist=[]; saveHist(); renderHistory(); } };
if(_btnCsv) _btnCsv.onclick=()=>{
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
$('btnTake').onclick = () => { location.href = '/stocktake'; };   // 库存盘点：独立页面
const _btnPick = $('btnPick');             // 拣货按钮已移除；处理器保留但不再绑定
if(_btnPick) _btnPick.onclick = () => {
  const sid = (function(){ try { return localStorage.getItem('km_sid') || ''; } catch(e){ return ''; } })();
  const q = {k:K}; if(sid) q.sid = sid;
  location.href = '/pick?' + new URLSearchParams(q).toString();
};
/* ---------------- 订单查询：独立页面 /order（订单号/快递单号都能查） ---------------- */
$('btnOrder').onclick = () => {
  const sid = (function(){ try { return localStorage.getItem('km_sid') || ''; } catch(e){ return ''; } })();
  location.href = '/order' + (sid ? ('?sid=' + encodeURIComponent(sid)) : '');
};
/* ---------------- 现货可发：独立页面 /stock ---------------- */
$('btnStock').onclick = () => {
  const sid = (function(){ try { return localStorage.getItem('km_sid') || ''; } catch(e){ return ''; } })();
  location.href = '/stock' + (sid ? ('?sid=' + encodeURIComponent(sid)) : '');
};
/* （拣货已下线，不再自动查未结束批次） */

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

renderHistory();
try {
  var _r0 = localStorage.getItem('km_rel'); if(_r0) $('rel').value = _r0;
  var _n0 = localStorage.getItem('km_num'); if(_n0) $('num').value = _n0;
} catch(e){}
loadStatus(); setInterval(loadStatus,60000);
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
  .pitem.urgent { border:2px solid #FF3B30; background:#fff5f5; }
  .pitem.urgent::before { content:"加急"; display:inline-block; background:#FF3B30; color:#fff;
                          font-weight:800; font-size:13px; border-radius:8px; padding:2px 10px; margin-bottom:6px; }
  .pitem.urgent .pexp, .pitem.urgent .pseq { color:#FF3B30; }
  .pseq { font-size:13px; color:#666; }
  .pexp { font-weight:800; font-size:16.5px; color:#111; letter-spacing:.02em; }
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
  .pitem.one .pbtns button { padding:12px 8px; font-size:16px; }
  .pbtns { display:flex; gap:8px; margin-top:9px; }
  .pbtns button { flex:1; padding:11px 8px; font-size:15px; }
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
  .pitem.one .pbtns button { padding:13px 8px; font-size:16px; border-radius:12px; }
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
    div.className = 'pitem' + (MODE === 'one' ? ' one' : '') + (o.urgent ? ' urgent' : '')
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
          + '<span class="pbin2">' + (nb ? '<b style="color:#FF9500">无货位</b>'
              : ('货位 ' + l.bins + '　在架 ' + (l.shelf == null ? '-' : l.shelf))) + '</span>'
          + '<span class="pst">' + (lst==='done'?'✓ 已拣':(lst==='short'?(nb?'无货位':'无货'):'待拣')) + '</span>'
          + '</div>';
      });
    } else {
      linesHtml = '<div class="pmeta2">共 ' + ls.length + ' 个商品 · ' + ls.reduce(function(a, l){ return a + (l.qty||0); }, 0) + ' 件 · 已拣 ' + (ls.length - pending) + ' 个'
        + (nl ? ('　下一个：' + nl.l.code + ' ×' + nl.l.qty + ' → '
                + ((!nl.l.bins || nl.l.bins === '无在架货位') ? '无货位' : (nl.l.bins + '（在架 ' + (nl.l.shelf == null ? '-' : nl.l.shelf) + '）'))) : '')
        + '</div>';
    }
    const pieces = ls.reduce(function(a, l){ return a + (l.qty || 0); }, 0);
    div.innerHTML = '<div class="pseq">' + rng + (o.express ? (' · <b class="pexp">快递单号 ' + o.express + '</b>') : '') + '</div>'
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


# ====================== 网页端：订单查询（图文 + 退款状态） ======================
ORDER_HTML = r"""<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>订单查询 · 快麦</title>
<style>
  * { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
  :root { --blue:#007AFF; --green:#34C759; --red:#FF3B30; --ink:#1d1d1f; --sub:#6e6e73;
          --line:rgba(60,60,67,.12); --fill:rgba(120,120,128,.12); --glass:rgba(255,255,255,.80); }
  body { margin:0; padding:12px; min-height:100vh; color:var(--ink);
         font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
         letter-spacing:-.01em; -webkit-font-smoothing:antialiased;
         background:linear-gradient(170deg,#eef3fa 0%,#e6edf8 45%,#e1e8f4 100%) fixed; }
  .card { background:var(--glass); backdrop-filter:saturate(180%) blur(20px);
          -webkit-backdrop-filter:saturate(180%) blur(20px); border:1px solid rgba(255,255,255,.62);
          border-radius:14px; padding:12px; margin-bottom:10px; box-shadow:0 8px 24px rgba(24,39,75,.10); }
  .bar { display:flex; gap:8px; }
  .bar input { flex:1; min-width:0; padding:13px 14px; font-size:19px; color:var(--ink);
               background:rgba(255,255,255,.92); border:1px solid var(--line); border-radius:12px; }
  .bar input:focus { outline:none; border-color:var(--blue); box-shadow:0 0 0 3.5px rgba(0,122,255,.16); }
  .bar button { padding:13px 18px; font-size:16px; font-weight:600; border:0; border-radius:12px;
                background:var(--blue); color:#fff; }
  .bar button:active { transform:scale(.98); }
  h2 { font-size:15px; margin:0 0 8px; font-weight:700; color:var(--ink);
       border-left:3px solid var(--blue); padding-left:8px; }
  .kv { font-size:14px; line-height:2; }
  .kv div { display:flex; gap:6px; }
  .kv b { color:var(--sub); font-weight:400; flex:0 0 72px; }
  .kv span { flex:1; word-break:break-all; }
  .item { display:flex; gap:10px; padding:10px 0; border-top:1px solid rgba(60,60,67,.10); }
  .item:first-of-type { border-top:0; }
  .item img { width:92px; height:92px; object-fit:cover; border-radius:10px; background:#ececf0; flex:0 0 auto; }
  .t { font-size:14.5px; font-weight:600; line-height:1.4; }
  .s { font-size:12.5px; color:var(--sub); line-height:1.75; margin-top:2px; word-break:break-all; }
  .amt { font-size:14px; font-weight:700; color:#c62828; margin-top:4px; }
  .total { font-size:13px; color:var(--sub); border-top:1px solid rgba(60,60,67,.10); padding-top:8px; margin-top:2px; }
  .tag { display:inline-block; font-size:12px; padding:2px 9px; border-radius:8px; background:var(--fill);
         color:var(--sub); margin:0 6px 4px 0; }
  .tag.warn { background:rgba(255,59,48,.15); color:#c62828; }
  .tag.ok { background:rgba(52,199,89,.18); color:#1B7F35; }
  .tag.big { font-size:13.5px; font-weight:700; padding:3px 12px; }
  .tag.red { background:#FF3B30; color:#fff; font-weight:800; font-size:14px; padding:3px 12px; }
  .muted { font-size:12.5px; color:var(--sub); line-height:1.7; }
  .sub2 { border-top:1px solid rgba(60,60,67,.10); padding-top:8px; margin-top:8px; }
  .stline { font-size:13.5px; line-height:1.9; }
  @media (prefers-color-scheme: dark) {
    body { background:linear-gradient(170deg,#1c1c1e,#151517 60%,#1a1a1c) fixed; color:#f2f2f7; }
    .card { background:rgba(28,28,30,.74); border-color:rgba(255,255,255,.08); }
    .kv b, .s, .muted, .total { color:#a1a1a6; }
    h2 { color:#f2f2f7; }
    .bar input { background:rgba(118,118,128,.24); border-color:rgba(255,255,255,.12); color:#f2f2f7; }
  }
</style></head>
<body>
<div class="card">
  <div class="bar">
    <input id="no" type="text" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="扫/手动输入订单号或快递单号">
    <button id="go">查询</button>
  </div>
  <div class="muted" id="hint" style="margin-top:8px">快递单号、19 位平台单号、16 位系统单号都能查；扫码枪直接扫，回车即查。</div>
</div>
<div id="out"></div>
<script>
const $ = id => document.getElementById(id);
const esc = s => String(s==null?'':s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const SID = (function(){
  try {
    const q = new URLSearchParams(location.search).get('sid');
    if(q) localStorage.setItem('km_sid', q);
    return localStorage.getItem('km_sid') || '';
  } catch(e){ return ''; }
})();
function withSid(u){ return SID ? (u + (u.indexOf('?') >= 0 ? '&' : '?') + 'sid=' + encodeURIComponent(SID)) : u; }
function imgUrl(u){ return withSid('/api/order/img?u=' + encodeURIComponent(u)); }
function kvHtml(kv){
  return (kv||[]).map(function(x){
    const v = (x[1] === null || x[1] === undefined || x[1] === '') ? '—' : x[1];
    return '<div><b>' + esc(x[0]) + '</b><span>' + esc(v) + '</span></div>';
  }).join('');
}
function load(no){
  no = (no || '').trim();
  if(!no){ $('hint').textContent = '请先输入订单号或快递单号'; return; }
  $('out').innerHTML = '<div class="card"><div class="muted">正在查询 ' + esc(no) + ' …</div></div>';
  fetch(withSid('/api/order?no=' + encodeURIComponent(no)), {cache:'no-store'})
    .then(function(r){ if(r.status === 401){ location.href = '/login'; throw new Error('请重新登录'); } return r.json(); })
    .then(function(d){
      if(d.error){ $('out').innerHTML = '<div class="card"><div class="muted">' + esc(d.error) + '</div></div>'; return; }
      render(d);
    })
    .catch(function(e){
      $('out').innerHTML = '<div class="card"><div class="muted">查询失败：' + esc(e.message) + '（可再点一次查询）</div></div>';
    });
}
function render(d){
  var h = '';
  if(d.order){
    h += '<div class="card"><div class="stline"><span class="tag">系统状态：' + esc(d.statusText || '—') + '</span>'
      + '<span class="tag">平台状态：' + esc(d.uniText || '—') + '</span>'
      + (d.urgent ? '<span class="tag red">加急</span>' : '')
      + ((d.excs && d.excs.length) ? ('<span class="tag warn">异常：' + esc(d.excs.join('、')) + '</span>') : '')
      + ((d.tags && d.tags.length) ? ('<span class="tag">标签：' + esc(d.tags.join('、')) + '</span>') : '')
      + '</div></div>';
    h += '<div class="card"><h2>订单信息</h2><div class="kv">' + kvHtml(d.head) + '</div></div>';
    h += '<div class="card"><h2>商品信息</h2>';
    (d.items || []).forEach(function(it){
      h += '<div class="item">' + (it.pic ? '<img src="' + imgUrl(it.pic) + '" loading="lazy">' : '<img>')
        + '<div><div class="t">' + esc(it.title) + '</div>'
        + '<div class="s">规格别名：' + esc(it.spec || '—') + '</div>'
        + '<div class="s">编码：' + esc(it.code) + '</div>'
        + (it.platSpec ? '<div class="s">平台规格：' + esc(it.platSpec) + '</div>' : '')
        + (it.remark ? '<div class="s">备注：' + esc(it.remark) + '</div>' : '')
        + '<div class="s">货位：' + esc(it.bin) + '</div>'
        + '<div class="amt">成交金额 ¥' + esc(it.amount == null ? '' : it.amount)
        + '<span style="font-weight:400;color:#6e6e73">　× ' + esc(it.qty) + ' 件</span></div>'
        + ((it.tags && it.tags.length) ? '<div class="s">' + it.tags.map(function(t){ return '<span class="tag warn">' + esc(t) + '</span>'; }).join('') + '</div>' : '')
        + '</div></div>';
    });
    h += '<div class="total">商品总数量：' + esc(d.itemNum) + '（' + esc(d.itemKind) + ' 种）　订单行：' + esc((d.items||[]).length) + '</div>';
    h += '</div>';
  } else {
    h += '<div class="card"><div class="muted">订单接口查不到这张单（多为归档老单），下面显示售后信息。</div></div>';
  }
  h += '<div class="card"><h2>退款 / 售后</h2>';
  if(!(d.after && d.after.length)){
    h += '<div><span class="tag ok big">未申请退款</span><span class="muted">订单行退款状态：'
      + esc((d.lineRefund || []).join('；') || '未退款') + '；无售后工单</span></div>';
  } else {
    d.after.forEach(function(w){
      h += '<div class="sub2"><div>'
        + '<span class="tag ' + (w.status === 9 ? 'ok' : 'warn') + ' big">' + esc(w.statusText) + '</span>'
        + '<span class="tag warn">' + esc(w.typeText) + '</span>'
        + '<span class="tag">工单 ' + esc(w.id) + '</span>'
        + (w.shopName ? '<span class="tag">' + esc(w.shopName) + '</span>' : '')
        + '</div><div class="kv">' + kvHtml(w.kv) + '</div>';
      (w.items || []).forEach(function(it){
        h += '<div class="item">' + (it.pic ? '<img src="' + imgUrl(it.pic) + '" loading="lazy">' : '<img>')
          + '<div><div class="t">' + esc(it.title) + '</div><div class="s">' + esc(it.spec) + '</div>'
          + '<div class="s">编码 ' + esc(it.code) + '　申请 ' + esc(it.count) + ' 件　实退 ' + esc(it.realQty) + ' 件　单价 ' + esc(it.price) + '</div></div></div>';
      });
      h += '</div>';
    });
  }
  h += '</div>';
  $('out').innerHTML = h;
}
$('go').onclick = function(){ load($('no').value); };
$('no').addEventListener('keydown', function(e){ if(e.key === 'Enter'){ e.preventDefault(); load($('no').value); } });
(function(){
  const q = new URLSearchParams(location.search).get('no');
  if(q){ $('no').value = q; load(q); }
  $('no').focus();
})();
</script>
</body></html>
"""


# ====================== 网页端：现货可发（在架 / 待发货 / 可发数量） ======================
STOCKTAKE_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>库存盘点 · 快麦扫码</title>
<style>
  :root { --bg:#f2f2f7; --card:#ffffff; --sub:#6b7280; --line:rgba(60,60,67,.10); }
  * { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
  body { margin:0; padding:10px 10px 40px; background:var(--bg); color:#111;
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif; }
  header { display:flex; align-items:baseline; gap:8px; padding:2px 3px 8px; }
  header b { font-size:17px; }
  .top { position:sticky; top:0; z-index:9; background:rgba(255,255,255,.94);
         backdrop-filter:saturate(180%) blur(14px); border-radius:14px; padding:10px;
         display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
  input[type=text] { flex:1 1 130px; min-width:110px; padding:11px 12px; font-size:17px;
         border:1px solid #d7dbe0; border-radius:10px; }
  button { padding:11px 14px; font-size:15px; font-weight:700; border:0; border-radius:10px;
           background:#0b5394; color:#fff; }
  button.g { background:#e8eef5; color:#0b5394; }
  .sum { font-size:13px; color:var(--sub); margin:9px 3px; }
  .flash { font-size:13px; color:#1B7F35; font-weight:700; margin:0 3px 6px; min-height:18px; }
  .card { background:var(--card); border-radius:14px; padding:4px 12px; margin-top:8px; }
  .row { display:flex; gap:8px; padding:10px 0; border-top:1px solid var(--line); align-items:center; }
  .row:first-child { border-top:0; }
  .main { flex:1; min-width:0; }
  .l1 { display:flex; align-items:center; gap:6px; }
  .code { font-size:16px; font-weight:700; flex:1; min-width:0; word-break:break-all; }
  .num { font-size:17px; font-weight:800; color:#1B7F35; white-space:nowrap; }
  .num.z { color:#c62828; }
  .sub { font-size:12.5px; color:var(--sub); margin-top:2px; }
  .sub b { color:#0b5394; }
  .btns { display:flex; flex-direction:column; gap:6px; flex:0 0 auto; }
  .sbtn { padding:9px 13px; font-size:13.5px; border-radius:9px; background:#e8eef5;
          color:#0b5394; font-weight:700; white-space:nowrap; }
  .sbtn.zero { background:#fde8e8; color:#b00020; }
  .muted { color:var(--sub); font-size:14px; }
</style>
</head>
<body>
<header><b>库存盘点</b><span class="muted">按款号看所有颜色尺码的在架数</span></header>
<div class="top">
  <input id="kw" type="text" inputmode="search" autocomplete="off" placeholder="款号，如 7107">
  <button id="go">查询</button>
  <button class="g" id="home">返回</button>
</div>
<div class="sum" id="sum">输入款号后回车：列出该款所有颜色尺码的货位与在架数，可直接改库存 / 盘0</div>
<div class="flash" id="flash"></div>
<div id="list"></div>
<script>
const $ = id => document.getElementById(id);
const esc = s => String(s==null?'':s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const SID = (function(){
  try { const q = new URLSearchParams(location.search).get('sid'); if(q) localStorage.setItem('km_sid', q);
        return localStorage.getItem('km_sid') || ''; } catch(e){ return ''; }
})();
const K = new URLSearchParams(location.search).get('k') || localStorage.getItem('km_key') || '';
if (K) localStorage.setItem('km_key', K);
const KQ = K ? ('&k=' + encodeURIComponent(K)) : '';
function withSid(u){ return SID ? (u + (u.indexOf('?') >= 0 ? '&' : '?') + 'sid=' + encodeURIComponent(SID) + KQ) : u; }
function flash(m){ const el=$('flash'); el.textContent=m||'';
  if(m) setTimeout(()=>{ if(el.textContent===m) el.textContent=''; },5000); }
/* 尺码排序：S < M < L < XL < 2XL < 3XL …；认不出尺码的排最后 */
function sizeRank(code){
  const t = String(code||'').toUpperCase().replace(/[\s\-]/g,'');
  const m = t.match(/(XXXL|XXL|XS|XL|[2-9]XL|S|M|L|[0-9]{2,3})$/);
  if(!m) return 900;
  const tok = m[1];
  const map = {XS:5, S:10, M:20, L:30, XL:40, XXL:50, XXXL:60};
  if(map[tok] != null) return map[tok];
  const d = tok.match(/^([2-9])XL$/);
  if(d) return 30 + parseInt(d[1],10) * 10;          // 2XL=50, 3XL=60 …
  if(/^[0-9]{2,3}$/.test(tok)) return 200 + parseInt(tok,10);   // 数字尺码
  return 900;
}
let ROWS = [];
function load(){
  const kw = $('kw').value.trim();
  if(!kw){ $('sum').textContent = '先输入款号（如 7107）'; return; }
  $('sum').textContent = '正在查 ' + kw + ' …';
  fetch(withSid('/api/stock?only=all&sort=code&kw=' + encodeURIComponent(kw)), {cache:'no-store'})
    .then(r => r.json())
    .then(d => {
      const all = d.rows || [];
      const K0 = kw.toUpperCase();
      // 去掉裸款号本身（如 7107）那一行；其余按尺码 S/M/L/XL/2XL… 排序，同尺码再按编码
      ROWS = all.filter(r => !(String(r.c).toUpperCase() === K0 && String(r.c).indexOf('-') < 0))
                .sort((a, b) => (sizeRank(a.c) - sizeRank(b.c))
                                || String(a.c).localeCompare(String(b.c)));
      $('sum').textContent = '款号 ' + kw + '：' + ROWS.length + ' 个规格 / '
        + ROWS.reduce((n,r)=>n+((r.bl||[]).length||1),0) + ' 个货位行（已按尺码排序）';
      render();
    })
    .catch(e => { $('sum').textContent = '查询失败：' + e.message; });
}
function render(){
  const box = $('list');
  if(!ROWS.length){ box.innerHTML = '<div class="card"><div class="muted" style="padding:12px 0">'
    + '这个款号没查到编码（试试只输数字前缀，如 7107）</div></div>'; return; }
  const lines = [];
  ROWS.forEach(function(r){
    const bins = (r.bl && r.bl.length) ? r.bl : [['无在架货位', 0]];
    bins.forEach(function(b, i){
      const sh = Number(b[1] || 0);
      lines.push('<div class="row"><div class="main">'
        + '<div class="l1"><span class="code">' + (i === 0 ? esc(r.c) : '') + '</span>'
        + '<span class="num' + (sh ? '' : ' z') + '">' + sh + '</span></div>'
        + '<div class="sub">货位 <b>' + esc(b[0]) + '</b> · 在架 ' + sh + ' 件'
        + (r.p ? (' · 待发 ' + r.p + ' 件') : '') + '</div></div>'
        + '<div class="btns">'
        + '<button class="sbtn adj" data-c="' + esc(r.c) + '" data-b="' + esc(b[0]) + '" data-n="' + sh + '">改库存</button>'
        + '<button class="sbtn zero" data-c="' + esc(r.c) + '" data-b="' + esc(b[0]) + '" data-n="' + sh + '">盘0</button>'
        + '</div></div>');
    });
  });
  box.innerHTML = '<div class="card">' + lines.join('') + '</div>';
  bind();
}
function post(code, bin, qty){
  return fetch(withSid('/api/stock/adjust'), {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({code: code, bin: bin, qty: qty, confirm: 1})})
    .then(r => r.json());
}
function bind(){
  document.querySelectorAll('.sbtn.adj').forEach(function(b){
    b.onclick = function(){
      const code = b.dataset.c, bin = b.dataset.b, cur = b.dataset.n;
      const v = prompt(code + ' @ ' + bin + '\n改成多少件？（当前 ' + cur + ' 件）', cur);
      if(v === null) return;
      const q = parseInt(v, 10);
      if(isNaN(q) || q < 0){ alert('数量要填 0 或正整数'); return; }
      if(!confirm('确认改库存？\n\n' + code + '\n货位 ' + bin + '：' + cur + ' → ' + q + ' 件\n\n【真实修改快麦库存，不可撤销】')) return;
      flash('正在改库存…');
      post(code, bin, q).then(function(j){
        alert((j.ok ? '✓ 已改：' : '✗ 失败：') + (j.msg || ''));
        flash(j.ok ? ('已改：' + code + ' @ ' + bin + ' → ' + q) : ('失败：' + (j.msg || '')));
        if(j.ok) load();
      }).catch(e => alert('网络错误：' + e.message));
    };
  });
  document.querySelectorAll('.sbtn.zero').forEach(function(b){
    b.onclick = function(){
      const code = b.dataset.c, bin = b.dataset.b, cur = Number(b.dataset.n || 0);
      if(cur === 0){ alert('这个货位本来就是在架 0，不用盘'); return; }
      if(!confirm('确认盘0？\n\n' + code + '\n货位 ' + bin + '：' + cur + ' → 0 件\n\n【真实修改快麦库存，不可撤销】')) return;
      if(!confirm('再确认一次：真的要把 ' + code + ' @ ' + bin + ' 盘成 0 吗？')) return;
      flash('正在盘0…');
      post(code, bin, 0).then(function(j){
        alert((j.ok ? '✓ 已盘0：' : '✗ 失败：') + (j.msg || ''));
        flash(j.ok ? ('已盘0：' + code + ' @ ' + bin) : ('失败：' + (j.msg || '')));
        if(j.ok) load();
      }).catch(e => alert('网络错误：' + e.message));
    };
  });
}
$('go').onclick = load;
$('kw').addEventListener('keydown', function(e){ if(e.key === 'Enter'){ e.preventDefault(); load(); } });
$('home').onclick = function(){ location.href = '/'; };
if(!SID){ location.href = '/login'; } else { $('kw').focus(); }
</script>
</body></html>
"""


STOCK_HTML = r"""<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>现货可发 · 快麦</title>
<style>
  * { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
  :root { --blue:#007AFF; --green:#34C759; --red:#FF3B30; --ink:#1d1d1f; --sub:#6e6e73;
          --line:rgba(60,60,67,.12); --fill:rgba(120,120,128,.12); --glass:rgba(255,255,255,.80); }
  body { margin:0; padding:12px; min-height:100vh; color:var(--ink);
         font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
         letter-spacing:-.01em; -webkit-font-smoothing:antialiased;
         background:linear-gradient(170deg,#eef3fa 0%,#e6edf8 45%,#e1e8f4 100%) fixed; }
  .card { background:var(--glass); backdrop-filter:saturate(180%) blur(20px);
          -webkit-backdrop-filter:saturate(180%) blur(20px); border:1px solid rgba(255,255,255,.62);
          border-radius:14px; padding:12px; margin-bottom:10px; box-shadow:0 8px 24px rgba(24,39,75,.10); }
  .bar { display:flex; gap:8px; }
  .bar input { flex:1; min-width:0; padding:13px 14px; font-size:18px; color:var(--ink);
               background:rgba(255,255,255,.92); border:1px solid var(--line); border-radius:12px; }
  .bar input:focus { outline:none; border-color:var(--blue); box-shadow:0 0 0 3.5px rgba(0,122,255,.16); }
  .bar button { padding:13px 16px; font-size:16px; font-weight:600; border:0; border-radius:12px;
                background:var(--blue); color:#fff; }
  .ctl { display:flex; gap:6px; margin-top:8px; align-items:center; flex-wrap:wrap; }
  .ctl select { flex:1 1 40%; min-width:0; font-size:13.5px; padding:8px; border:1px solid var(--line);
                border-radius:10px; background:rgba(255,255,255,.92); color:var(--ink); }
  .ctl button { flex:1 1 100%; padding:11px; font-size:14.5px; font-weight:600; border:0; border-radius:10px;
                background:var(--green,#34C759); color:#fff; }
  .muted { font-size:12.5px; color:var(--sub); line-height:1.7; margin-top:8px; }
  .row { display:flex; align-items:center; gap:8px; padding:9px 0; border-top:1px solid rgba(60,60,67,.10); }
  .main { flex:1; min-width:0; }
  .l1 { display:flex; align-items:center; gap:6px; }
  .l1 .code { flex:1; min-width:0; }
  .tag { background:#FF3B30; color:#fff; border-radius:6px; padding:2px 7px; font-size:12px;
         font-weight:800; white-space:nowrap; flex:0 0 auto; }
  .btns { display:flex; flex-direction:column; gap:6px; flex:0 0 auto; }
  .row:first-child { border-top:0; }
  .code { font-size:16px; font-weight:700; word-break:break-all; }
  .num { font-size:12.5px; color:var(--sub); white-space:nowrap; }
  .num b { font-size:15px; color:var(--ink); }
  .free { font-size:17px; font-weight:800; min-width:50px; text-align:right; white-space:nowrap;
          flex:0 0 auto; }
  .free.pos { color:#1B7F35; }
  .free.neg { color:#c62828; }
  .sub { display:block; font-size:12.5px; color:var(--sub); margin-top:2px; line-height:1.55; }
  .legend { font-size:12px; color:var(--sub); line-height:1.7; }
  .rec { margin-top:8px; padding:9px 12px; border-radius:12px; background:rgba(52,199,89,.14);
         color:#1B7F35; font-size:14.5px; font-weight:700; line-height:1.5; }
  .rec.bad { background:rgba(255,59,48,.13); color:#c62828; }
  .calc { font-size:12.5px; color:var(--sub); margin-top:3px; line-height:1.7; }
  .calc b { color:var(--ink); }
  .sbtn { margin:0; padding:9px 13px; font-size:13.5px; border:0; border-radius:9px;
          background:#e8eef5; color:#0b5394; font-weight:700; white-space:nowrap; }
  .sbtn.undo { background:#fdecec; color:#c62828; }
  .sbtn.adj { background:#fff4e5; color:#b26a00; }
  .sbtn.zero { background:#fde8e8; color:#b00020; }
  .chk { font-size:13px; display:flex; align-items:center; gap:5px; flex:1 1 100%; color:var(--sub); }
  .row.sent { opacity:.55; }
  .code.ug { color:#FF3B30; }
  .flash { font-size:13px; color:#1B7F35; font-weight:700; margin-top:6px; min-height:18px; }
  @media (prefers-color-scheme: dark) {
    body { background:linear-gradient(170deg,#1c1c1e,#151517 60%,#1a1a1c) fixed; color:#f2f2f7; }
    .card { background:rgba(28,28,30,.74); border-color:rgba(255,255,255,.08); }
    .muted, .num, .sub, .legend { color:#a1a1a6; }
    .num b { color:#f2f2f7; }
    .bar input, .ctl select { background:rgba(118,118,128,.24); border-color:rgba(255,255,255,.12); color:#f2f2f7; }
  }
</style></head>
<body>
<div class="card">
  <div class="bar">
    <input id="kw" type="text" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="编码或款号（如 7107 / 7107-黑色S）">
    <button id="go">查询</button>
  </div>
  <div class="ctl">
    <select id="sort">
      <option value="urg_free">加急有货优先（可发多 → 少）</option>
      <option value="free">可发数量（多 → 少）</option>
      <option value="urgent">加急件数（多 → 少）</option>
      <option value="shelf">在架数（多 → 少）</option>
      <option value="pieces">待发货件数（多 → 少）</option>
      <option value="code">编码 A → Z</option>
    </select>
    <select id="only">
      <option value="free">只看可发（可发 &gt; 0）</option>
      <option value="all">全部编码（含缺货）</option>
      <option value="short">只看缺货（可发 &lt; 0）</option>
      <option value="orders">只看有待发货</option>
      <option value="urgent">只看有加急</option>
      <option value="urg_free">只看加急且有货</option>
    </select>
    <button id="exp" title="导出 Excel：编码 / 货位 / 一单一件 / 一单多件 / 多件件数 / 加急 / 待发货 / 在架 / 可发 / 加急有货">导出</button>
    <label class="chk"><input type="checkbox" id="hidesent" checked> 隐藏已发（数据拉新后自动清空标记）</label>
  </div>
  <div class="muted" id="sum">正在载入…</div>
  <div class="flash" id="flash"></div>
  <div class="rec" id="rec"></div>
</div>
<div class="card" id="list" style="max-height:66vh; overflow:auto"></div>
<div class="card"><div class="legend">
  <b>可发数量 = 能发出去的件数</b>：订单要的和库存取小的，再扣掉留给一单多件单的部分。<br>
  例：一单一件 100 件 + 一单多件 20 件 = 订单共要 120 件，库存只有 80 件 → 最多发 80 件，
  其中 20 件留给多件单 → <b>可发 60 件</b>（就是「只有 60 件货」的意思）。<br>
  负数 = 连多件单的库存都不够（需补货）。已排除 1166、买家秀、圆虹包 等占位/补偿商品。<br>
  <b>加急</b> = 平台上标了加急的单（优先发这些）；想先处理加急，用「只看有加急」或按「加急件数」排序。<br>
  <b>默认排序</b>：带加急且有货可发的（红标「加急·有货」）排最前，同类里再按可发从多到少 —— 这样从上往下顺着发就是先发加急。
</div></div>
<script>
const $ = id => document.getElementById(id);
const esc = s => String(s==null?'':s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const SID = (function(){
  try {
    const q = new URLSearchParams(location.search).get('sid');
    if(q) localStorage.setItem('km_sid', q);
    return localStorage.getItem('km_sid') || '';
  } catch(e){ return ''; }
})();
function withSid(u){ return SID ? (u + (u.indexOf('?') >= 0 ? '&' : '?') + 'sid=' + encodeURIComponent(SID)) : u; }
let ROWS = [];
let HIDE_SENT = true;
function flash(msg){
  const el = $('flash');
  if(!el) return;
  el.textContent = msg || '';
  if(msg){ setTimeout(function(){ if(el.textContent === msg) el.textContent = ''; }, 5000); }
}
function params(){ return 'kw=' + encodeURIComponent($('kw').value.trim()) + '&only=' + $('only').value + '&sort=' + $('sort').value; }
function load(){
  $('sum').textContent = '正在载入…';
  fetch(withSid('/api/stock?' + params()), {cache:'no-store'})
    .then(function(r){ if(r.status === 401){ location.href = '/login'; throw new Error('请重新登录'); } return r.json(); })
    .then(function(d){
      if(d.error){ $('sum').textContent = d.error; return; }
      ROWS = d.rows || [];
      const t = d.totals || {};
      $('sum').innerHTML = '共 <b>' + (d.total||0) + '</b> 个　可发合计 <b>' + (t.free||0) + '</b> 件'
        + ((t.up || t.uo) ? ('　<b style="color:#c62828">加急 ' + (t.up||0) + ' 件</b>') : '')
        + ((t.prio) ? ('　<b style="color:#FF3B30">加急有货 ' + t.prio + '</b>') : '')
        + ((t.sent) ? ('　<b style="color:#1B7F35">已发 ' + t.sent + '</b>') : '');
      const rec = $('rec');
      if(rec){
        if((t.free||0) >= 0){
          rec.className = 'rec';
          rec.style.display = '';
          rec.innerHTML = '推荐可发合计：' + (t.free||0) + ' 件';
        } else {
          rec.className = 'rec';
          rec.style.display = 'none';
          rec.innerHTML = '';
        }
      }
      render();
    })
    .catch(function(e){ $('sum').textContent = '载入失败：' + e.message; });
}
function render(){
  const box = $('list');
  const vis = ROWS.filter(function(r){ return !(HIDE_SENT && r.sent); });
  if(!vis.length){ box.innerHTML = '<div class="muted">没有匹配的编码</div>'; return; }
  const head = vis.slice(0, 800);
  box.innerHTML = head.map(function(r){
    const cls = r.f >= 0 ? 'pos' : 'neg';
    return '<div class="row' + (r.sent ? ' sent' : '') + '">'
      + '<div class="main"><div class="l1"><span class="code'
      + ((r.p1 || r.up || r.uo) ? ' ug' : '') + '">' + esc(r.c) + '</span>'
      + ((r.p1) ? '<span class="tag">加急·有货</span>' : '')
      + '<span class="free ' + cls + '" title="可发 = min(在架, 待发) − 多件">' + r.f + '</span></div>'
      + '<div class="sub">货位 <b style="color:#0b5394">' + esc(r.b || '无在架货位') + '</b>'
      + ' · 在架 ' + r.s + ' · 一件 ' + r.n + ' · 多件 ' + r.m + '(' + (r.mp == null ? 0 : r.mp) + ')'
      + ((r.up || r.uo) ? (' · <span style="color:#c62828;font-weight:800">加急 ' + (r.uo || 0) + '/' + (r.up || 0) + '</span>') : '')
      + (r.l ? (' · 锁定 ' + r.l) : '') + '</div></div>'
      + '<div class="btns">'
      + '<button class="sbtn' + (r.sent ? ' undo' : '') + '" data-c="' + esc(r.c) + '">'
      + (r.sent ? '撤回' : '可发') + '</button>'
      + '<button class="sbtn adj" data-c="' + esc(r.c) + '">改库存</button>'
      + '<button class="sbtn zero" data-c="' + esc(r.c) + '">盘0</button></div></div>';
  }).join('') + (vis.length > head.length
      ? ('<div class="muted">只显示前 ' + head.length + ' 条，其余 ' + (vis.length - head.length) + ' 条请用「导出 Excel」或加关键词。</div>') : '');
  box.querySelectorAll('.sbtn:not(.adj):not(.zero)').forEach(function(b){
    b.onclick = function(){
      const code = b.dataset.c, undo = b.classList.contains('undo');
      const row = ROWS.filter(function(r){ return r.c === code; })[0] || {};
      if(!undo){   // 点「可发」→ 输入可打单数量，写一条扫码日志到电脑端
        const v = prompt('可发 ' + code + '\n可打单数量填多少？', row.f == null ? '' : String(row.f));
        if(v !== null){
          const q = parseInt(v, 10);
          if(isNaN(q) || q < 0){ alert('数量要填 0 或正整数'); return; }
          fetch(withSid('/api/stock/canprint'), {method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({code: code, qty: q, bins: row.b || '',
                                  pending: row.p || 0, shelf: row.s || 0})})
            .then(function(r2){ return r2.json(); })
            .then(function(j){
              if(j && j.ok){ flash('已记可打单：' + code + ' ' + q + '（电脑端扫码记录已更新）'); }
              else { flash('记录失败：' + ((j && j.msg) || '未知')); alert('没能写入扫码记录：' + ((j && j.msg) || '未知')); }
            })
            .catch(function(){ flash('网络错误，扫码记录未写入'); });
        }
      }
      // 先本地生效（立刻隐藏/恢复），再同步到服务端
      ROWS.forEach(function(r){ if(r.c === code) r.sent = undo ? 0 : 1; });
      render();
      fetch(withSid('/api/stock/sent'), {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({codes:[code], undo: undo})})
        .then(function(r2){ return r2.json(); })
        .then(function(j){
          if(j && j.ok === false){
            ROWS.forEach(function(r){ if(r.c === code) r.sent = undo ? 1 : 0; });
            render();
          }
          flash((undo ? '已撤回：' : '已标记已发：') + code + '（本地先隐藏，拉到新数据后自动清空）');
        })
        .catch(function(){ load(); flash('同步失败，已刷新列表'); });
    };
  });
  /* 「改库存」：按货位改数量（调盘点接口，二次确认后真实修改快麦库存） */
  box.querySelectorAll('.sbtn.adj').forEach(function(b){
    b.onclick = function(){
      const code = b.dataset.c;
      const row = ROWS.filter(function(r){ return r.c === code; })[0] || {};
      const bins = row.bl || [];
      let bin = bins.length ? String(bins[0][0]) : (prompt('这个编码没有货位记录，请填货位号：') || '');
      if(!bin) return;
      if(bins.length > 1){
        const pick = prompt('有多个货位，要改哪个？（货位=当前数量）',
                            bins.map(function(x){ return x[0] + '=' + x[1]; }).join('  '));
        if(pick === null) return;
        bin = (pick || '').trim() || bin;
      }
      let cur = null;
      bins.forEach(function(x){ if(String(x[0]).toUpperCase() === bin.toUpperCase()) cur = x[1]; });
      const oldTxt = (cur === null) ? '无记录' : (cur + ' 件');
      const v = prompt('把 ' + code + ' 货位 ' + bin + ' 改成多少件？（当前 ' + oldTxt + '）',
                       cur === null ? '0' : String(cur));
      if(v === null) return;
      const qty = parseInt(v, 10);
      if(isNaN(qty) || qty < 0){ alert('数量要填 0 或正整数'); return; }
      if(!confirm('确认改库存？\n\n编码：' + code + '\n货位：' + bin + '\n' + oldTxt + ' → ' + qty
                  + ' 件\n\n【这会真实修改快麦里的库存，不可撤销】')) return;
      flash('正在改库存…');
      fetch(withSid('/api/stock/adjust'), {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({code: code, bin: bin, qty: qty, confirm: 1})})
        .then(function(r){ return r.json(); })
        .then(function(j){
          alert((j.ok ? '✓ 已改：' : '✗ 失败：') + (j.msg || '')
                + (j.ok ? ('\n' + code + ' @ ' + bin + ' → ' + j.new + ' 件') : ''));
          flash(j.ok ? ('已改库存：' + code + ' @ ' + bin + ' → ' + j.new + ' 件')
                     : ('改库存失败：' + (j.msg || '')));
          if(j.ok) load();
        })
        .catch(function(e){ alert('网络错误：' + e.message); });
    };
  });
  /* 「盘0」：两道确认后把该货位盘成 0（避免误操作） */
  box.querySelectorAll('.sbtn.zero').forEach(function(b){
    b.onclick = function(){
      const code = b.dataset.c;
      const row = ROWS.filter(function(r){ return r.c === code; })[0] || {};
      const bins = (row.bl || []).filter(function(x){ return Number(x[1]) > 0; });
      if(!bins.length){ alert('这个编码当前没有在架数量，无需盘0'); return; }
      let bin = String(bins[0][0]), cur = bins[0][1];
      if(bins.length > 1){
        const pick = prompt('有多个货位有货，要盘哪个为 0？（货位=当前数量）',
                            bins.map(function(x){ return x[0] + '=' + x[1]; }).join('  '));
        if(pick === null) return;
        bin = (pick || '').trim() || bin;
        let found = null;
        bins.forEach(function(x){ if(String(x[0]).toUpperCase() === bin.toUpperCase()) found = x[1]; });
        if(found !== null) cur = found;
      }
      if(!confirm('确认盘0？\n\n编码：' + code + '\n货位：' + bin + '\n' + cur + ' 件 → 0 件\n\n'
                  + '【这会真实修改快麦库存，不可撤销】')) return;
      if(!confirm('再确认一次：真的要把 ' + code + ' @ ' + bin + ' 盘成 0 吗？')) return;
      flash('正在盘0…');
      fetch(withSid('/api/stock/adjust'), {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({code: code, bin: bin, qty: 0, confirm: 1})})
        .then(function(r){ return r.json(); })
        .then(function(j){
          alert((j.ok ? '✓ 已盘0：' : '✗ 失败：') + (j.msg || '')
                + (j.ok ? ('\n' + code + ' @ ' + bin + ' → 0 件') : ''));
          flash(j.ok ? ('已盘0：' + code + ' @ ' + bin) : ('盘0失败：' + (j.msg || '')));
          if(j.ok) load();
        })
        .catch(function(e){ alert('网络错误：' + e.message); });
    };
  });
}
$('go').onclick = load;
$('kw').addEventListener('keydown', function(e){ if(e.key === 'Enter'){ e.preventDefault(); load(); } });
/* 记住我的选择：隐藏已发 / 排序 / 筛选（刷新、重开页面都保留） */
try{
  if(localStorage.getItem('km_hide_sent') === '0'){ HIDE_SENT = false; $('hidesent').checked = false; }
  var _s = localStorage.getItem('km_sort'); if(_s){ $('sort').value = _s; }
  var _o = localStorage.getItem('km_only'); if(_o){ $('only').value = _o; }
}catch(e){}
$('sort').onchange = function(){ try{ localStorage.setItem('km_sort', this.value); }catch(e){} load(); };
$('only').onchange = function(){ try{ localStorage.setItem('km_only', this.value); }catch(e){} load(); };
$('hidesent').onchange = function(){
  HIDE_SENT = this.checked;
  try{ localStorage.setItem('km_hide_sent', this.checked ? '1' : '0'); }catch(e){}
  render();
};
$('exp').onclick = function(){ location.href = withSid('/api/stock/export?' + params()); };
load();
</script>
</body></html>
"""
