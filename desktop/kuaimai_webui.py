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
<header><span id="hdrTitle"></span><small id="hdr">连接中…</small><a id="lnkPrints" href="/prints" data-perm="scan.printed"
   style="color:inherit;text-decoration:none;font-size:13px;font-weight:600;padding:4px 10px;
          border-radius:9px;background:rgba(120,120,128,.16);white-space:nowrap">打印记录</a></header>
<div class="wrap">
  <div class="card">
    <div class="row" data-perm="scan.query">
      <input id="code" type="text" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="扫商家编码…" autofocus>
      <button id="btnQuery" class="ghost" data-perm="scan.query">查询</button>
    </div>
    <div class="toolbar nav4" id="navBar">
      <button id="btnCam" class="ghost" data-perm="scan.camera">摄像头扫码</button>
      <button id="btnOrder" class="ghost" data-perm="order.query">订单查询</button>
      <button id="btnStock" class="ghost" data-perm="stock.view">现货可发</button>
      <button id="btnTake" class="ghost" data-perm="stocktake.view">库存盘点</button>
      <button id="btnSound" class="ghost" data-perm="ui.sound">声音：开</button>
    </div>
    <div id="camBox" class="hidden" style="margin-top:8px">
      <video id="video" playsinline muted></video>
      <div class="toolbar"><button id="btnCamStop" class="ghost" data-perm="scan.camera">关闭摄像头</button></div>
    </div>
  </div>
  <div id="result">
    <div id="rcode">就绪</div>
    <div id="rmain">扫码后显示</div>
    <div id="rdetail"></div>
    <!-- 可发：像「现货可发」页那样就地填数量，写一条扫码记录 → 电脑端立刻能看到 -->
    <div id="rfree" style="display:none;align-items:center;gap:8px;margin-top:12px;flex-wrap:wrap" data-perm="stock.canprint">
      <span style="font-size:14px;color:#3a3a3c">可发数量</span>
      <input id="rqty" type="number" inputmode="numeric" min="0" step="1"
             style="width:96px;font-size:21px;font-weight:800;padding:8px;text-align:center">
      <span style="font-size:13px;color:#3a3a3c">宽限</span>
      <span id="rholdTip" style="font-size:12px;color:#8e8e93">（宽限时长在电脑端设置）</span>
      <button id="btnFree" class="ghost" style="font-weight:800;padding:10px 18px">可发</button>
      <button id="btnFreeUndo" class="ghost" style="display:none">撤回</button>
      <span style="font-size:12px;color:#8e8e93">（只有这里点「可发」并填数量才写进电脑端扫码记录；上面的秒数内可撤回，撤回就不写）</span>
      <span id="rfreeMsg" style="font-size:13px;color:#1e9e4a"></span>
    </div>
  </div>
  <div class="card" data-perm="scan.filter">
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
    try { if(s.web_hold!=null){ window.KM_HOLD=s.web_hold;
      const t=$('rholdTip'); if(t) t.textContent='（电脑端设置：'+s.web_hold+' 秒内可撤回，撤回就不写）'; } } catch(e){}
  } catch(e){ $('hdr').textContent='连接失败'; }
}
async function query(code){
  code=(code||'').trim(); if(!code) return;
  CUR = code;
  showFree(false);                       // 每次新查询先收起「可发」，查到单编码再弹出来
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
  function urgentLine(ue){
  ue = ue || {};
  return '<br><span style="color:#c62828;font-weight:700">一单一件 加急 中通 ' + (ue['中通'] || 0) + '单</span>'
       + '<br><span style="color:#c62828;font-weight:700">一单一件 加急 申通 ' + (ue['申通'] || 0) + '单</span>';
  }
$('rmain').innerHTML = `待发货一单一件：${onePiece}<br>待发货一单多件：${multiPiece}` + urgentLine(d.ue);
  $('rdetail').innerHTML = `货位：${bins}（在架 ${d.shelf}）`
    + (short ? '<br><span style="color:#c62828;font-weight:800;font-size:22px">需补货</span>' : '');
  // 可发：默认值 = min(在架, 待发) − 一单多件；填多少就写多少（和「现货可发」页同一个接口）
  LAST = {code:d.code, bins:bins, pieces:d.pieces||0, shelf:d.shelf||0, multi:multiPiece};
  showFree(true);
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
try{ const _h=localStorage.getItem('km_hold'); if(_h && $('rhold')) $('rhold').value=_h; }catch(e){}
/* ---------------- 查询结果里的「可发」：就地填数量 → 写一条扫码记录（和电脑端联动） ---------------- */
let LAST=null;
const SID=(function(){ try { return localStorage.getItem('km_sid') || ''; } catch(e){ return ''; } })();
function postq(){ return '?k=' + encodeURIComponent(K) + (SID ? ('&sid=' + encodeURIComponent(SID)) : ''); }
function freeDefault(){
  if(!LAST) return 0;
  return Math.max(0, Math.min(LAST.shelf||0, LAST.pieces||0) - (LAST.multi||0));
}
function showFree(on){
  const box=$('rfree'); if(!box) return;
  const can=(!window.KM_CAN) || window.KM_CAN('stock.canprint');
  box.style.display=(on&&can)?'flex':'none';
  if(on&&can){
    if($('rqty')) $('rqty').value=String(freeDefault());
    if($('rfreeMsg')) $('rfreeMsg').textContent='';
    if($('btnFreeUndo')) $('btnFreeUndo').style.display='none';
  }
}
async function sendFree(undo){
  if(!LAST) return;
  const code=LAST.code;
  try{
    let url, body;
    if(undo){ url='/api/stock/canprint'+postq(); body={code:code, cancel:1}; }
    else{
      const q=parseInt($('rqty').value,10);
      if(isNaN(q)||q<0){ alert('可发数量要填 0 或正整数'); return; }
      url='/api/stock/canprint'+postq();
      body={code:code, qty:q, bins:LAST.bins||'', pending:LAST.pieces||0, shelf:LAST.shelf||0};
    }
    const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    let j={}; try{ j=await r.json(); }catch(e){}
    if(!r.ok||!j.ok){ alert('保存失败：'+((j&&j.error)||('HTTP '+r.status))); return; }
    if($('rfreeMsg')){
      $('rfreeMsg').textContent = undo ? ('已撤回：'+code+'（电脑端不会出现这条'
          + ((j&&j.jobs_cancelled) ? ('；已取消 '+j.jobs_cancelled+' 个未开打的打单任务') : '')
          + '）')
        : (j.dup ? ('已记可打单，但'+j.dup_msg+'：本次未新建打单任务（避免重复出纸）')
        : ('已提交：'+code+' 可发 '+$('rqty').value+' 件，'+(window.KM_HOLD||10)+' 秒内点「撤回」就不写进电脑端'));
    }
    if($('btnFreeUndo')) $('btnFreeUndo').style.display = undo ? 'none' : '';
    beep(!undo);
  }catch(e){ alert('网络错误：'+e.message); }
}
if($('btnFree')) $('btnFree').onclick=()=>sendFree(false);
if($('btnFreeUndo')) $('btnFreeUndo').onclick=()=>sendFree(true);
if($('rqty')) $('rqty').addEventListener('keydown', e=>{ if(e.key==='Enter'){ e.preventDefault(); sendFree(false); } });
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
/* ---------------- 打印记录：独立页面 /prints ---------------- */
const _lnkPrints = $('lnkPrints');
if(_lnkPrints) _lnkPrints.onclick = function(e){
  if(e) e.preventDefault();
  const sid = (function(){ try { return localStorage.getItem('km_sid') || ''; } catch(e){ return ''; } })();
  location.href = '/prints' + (sid ? ('?sid=' + encodeURIComponent(sid)) : '');
  return false;
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
    <button id="btnGo" data-perm="pick.start">开始拣货</button>
  </div>
  <div class="row row4" style="margin-top:8px">
    <button id="btnRefresh" class="ghost" data-perm="pick.start">重新拉取</button>
    <button id="btnEnd" class="ghost" data-perm="pick.end">结束批次</button>
    <button id="btnSpeak" class="ghost" data-perm="pick.speak">播报：开</button>
    <button id="btnHome" class="ghost">返回扫码</button>
  </div>
  <div id="pinfo" class="muted" style="margin-top:8px">—</div>
</div>
<div class="zones" id="zones"></div>
<div class="filters" id="filters">
  <button data-f="one">单条</button>
  <button id="btnZone" data-perm="pick.zone">按分区拣货</button>
  <button data-f="pending" class="ghost">待拣</button>
  <button data-f="all" class="ghost">全部</button>
  <button data-f="done" class="ghost">已完成</button>
  <button data-f="short" class="ghost">无货</button>
</div>
<div id="plist"></div>
<div id="psumbox" class="card hidden"><pre id="psum"></pre></div>
<div class="bar">
  <button id="btnSum" class="ghost">按货位汇总</button>
  <button id="btnEnd2" data-perm="pick.end">结束批次</button>
</div>
<script>
const K = new URLSearchParams(location.search).get('k') || '';
const $ = function(id){ return document.getElementById(id); };
const CAN = function(k){ return window.KM_CAN ? window.KM_CAN(k) : true; };
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
          ? (CAN('pick.mark') ? ('<div class="pbtns">'
             + '<button class="pdone" data-o="' + oi + '" data-l="' + nl.i + '" data-s="done">拣货完成</button>'
             + '<button class="pshort" data-o="' + oi + '" data-l="' + nl.i + '" data-s="short">'
             + ((!nl.l.bins || nl.l.bins === '无在架货位') ? '无货位' : '无货') + '</button>'
             + '</div>') : '')
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
const CAN = function(k){ return window.KM_CAN ? window.KM_CAN(k) : true; };
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
        + (CAN('stock.edit') ? ('<button class="sbtn adj" data-c="' + esc(r.c) + '" data-b="' + esc(b[0]) + '" data-n="' + sh + '">改库存</button>') : '')
        + (CAN('stock.zero') ? ('<button class="sbtn zero" data-c="' + esc(r.c) + '" data-b="' + esc(b[0]) + '" data-n="' + sh + '">盘0</button>') : '')
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
    <button id="exp" data-perm="stock.export" title="导出 Excel：编码 / 货位 / 一单一件 / 一单多件 / 多件件数 / 加急 / 待发货 / 在架 / 可发 / 加急有货">导出</button>
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
const CAN = function(k){ return window.KM_CAN ? window.KM_CAN(k) : true; };
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
      + ' · 在架 ' + r.s + ' · 一件 ' + r.n + ' · 多件 ' + r.m + '(' + (r.mp == null ? 0 : r.mp) + ')' + (function(ue){ue=ue||{};var p=[];if(ue['中通'])p.push('中通 '+ue['中通']+'件');if(ue['申通'])p.push('申通 '+ue['申通']+'件');return ' <span style="color:#c62828;font-weight:700">· 加急 中通 '+((r.ue&&r.ue['中通'])||0)+'单 申通 '+((r.ue&&r.ue['申通'])||0)+'单</span>';})(r.ue)
      + ((r.up || r.uo) ? (' · <span style="color:#c62828;font-weight:800">加急 ' + (r.uo || 0) + '/' + (r.up || 0) + '</span>') : '')
      + (r.l ? (' · 锁定 ' + r.l) : '') + '</div></div>'
      + '<div class="btns">'
      + (CAN('stock.canprint') ? ('<button class="sbtn' + (r.sent ? ' undo' : '') + '" data-c="' + esc(r.c) + '">'
          + (r.sent ? '撤回' : '可发') + '</button>') : '')
      + (CAN('stock.edit') ? ('<button class="sbtn adj" data-c="' + esc(r.c) + '">改库存</button>') : '')
      + (CAN('stock.zero') ? ('<button class="sbtn zero" data-c="' + esc(r.c) + '">盘0</button>') : '')
      + '</div></div>';
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
              if(j && j.ok){
                if(j.dup){ flash('已记可打单：' + code + ' ' + q + '，但' + j.dup_msg
                                 + '：本次未新建打单任务（避免重复出纸）'); }
                else { flash('已记可打单：' + code + ' ' + q + '（电脑端扫码记录已更新）'); }
              }
              else { flash('记录失败：' + ((j && (j.msg || j.error)) || '未知')); alert('没能写入扫码记录：' + ((j && (j.msg || j.error)) || '未知')); }
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


# ====================== 权限管理（管理员专用：账号 × 按钮 勾选矩阵） ======================
PERMS_HTML = r"""<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>权限管理 · 快麦扫码查询</title>
<style>
  * { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
  :root { --blue:#007AFF; --green:#34C759; --red:#FF3B30; --ink:#1d1d1f; --sub:#6e6e73;
          --line:rgba(60,60,67,.12); --fill:rgba(120,120,128,.10); --glass:rgba(255,255,255,.80); }
  body { margin:0; padding:12px 12px 96px; color:var(--ink);
         font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
         letter-spacing:-.01em; -webkit-font-smoothing:antialiased; font-size:16px;
         background:linear-gradient(170deg,#eef3fa 0%,#e6edf8 45%,#e1e8f4 100%) fixed; }
  h1 { font-size:19px; margin:2px 0 6px; }
  .note { font-size:12.5px; color:var(--sub); line-height:1.7; margin-bottom:10px; }
  .note a { color:var(--blue); text-decoration:none; }
  #msg { font-size:13.5px; font-weight:700; color:var(--green); margin:6px 2px 8px; min-height:18px; line-height:1.5; }
  #msg.bad { color:#c62828; }
  .chips { display:flex; gap:8px; overflow-x:auto; padding:2px 2px 10px; -webkit-overflow-scrolling:touch; }
  .chip { flex:0 0 auto; border:1px solid var(--line); background:var(--glass); color:var(--ink);
          border-radius:999px; padding:9px 14px; font-size:14.5px; font-weight:600; font-family:inherit;
          display:flex; align-items:center; gap:6px; }
  .chip.on { background:var(--blue); border-color:var(--blue); color:#fff; }
  .dot { width:7px; height:7px; border-radius:50%; background:var(--green); }
  .tag { font-size:11px; border-radius:6px; padding:1px 6px; background:var(--fill); color:var(--sub); font-weight:600; }
  .chip.on .tag { background:rgba(255,255,255,.25); color:#fff; }
  .tag.own { background:rgba(255,149,0,.18); color:#a85b00; }
  .tag.adm { background:rgba(255,59,48,.14); color:#c62828; }
  .card { background:var(--glass); backdrop-filter:saturate(180%) blur(20px);
          -webkit-backdrop-filter:saturate(180%) blur(20px); border:1px solid rgba(255,255,255,.62);
          border-radius:14px; padding:6px 12px; box-shadow:0 8px 24px rgba(24,39,75,.10); margin-bottom:12px; }
  .card h2 { font-size:13px; color:var(--sub); font-weight:700; letter-spacing:.04em;
             margin:10px 0 4px; }
  .row { display:flex; align-items:center; gap:10px; padding:12px 0; border-bottom:1px solid var(--line); }
  .row:last-child { border-bottom:0; }
  .row .txt { flex:1; min-width:0; }
  .row .lbl { font-size:15.5px; line-height:1.35; }
  .row .key { font-size:11.5px; color:#8e8e93; margin-top:2px; word-break:break-all; }
  .sw { position:relative; flex:0 0 52px; width:52px; height:32px; }
  .sw input { position:absolute; opacity:0; width:100%; height:100%; margin:0; }
  .sw i { position:absolute; inset:0; border-radius:16px; background:var(--fill); transition:background .18s; }
  .sw i:after { content:""; position:absolute; top:3px; left:3px; width:26px; height:26px; border-radius:50%;
        background:#fff; box-shadow:0 1px 3px rgba(0,0,0,.25); transition:transform .18s; }
  .sw input:checked + i { background:var(--green); }
  .sw input:checked + i:after { transform:translateX(20px); }
  .sw input:disabled + i { opacity:.45; }
  .row.dis .lbl { color:var(--sub); }
  .who { font-size:12.5px; color:var(--sub); line-height:1.6; margin:8px 0 2px; }
  .grid { display:block; }
  @media (min-width:820px) { .grid { display:grid; grid-template-columns:1fr 1fr; gap:0 16px; align-items:start; } }
  .bar { position:fixed; left:0; right:0; bottom:0; display:flex; gap:8px; padding:10px 12px 14px;
         background:rgba(255,255,255,.88); backdrop-filter:saturate(180%) blur(20px);
         -webkit-backdrop-filter:saturate(180%) blur(20px); border-top:1px solid var(--line); }
  .bar button { flex:1; padding:14px 8px; font-size:16px; font-weight:700; border:0; border-radius:12px;
         background:var(--blue); color:#fff; font-family:inherit; }
  .bar button.g { flex:0 0 auto; padding:14px 12px; background:var(--fill); color:var(--blue); font-size:14.5px; }
  .bar button:disabled { opacity:.5; }
  @media (prefers-color-scheme: dark) {
    body { background:linear-gradient(170deg,#1c1c1e,#151517 60%,#1a1a1c) fixed; color:#f2f2f7; }
    .card, .chip { background:rgba(28,28,30,.74); border-color:rgba(255,255,255,.08); }
    .chip.on { background:var(--blue); }
    .bar { background:rgba(28,28,30,.88); border-top-color:rgba(255,255,255,.08); }
    .sw i { background:rgba(120,120,128,.28); }
  }
</style></head>
<body>
<h1>权限管理</h1>
<div class="note">选一个账号 → 打开/关掉它可用的功能 → <b>保存后立即生效</b>（没开的按钮不显示，直接调接口也会被拒 403）。<br>
查询类默认开放；动作类（改库存、盘 0、可发…）默认关闭。主账号与管理员的权限不用配。 <a href="/">返回扫码</a></div>
<div id="msg"></div>
<div class="chips" id="chips"></div>
<div id="panel">正在载入…</div>
<div class="bar">
  <button id="save">保存</button>
  <button class="g" id="all">全选</button>
  <button class="g" id="none">全不选</button>
  <button class="g" id="reload">重载</button>
</div>
<script>
const $ = id => document.getElementById(id);
const esc = s => String(s==null?'':s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const SID = (function(){
  try { const q = new URLSearchParams(location.search).get('sid'); if(q) localStorage.setItem('km_sid', q);
        return localStorage.getItem('km_sid') || ''; } catch(e){ return ''; }
})();
function withSid(u){ return SID ? (u + (u.indexOf('?') >= 0 ? '&' : '?') + 'sid=' + encodeURIComponent(SID)) : u; }
let DATA = null, CUR = null, DIRTY = 0;

function msg(t, bad){ const el = $('msg'); el.textContent = t || ''; el.className = bad ? 'bad' : ''; }

function load(){
  msg('正在载入…');
  fetch(withSid('/api/perms'), {cache:'no-store'})
    .then(r => r.json())
    .then(d => {
      if(d.error || d.denied){ msg(d.error || '没有权限管理权限', true); $('panel').innerHTML=''; return; }
      DATA = d; DIRTY = 0;
      const us = d.users || [];
      if(!CUR || !us.some(u => u.name === CUR.name)) CUR = us[0] || null;
      else CUR = us.filter(u => u.name === CUR.name)[0];
      render();
      msg('共 ' + us.length + ' 个账号 · ' + (d.catalog||[]).length + ' 项权限');
    })
    .catch(e => msg('载入失败：' + e.message, true));
}

function userByName(n){ return (DATA.users||[]).filter(u => u.name === n)[0] || null; }

function render(){ renderChips(); renderPanel(); }

function renderChips(){
  const us = DATA.users || [];
  $('chips').innerHTML = us.map(function(u){
    const tag = u.owner ? '<span class="tag own">主账号</span>'
              : (u.role === 'admin' ? '<span class="tag adm">管理员</span>' : '<span class="tag">子账号</span>');
    const dot = u.online ? '<span class="dot"></span>' : '';
    return '<button class="chip' + (CUR && u.name === CUR.name ? ' on' : '') + '" data-u="' + esc(u.name) + '">'
         + dot + esc(u.name) + tag + (u.allow_multi_device ? '<span class="tag">双端</span>' : '') + '</button>';
  }).join('');
  $('chips').querySelectorAll('button[data-u]').forEach(function(b){
    b.onclick = function(){ CUR = userByName(b.getAttribute('data-u')); render(); };
  });
}

function renderPanel(){
  if(!CUR){ $('panel').innerHTML = '<div class="card"><div class="row"><div class="txt">还没有账号</div></div></div>'; return; }
  const cat = DATA.catalog || [], groups = DATA.groups || [];
  const isAdmin = CUR.role === 'admin';
  const locked = isAdmin;                       // 管理员全开、不用配
  let h = '';
  h += '<div class="card"><h2>账号设置</h2>';
  h += '<div class="row' + (locked ? '' : '') + '"><div class="txt"><div class="lbl">电脑端 + 网页端同时登录</div>'
     + '<div class="key">关：一处登录，新的把旧的顶下线　开：电脑端、网页端各留一个</div></div>'
     + '<label class="sw"><input type="checkbox" id="multi"' + (CUR.allow_multi_device ? ' checked' : '') + '><i></i></label></div>';
  h += '<div class="who">身份：' + (CUR.owner ? '主账号（主客户端只能用主账号登录）'
        : (isAdmin ? '管理员' : '子账号'))
     + (CUR.owner ? '' : '') + (CUR.device ? '　·　最近登录设备：' + esc(CUR.device) : '')
     + (CUR.online ? '　·　当前在线（' + esc((CUR.kinds||[]).join(' / ')) + '）' : '') + '</div>';
  h += '</div>';
  if(locked){
    h += '<div class="card"><h2>权限</h2><div class="row"><div class="txt">'
       + '<div class="lbl">' + (CUR.owner ? '主账号' : '管理员') + '始终拥有全部权限</div>'
       + '<div class="key">不用配置；要限制它就请先把它改成子账号（桌面端权限管理里改）</div>'
       + '</div></div></div>';
  } else {
    groups.forEach(function(g){
      h += '<div class="card"><h2>' + esc(g.name) + '</h2>';
      (g.keys||[]).forEach(function(k){
        const c = cat.filter(x => x.key === k)[0] || {key:k, label:k};
        const on = !!(CUR.perms && CUR.perms[k]);
        h += '<div class="row"><div class="txt"><div class="lbl">' + esc(c.label) + '</div>'
           + '<div class="key">' + esc(k) + '</div></div>'
           + '<label class="sw"><input type="checkbox" data-k="' + esc(k) + '"' + (on ? ' checked' : '') + '><i></i></label></div>';
      });
      h += '</div>';
    });
    $('panel').innerHTML = '<div class="grid" id="grid"></div>';
    const grid = $('grid'), cards = [];
    // 把上面的卡片按两列排（宽屏）；手机上单列
    let tmp = document.createElement('div'); tmp.innerHTML = h;
    while(tmp.firstChild){ cards.push(tmp.firstChild); tmp.removeChild(tmp.firstChild); }
    const colA = document.createElement('div'), colB = document.createElement('div');
    cards.forEach(function(c, i){ (i % 2 === 0 ? colA : colB).appendChild(c); });
    grid.appendChild(colA); grid.appendChild(colB);
  }
  if(locked){ $('panel').innerHTML = h; }
  const m = $('multi');
  if(m) m.onchange = function(){ CUR.allow_multi_device = !!m.checked; DIRTY++; msg('改动未保存：同时登录已设为「' + (m.checked ? '开' : '关') + '」'); };
  $('panel').querySelectorAll('input[data-k]').forEach(function(b){
    b.onchange = function(){
      if(!CUR.perms) CUR.perms = {};
      CUR.perms[b.getAttribute('data-k')] = !!b.checked;
      DIRTY++;
      msg('改动未保存：' + b.getAttribute('data-k') + ' → ' + (b.checked ? '开' : '关'));
    };
  });
  updateBar();
}

function updateBar(){
  $('save').textContent = DIRTY ? ('保存（' + DIRTY + ' 处改动）') : '保存';
  $('save').disabled = false;
}

function setAll(v){
  if(!CUR || CUR.role === 'admin'){ msg('管理员不用配置', true); return; }
  $('panel').querySelectorAll('input[data-k]').forEach(function(b){ b.checked = v; });
  if(!CUR.perms) CUR.perms = {};
  (DATA.catalog||[]).forEach(function(c){ CUR.perms[c.key] = v; });
  DIRTY++; msg('改动未保存：本账号权限已' + (v ? '全选' : '全不选'));
  updateBar();
}

async function save(){
  if(!DATA){ msg('还没载入', true); return; }
  const us = DATA.users || [];
  let okN = 0; const errs = [];
  for(let i = 0; i < us.length; i++){
    const u = us[i];
    if(u.role === 'admin') continue;                  // 管理员全开，不用写
    try {
      const r = await fetch(withSid('/api/perms'), {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({name: u.name, perms: u.perms || {}})});
      const j = await r.json();
      if(r.ok && j.ok){ okN++; } else { errs.push(u.name + '：' + ((j && j.error) || ('HTTP ' + r.status))); }
    } catch(e){ errs.push(u.name + '：' + e.message); }
    try {
      const r2 = await fetch(withSid('/api/users'), {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({action:'multi', name: u.name, flag: !!u.allow_multi_device})});
      const j2 = await r2.json();
      if(!(r2.ok && j2.ok)) errs.push(u.name + '（同时登录）：' + ((j2 && j2.error) || ('HTTP ' + r2.status)));
    } catch(e){ errs.push(u.name + '（同时登录）：' + e.message); }
  }
  DIRTY = 0;
  if(errs.length){ msg('保存 ' + okN + ' 个，失败 ' + errs.length + ' 个 —— ' + errs.join('；'), true); }
  else { msg('已保存 ' + okN + ' 个账号权限 + 同时登录设置（立即生效）'); }
  load();
}

$('save').onclick = save;
$('all').onclick = function(){ setAll(true); };
$('none').onclick = function(){ setAll(false); };
$('reload').onclick = load;
window.addEventListener('beforeunload', function(e){ if(DIRTY){ e.preventDefault(); e.returnValue = ''; } });
load();
</script>
</body></html>
"""


# ============================ 网页「打印记录」页（/prints） ============================
# 数据来自 GET /api/print/stats 的 live（正在打印 / 排队 / **打印完成** / 失败）；
# 分区口径：排队区只列**未完成**（待打 + 正在打印），打完了进「打印完成」区。
# 登录 / 权限 / 会话完全沿用现有机制（服务端 _auth + _page 注权限，前端只读 km_sid）。
PRINTS_HTML = r"""<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>打印记录 · 快麦</title>
<style>
  * { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
  :root { --blue:#007AFF; --green:#34C759; --red:#FF3B30; --orange:#FF9500; --ink:#1d1d1f; --sub:#6e6e73;
          --line:rgba(60,60,67,.12); --fill:rgba(120,120,128,.12); --glass:rgba(255,255,255,.80); }
  body { margin:0; padding:12px; min-height:100vh; color:var(--ink); letter-spacing:-.01em;
         -webkit-font-smoothing:antialiased;
         font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
         background:linear-gradient(170deg,#eef3fa 0%,#e6edf8 45%,#e1e8f4 100%) fixed; }
  header { display:flex; align-items:center; gap:8px; padding:2px 3px 10px; }
  header b { font-size:17px; }
  header .sp { flex:1; }
  header a.home { color:var(--blue); text-decoration:none; font-size:13.5px; font-weight:600;
                  background:var(--fill); border-radius:9px; padding:5px 11px; white-space:nowrap; }
  .card { background:var(--glass); backdrop-filter:saturate(180%) blur(20px);
          -webkit-backdrop-filter:saturate(180%) blur(20px); border:1px solid rgba(255,255,255,.62);
          border-radius:14px; padding:12px; margin-bottom:10px; box-shadow:0 8px 24px rgba(24,39,75,.10); }
  .sums { display:flex; gap:8px; margin-bottom:10px; }
  .sum { flex:1 1 0; min-width:0; text-align:center; padding:11px 4px; border-radius:14px;
         background:var(--glass); backdrop-filter:saturate(180%) blur(20px);
         -webkit-backdrop-filter:saturate(180%) blur(20px); border:1px solid rgba(255,255,255,.62);
         box-shadow:0 8px 24px rgba(24,39,75,.10); }
  .sum b { display:block; font-size:24px; line-height:1.15; letter-spacing:-.02em; }
  .sum span { font-size:12.5px; color:var(--sub); }
  .sum.run b { color:var(--blue); } .sum.wait b { color:var(--orange); } .sum.fail b { color:var(--red); }
  .sum.ok b { color:var(--green); }
  .secttl { font-size:14px; font-weight:700; padding:2px 6px 6px; }
  .tblwrap { padding:6px 6px 2px; overflow-x:auto; -webkit-overflow-scrolling:touch; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th, td { padding:7px 6px; border-bottom:1px solid rgba(60,60,67,.08); text-align:left;
           white-space:nowrap; }
  th { color:var(--sub); font-weight:500; background:transparent; position:sticky; top:0; z-index:2; }
  tbody tr:last-child td { border-bottom:0; }
  td.code { font-weight:700; }
  .pill { display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; font-weight:700; }
  .pill.run { background:rgba(0,122,255,.14); color:#0b5394; }
  .pill.wait { background:rgba(255,149,0,.16); color:#a35c00; }
  .pill.ok { background:rgba(52,199,89,.15); color:#1B7F35; }
  .pill.bad { background:rgba(255,59,48,.13); color:#c62828; }
  td.msg { max-width:280px; white-space:normal; font-size:12.5px; color:var(--sub); }
  .muted { font-size:12.5px; color:var(--sub); line-height:1.7; }
  .opbtn { border:0; border-radius:9px; padding:4px 10px; font-size:12.5px; font-weight:600;
           color:#c62828; background:rgba(255,59,48,.12); cursor:pointer; white-space:nowrap; }
  .opbtn:active { transform:scale(.96); }
  td.op { text-align:right; }
  .legend b { color:var(--ink); }
  @media (prefers-color-scheme: dark) {
    body { background:linear-gradient(170deg,#1c1c1e,#151517 60%,#1a1a1c) fixed; color:#f2f2f7; }
    .card, .sum { background:rgba(28,28,30,.74); border-color:rgba(255,255,255,.08); }
    .muted, td.msg { color:#a1a1a6; }
    .legend b { color:#f2f2f7; }
    .sum.run b { color:#5aa9ff; } .sum.wait b { color:#ffb340; } .sum.fail b { color:#ff6b62; }
    .sum.ok b { color:#4cd964; }
    th, td { border-bottom-color:rgba(255,255,255,.08); }
  }
</style></head>
<body>
<header><span id="hdrTitle"></span><b>打印记录</b><span class="sp"></span>
  <span class="muted" id="upd">载入中…</span>
  <a class="home" href="#" id="clrFail" data-perm="scan.printed">清空失败任务</a>
  <a class="home" href="/" id="home">返回扫码</a></header>
<div class="sums">
  <div class="sum run"><b id="nRun">0</b><span>正在打印</span></div>
  <div class="sum wait"><b id="nWait">0</b><span>排队</span></div>
  <div class="sum ok"><b id="nDone">0</b><span>打印完成</span></div>
  <div class="sum fail"><b id="nFail">0</b><span>失败</span></div>
</div>
<div class="card">
  <div class="secttl">排队中 / 正在打印</div>
  <div class="tblwrap">
  <table>
    <thead><tr>
      <th>时间</th><th>编码</th><th>成功数量</th><th>来源账号</th>
      <th>状态</th><th>哪台电脑</th><th>运单号</th><th>备注</th><th>操作</th>
    </tr></thead>
    <tbody id="tbQueue"><tr><td colspan="9" class="muted">载入中…</td></tr></tbody>
  </table>
  </div>
</div>
<div class="card">
  <div class="secttl">打印完成</div>
  <div class="tblwrap">
  <table>
    <thead><tr>
      <th>完成时间</th><th>编码</th><th>成功数量</th><th>来源账号</th>
      <th>状态</th><th>哪台电脑</th><th>运单号</th><th>备注</th><th>操作</th>
    </tr></thead>
    <tbody id="tbDone"><tr><td colspan="9" class="muted">（暂无）</td></tr></tbody>
  </table>
  </div>
</div>
<div class="card">
  <div class="secttl">失败</div>
  <div class="tblwrap">
  <table>
    <thead><tr>
      <th>时间</th><th>编码</th><th>数量</th><th>来源账号</th>
      <th>状态</th><th>哪台电脑</th><th>运单号</th><th>失败原因</th><th>操作</th>
    </tr></thead>
    <tbody id="tbFail"><tr><td colspan="9" class="muted">（暂无）</td></tr></tbody>
  </table>
  </div>
</div>
<div class="card"><div class="legend muted">
  <b>正在打印</b> = 已被某台电脑领走、还没回写（超过 5 分钟没回写会自动回「排队」重试）；
  <b>打印完成</b> = 已经打出来的任务（打完就进这里，**不再留在「排队中」**，可查运单号与完成时间）；
  <b>失败</b> = 重试 3 次仍失败。<br>
  <b>哪台电脑</b>：「正在打印 / 已打印」显示实际打的那台；「排队」显示派给哪台（没派就是「任意」）。
  数据来自打单任务表，5 秒自动刷新一次。
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
if($('home')) $('home').onclick = function(e){
  if(e) e.preventDefault();
  location.href = SID ? ('/?sid=' + encodeURIComponent(SID)) : '/';
  return false;
};
const STLABEL = {pending:'排队', claimed:'正在打印', printing:'正在打印', done:'已打印', failed:'失败'};
function stLabel(s){ return STLABEL[s] || s || '-'; }
function stCls(s){ return s==='failed' ? 'bad' : (s==='done' ? 'ok' : (s==='pending' ? 'wait' : 'run')); }
function fmt(ts){
  if(ts==null || ts==='') return '-';
  const n = Number(ts);
  if(n && String(ts).length >= 9){                 // epoch 秒
    const d = new Date(n*1000), p = x => String(x).padStart(2,'0');
    return (d.getMonth()+1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
  }
  return String(ts);
}
function dur(sec){
  sec = Number(sec||0);
  if(sec < 60) return sec + '秒';
  if(sec < 3600) return Math.floor(sec/60) + '分';
  return Math.floor(sec/3600) + '小时' + (Math.floor((sec%3600)/60) ? (Math.floor((sec%3600)/60) + '分') : '');
}
function rowsOf(st){
  const live = st.live || {}, out = [], seen = {};
  (live.queue || []).forEach(function(r){
    seen[r.job_id] = 1;
    out.push({job_id:r.job_id, t:fmt(r.created_at), code:r.code, qty:r.qty, who:r.who,
              st:'pending', pc:r.client || '任意', sid:'-',
              msg:(r.retrying ? ('等待重试：' + (r.last_msg || '')) : (r.last_msg || ''))});
  });
  (live.printing || []).forEach(function(r){
    seen[r.job_id] = 1;
    out.push({job_id:r.job_id, t:fmt(r.claim_ts) + '（已' + dur(r.elapsed) + '）', code:r.code, qty:r.qty, who:r.who,
              st:'printing', pc:r.claimed_by || '-', sid:'-',
              msg:(r.tries ? ('重试 ' + r.tries + ' 次后重打') : '')});
  });
  return out;
}
function doneOf(st){
  const live = st.live || {}, out = [], seen = {};
  (live.done || []).forEach(function(r){
    seen[r.job_id] = 1;
    out.push({job_id:r.job_id, t:fmt(r.done_ts), code:r.code, qty:r.qty, who:r.who,
              st:'done', pc:r.claimed_by || r.client || '-', sid:(r.out_sid || '-'),
              msg:(r.last_msg || '')});
  });
  // 兼容：live.done 缺失时，从 recent 里把 done 挑出来（服务端没升级也不会漏显示）
  (st.recent || []).forEach(function(r){
    if(String(r.status) !== 'done') return;
    if(seen[r.job_id]) return;
    seen[r.job_id] = 1;
    out.push({job_id:r.job_id, t:fmt(r.done_ts || r.created_at), code:r.code, qty:r.qty, who:r.who,
              st:'done', pc:(r.claimed_by || r.target_client || '-'), sid:(r.out_sid || '-'),
              msg:(r.last_msg || '')});
  });
  return out;
}
function failedOf(st){
  const live = st.live || {}, out = [];
  (live.failed || []).forEach(function(r){
    out.push({job_id:r.job_id, t:fmt(r.done_ts), code:r.code, qty:r.qty, who:r.who,
              st:'failed', pc:(r.claimed_by || '-'), sid:(r.out_sid || '-'),
              msg:(r.last_msg || '')});
  });
  return out;
}
const CAN_DEL = !(window.KM_CAN && !window.KM_CAN('scan.printed'));
function delJobs(body){
  return fetch(withSid('/api/print/jobs_del'), {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify(body)
  }).then(function(r){
    if(r.status === 401){ location.href = '/login'; throw new Error('请重新登录'); }
    if(r.status === 403){ throw new Error('没有「打印记录」权限，删不了'); }
    return r.json();
  }).then(function(d){
    if(d && d.error) throw new Error(d.error);
    $('upd').textContent = '已删除 ' + ((d && d.deleted) || 0) + ' 个任务';
    load();
    return d;
  });
}
function delOne(btn){
  const id = btn.getAttribute('data-id');
  const code = btn.getAttribute('data-code'), qty = btn.getAttribute('data-qty');
  const st = btn.getAttribute('data-st');
  const busy = (st === 'printing' || st === 'claimed');
  const msg = (busy ? '这条任务正在打印中：\n\n' : '确定删除这条任务吗？\n\n')
      + (code || '?') + ' ×' + (qty || 0) + '  #' + id
      + (busy ? '\n\n正在打印中，先暂停再删（若坚持要删可再确认）。' : '\n\n（删了就没了，不能撤销）');
  if(!confirm(msg)) return;
  btn.disabled = true;
  delJobs({ids:[Number(id)]})['catch'](function(e){
    alert('删除失败：' + e.message);
  }).then(function(){ btn.disabled = false; });
}
function delFailed(){
  const n = Number($('nFail').textContent || 0);
  if(!confirm('确定删掉全部「失败」任务吗？（当前 ' + n + ' 条）\n\n（删了就没了，不能撤销）')) return;
  delJobs({status:'failed'})['catch'](function(e){ alert('删除失败：' + e.message); });
}
if($('clrFail')) $('clrFail').onclick = function(e){ if(e) e.preventDefault(); delFailed(); return false; };
document.addEventListener('click', function(e){
  const t = e.target;
  if(t && t.getAttribute && t.getAttribute('data-act') === 'del'){ e.preventDefault(); delOne(t); }
});
function trOf(r){
  const op = CAN_DEL
    ? ('<td class="op"><button class="opbtn" data-act="del" data-id="' + esc(r.job_id) + '"'
       + ' data-code="' + esc(r.code) + '" data-qty="' + esc(r.qty) + '" data-st="' + esc(r.st)
       + '">删除</button></td>')
    : '<td class="op"></td>';
  return '<tr>'
    + '<td>' + esc(r.t) + '</td>'
    + '<td class="code">' + esc(r.code) + '</td>'
    + '<td>' + esc(r.qty) + '</td>'
    + '<td>' + esc(r.who || '-') + '</td>'
    + '<td><span class="pill ' + stCls(r.st) + '">' + esc(stLabel(r.st)) + '</span></td>'
    + '<td>' + esc(r.pc) + '</td>'
    + '<td>' + esc(r.sid) + '</td>'
    + '<td class="msg">' + esc(r.msg) + '</td>'
    + op
    + '</tr>';
}
function fillTbody(el, rows, emptyText){
  el.innerHTML = rows.length ? rows.map(trOf).join('')
                             : '<tr><td colspan="9" class="muted">' + esc(emptyText) + '</td></tr>';
}
function render(st){
  const counts = (st.live && st.live.counts) || {};
  const queueRows = rowsOf(st), doneRows = doneOf(st), failRows = failedOf(st);
  $('nRun').textContent  = (counts.printing != null) ? counts.printing
                       : queueRows.filter(r => r.st === 'printing').length;
  $('nWait').textContent = (counts.queue != null) ? counts.queue
                       : queueRows.filter(r => r.st === 'pending').length;
  $('nDone').textContent = (counts.done != null) ? counts.done : doneRows.length;
  $('nFail').textContent = (counts.failed != null) ? counts.failed : failRows.length;
  fillTbody($('tbQueue'), queueRows, '排队里没有任务（打完了会进下面「打印完成」）');
  fillTbody($('tbDone'), doneRows, '（暂无）');
  fillTbody($('tbFail'), failRows, '（暂无）');
}
function load(){
  fetch(withSid('/api/print/stats'), {cache:'no-store'})
    .then(function(r){
      if(r.status === 401){ location.href = '/login'; throw new Error('请重新登录'); }
      return r.json();
    })
    .then(function(d){
      if(d.error){ $('upd').textContent = d.error; return; }
      render(d.stats || d);
      const d0 = new Date(), p = x => String(x).padStart(2,'0');
      $('upd').textContent = '更新 ' + p(d0.getHours()) + ':' + p(d0.getMinutes()) + ':' + p(d0.getSeconds());
    })
    .catch(function(e){ $('upd').textContent = '载入失败：' + e.message; });
}
load();
setInterval(function(){ if(!document.hidden) load(); }, 5000);
document.addEventListener('visibilitychange', function(){ if(!document.hidden) load(); });
</script>
</body></html>
"""
