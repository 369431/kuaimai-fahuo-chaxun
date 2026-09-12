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
  location.href = '/pick?' + new URLSearchParams({k:K}).toString();
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
  .hidden { display:none; }
  pre { white-space:pre-wrap; font-family:ui-monospace,Consolas,"Microsoft YaHei",monospace; font-size:14px; margin:0; }
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
/* 按分区排序后的 [ {g,i} ]（分区内保持打印顺序） */
function orderedGroups(){
  const gs = (PICK && PICK.groups ? PICK.groups : []).map(function(g, i){ return { g: g, i: i }; });
  if(!ZONE) return gs;
  return gs.sort(function(a, b){
    return (zoneRank(zoneOf(a.g.bins)) - zoneRank(zoneOf(b.g.bins)))
        || ((a.g.seq_a || 0) - (b.g.seq_a || 0));
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
function currentItem(){
  if(!PICK) return null;
  const gs = orderedGroups();
  for(let i = 0; i < gs.length; i++){
    if((gs[i].g.state || 'pending') === 'pending') return gs[i];
  }
  return null;
}
/* 播报当前要拣的那一条：分区 + 商家编码-颜色-尺码 多少件 */
function speakCurrent(){
  const it = currentItem();
  if(!it){ speak('全部拣完'); return; }
  const z = ZONE ? zoneOf(it.g.bins) : '';
  speak((z ? (z + '区 ') : '') + speakCode(it.g.code) + ' ' + it.g.qty + ' 件');
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
    + ' · 已拣 <b>' + (pr.done||0) + '</b>/' + (pr.groups||0) + ' 组'
    + ((pr.short||0) ? (' · 无货 <b>' + pr.short + '</b> 组') : '')
    + ' · 待拣 ' + (pr.pending||0) + ' 组 · 共 ' + (pr.qty||0) + ' 件（已拣 ' + (pr.qty_done||0) + '）';
  const box = $('plist'); box.innerHTML = '';
  let list = [];
  if(MODE === 'one'){
    const it = currentItem();
    if(it) list.push(it);
  } else {
    orderedGroups().forEach(function(it){
      const g = it.g;
      if(FILTER === 'all' || (g.state || 'pending') === FILTER) list.push(it);
    });
  }
  if(!list.length){
    box.innerHTML = '<div class="card muted">'
      + (MODE === 'one' ? '本批次已全部拣完（含无货）' : '这个筛选下没有条目。') + '</div>';
  }
  list.forEach(function(it){
    const g = it.g, i = it.i;
    const div = document.createElement('div');
    div.className = 'pitem' + (MODE === 'one' ? ' one' : '')
      + (g.state === 'done' ? ' done' : (g.state === 'short' ? ' short' : ''));
    const rng = (g.seq_a===g.seq_b) ? ('第 ' + g.seq_a + ' 张') : ('第 ' + g.seq_a + '-' + g.seq_b + ' 张');
    const ex = (g.sids && g.sids.length) ? (' · 首单 ' + g.sids[0]) : '';
    div.innerHTML = '<div class="pseq">' + rng + ' · ' + g.rows + ' 行' + ex + '</div>'
      + '<div class="pcode">' + (g.code||'（无明细）') + ((ZONE && zoneOf(g.bins)) ? ('<span class="pzone">' + zoneOf(g.bins) + '区</span>') : '') + '</div>'
      + '<div class="pqty' + (g.state==='done'?' done':'') + '">需拣 ' + g.qty + ' 件</div>'
      + '<div class="pbin">货位：<b>' + g.bins + '</b>（在架 ' + g.shelf + '）</div>'
      + '<div class="pmeta">状态：' + (g.state==='done'?'已完成':(g.state==='short'?'无货':'待拣'))
        + (g.marked_at ? (' · ' + g.marked_at) : '') + '</div>'
      + '<div class="pbtns">'
      + '<button class="pdone" data-i="' + i + '" data-s="done">' + (g.state==='done'?'已拣·撤销':'拣货完成') + '</button>'
      + '<button class="pshort" data-i="' + i + '" data-s="short">' + (g.state==='short'?'无货·撤销':'无货') + '</button>'
      + '</div>';
    box.appendChild(div);
  });
  if(!box.children.length) box.innerHTML = '<div class="card muted">这个筛选下没有条目。</div>';
  box.querySelectorAll('button[data-i]').forEach(function(b){
    b.onclick = function(){ mark(parseInt(b.dataset.i, 10), b.dataset.s); };
  });
  const sum = {};
  orderedGroups().forEach(function(it){
    const g = it.g;
    const bs = (g.bins && g.bins !== '无在架货位') ? g.bins.split('、') : ['（无在架货位）'];
    bs.forEach(function(b){ const k2 = b + '|' + g.code; const a = sum[k2] || [0,0]; a[0] += (g.qty||0); a[1] += 1; sum[k2] = a; });
  });
  const lines = ['批次 ' + PICK.batch + '：' + (pr.groups||0) + ' 组 / ' + (pr.qty||0) + ' 件'];
  let cur = null;
  Object.keys(sum).sort().forEach(function(k2){
    const parts = k2.split('|');
    if(parts[0] !== cur){ lines.push(''); lines.push(parts[0] + '：'); cur = parts[0]; }
    lines.push('    ' + parts[1] + ' ×' + sum[k2][0] + '（' + sum[k2][1] + ' 组）');
  });
  $('psum').textContent = lines.join('\n');
}
async function mark(i, state){
  if(!PICK) return;
  const g = PICK.groups[i];
  const target = (g && g.state === state) ? 'pending' : state;
  const qty = (g && g.qty) || 0;
  try {
    const d = await (await fetch(url('/api/pick/mark', {batch:PICK.batch, g:i, state:target}))).json();
    if(d.error){ alert(d.error); return; }
    PICK = d; render();
    if(target === 'done'){ beep(true); }
    else if(target === 'short'){ beep(false); }
    if(MODE === 'one'){ speakCurrent(); }        // 单条模式：直接播报下一条
    else if(target === 'done'){ speak('完成 ' + qty + ' 件'); }
    else if(target === 'short'){ speak('无货 ' + qty + ' 件'); }
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
loadCurrent();
speakBtn();
zoneBtn();
</script></body></html>
"""
