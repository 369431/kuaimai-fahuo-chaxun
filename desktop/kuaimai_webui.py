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
          --mac-line:rgba(60,60,67,.12); --mac-fill:rgba(120,120,128,.12); --mac-glass:#e0e5ec; }
  html { -webkit-text-size-adjust:100%; }
  body { font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
         letter-spacing:-.01em; -webkit-font-smoothing:antialiased; color:var(--mac-ink);
         background:#e0e5ec; min-height:100vh; }
  header { background:var(--mac-glass); color:var(--mac-ink); backdrop-filter:saturate(180%) blur(20px);
           -webkit-backdrop-filter:saturate(180%) blur(20px); border-bottom:1px solid var(--mac-line);
           font-size:17px; font-weight:600; position:sticky; top:0; z-index:20; }
  header small { color:var(--mac-sub); }
  .card, #result, .pitem { background:var(--mac-glass); backdrop-filter:saturate(180%) blur(20px);
           -webkit-backdrop-filter:saturate(180%) blur(20px); border:0;
           border-radius:18px; box-shadow:var(--neu-up); }
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
  .zones button:not(.ghost), .filters button:not(.ghost) { background:#007AFF; color:#fff;
           box-shadow:0 1px 3px rgba(0,0,0,.14); }
  .bar { background:var(--mac-glass); backdrop-filter:saturate(180%) blur(20px);
         -webkit-backdrop-filter:saturate(180%) blur(20px); border-top:1px solid var(--mac-line); }
  .row4 button { border-radius:10px; }
  @media (prefers-color-scheme: dark) {
    body { background:#262b36; color:#f2f2f7; }
    header { background:#262b36; color:#f2f2f7; border-bottom-color:rgba(255,255,255,.08); }
    .card, #result, .pitem, .bar { background:#262b36; border-color:rgba(255,255,255,.08); }
    #rcode, .pcode { color:#fff; }
    input, select, input[type=number] { background:rgba(118,118,128,.24); border-color:rgba(255,255,255,.12); color:#f2f2f7; }
    .zones button, .filters button { color:#ebebf5; }
    .zones button:not(.ghost), .filters button:not(.ghost) { background:rgba(255,255,255,.18); color:#fff; }
    #rdetail { color:#d1d1d6; }
  }
</style>
<style>
:root{--neu-up:8px 8px 18px rgba(163,177,198,.55),-8px -8px 18px rgba(255,255,255,.95);--neu-up-sm:4px 4px 10px rgba(163,177,198,.55),-4px -4px 10px rgba(255,255,255,.95);--neu-in:inset 5px 5px 10px rgba(163,177,198,.5),inset -5px -5px 10px rgba(255,255,255,.9);--neu-in-sm:inset 4px 4px 8px rgba(163,177,198,.5),inset -4px -4px 8px rgba(255,255,255,.9);}
input:not([type=checkbox]):not([type=radio]):not([type=range]),select,textarea{background:#e0e5ec!important;border:0!important;box-shadow:var(--neu-in)!important}
button{border:0;box-shadow:var(--neu-up-sm)}
button.ghost{background:#e0e5ec;box-shadow:var(--neu-up-sm)}
button:active{box-shadow:var(--neu-in-sm)}
@media (prefers-color-scheme:dark){:root{--neu-up:8px 8px 18px rgba(8,10,16,.6),-8px -8px 18px rgba(255,255,255,.06);--neu-up-sm:4px 4px 10px rgba(8,10,16,.6),-4px -4px 10px rgba(255,255,255,.06);--neu-in:inset 5px 5px 10px rgba(8,10,16,.6),inset -5px -5px 10px rgba(255,255,255,.05);--neu-in-sm:inset 4px 4px 8px rgba(8,10,16,.6),inset -4px -4px 8px rgba(255,255,255,.05)}input:not([type=checkbox]):not([type=radio]):not([type=range]),select,textarea{background:#262b36!important}button.ghost{background:#262b36}}
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
    <div class="toolbar" style="margin-top:6px">
      <button id="btnWave" class="ghost" data-perm="wave.view">生成波次</button>
      <button id="btnWaveRec" class="ghost" data-perm="wave.view">波次记录</button>
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

/* ---- PDA 扫码枪兼容（v1.45）----
   1) 有些枪不带回车后缀：一串快速输入后停 ~150ms 就当"扫完了"，自动提交；
   2) 有些 PDA 浏览器不给/丢失自动聚焦：没聚焦时在页面层也接住（打字落到 body）；
   3) 点页面空白处自动把焦点放回编码框。 */
function kmWedge(el, submit, clearAfter){
  /* 扫码枪**带回车后缀**：只认回车提交，不做「快输入自动提交」（避免误触发）。 */
  if(!el || !submit) return;
  el.addEventListener('keydown', function(e){
    if(e.key === 'Enter'){
      e.preventDefault();
      var v=(el.value||'').trim();
      if(v){ submit(v); if(clearAfter){ el.value=''; } }
    }
  });
}
kmWedge($('code'), function(v){ query(v); }, false);
/* 没聚焦时也接住（打字落到 body）：回车 / 一串≥6 字符快输入 就提交 */
(function(){
  var buf='';
  document.addEventListener('keydown', function(e){
    var tg=e.target||{};
    if(tg.tagName==='INPUT'||tg.tagName==='TEXTAREA'||tg.isContentEditable) return;
    if(e.key==='Enter'){ var v=buf.trim(); buf=''; if(v.length>=4){ query(v); } return; }
    if(e.key && e.key.length===1){ buf += e.key; }   /* 没聚焦时先攒着，等回车再提交 */
  });
  /* 点空白处把焦点放回编码框（PDA 浏览器常丢焦点） */
  document.addEventListener('click', function(e){
    var tg=e.target||{};
    if(tg.tagName==='BUTTON'||tg.tagName==='INPUT'||tg.tagName==='SELECT'||tg.tagName==='TEXTAREA'||tg.tagName==='A') return;
    try{ $('code').focus(); }catch(_){}
  });
})();
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
/* ---------------- 生成波次：独立页面 /wave ---------------- */
const _btnWave = $('btnWave');
if(_btnWave) _btnWave.onclick = () => {
  const sid = (function(){ try { return localStorage.getItem('km_sid') || ''; } catch(e){ return ''; } })();
  location.href = '/wave' + (sid ? ('?sid=' + encodeURIComponent(sid)) : '');
};
/* ---------------- 波次记录：独立页面 /wave-records ---------------- */
const _btnWaveRec = $('btnWaveRec');
if(_btnWaveRec) _btnWaveRec.onclick = () => {
  const sid = (function(){ try { return localStorage.getItem('km_sid') || ''; } catch(e){ return ''; } })();
  location.href = '/wave-records' + (sid ? ('?sid=' + encodeURIComponent(sid)) : '');
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
          --mac-line:rgba(60,60,67,.12); --mac-fill:rgba(120,120,128,.12); --mac-glass:#e0e5ec; }
  html { -webkit-text-size-adjust:100%; }
  body { font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
         letter-spacing:-.01em; -webkit-font-smoothing:antialiased; color:var(--mac-ink);
         background:#e0e5ec; min-height:100vh; }
  h1 { font-size:24px; font-weight:700; color:var(--mac-ink); letter-spacing:-.02em; margin:2px 2px 12px; }
  .card { background:var(--mac-glass); backdrop-filter:saturate(180%) blur(20px);
          -webkit-backdrop-filter:saturate(180%) blur(20px); border:0;
          border-radius:18px; padding:14px; box-shadow:var(--neu-up); }
  input { background:rgba(255,255,255,.86); border:1px solid var(--mac-line); border-radius:12px;
          color:var(--mac-ink); padding:13px 14px; font-size:19px; }
  input:focus { outline:none; border-color:var(--mac-blue); box-shadow:0 0 0 3.5px rgba(0,122,255,.16); }
  button { font-family:inherit; font-weight:600; border-radius:12px; background:var(--mac-blue); color:#fff;
           box-shadow:0 1px 2px rgba(0,0,0,.10); transition:transform .08s ease, opacity .12s ease; }
  button.ghost { background:var(--mac-fill); color:var(--mac-blue); box-shadow:none; }
  button:active { transform:scale(.97); opacity:.9; }
  .muted { color:var(--mac-sub); }
  .pitem { background:var(--mac-glass); backdrop-filter:saturate(180%) blur(20px);
           -webkit-backdrop-filter:saturate(180%) blur(20px); border:0;
           border-radius:18px; padding:14px; box-shadow:var(--neu-up); }
  .pitem.done { background:rgba(52,199,89,.14); border-color:rgba(52,199,89,.35); }
  .pitem.short { background:rgba(255,59,48,.12); border-color:rgba(255,59,48,.32); }
  .pitem.one { border-width:1px; padding:20px; box-shadow:var(--neu-up); }
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
  .zones button:not(.ghost), .filters button:not(.ghost) { background:#007AFF; color:#fff;
           box-shadow:0 1px 3px rgba(0,0,0,.14); }
  .bar { background:var(--mac-glass); backdrop-filter:saturate(180%) blur(20px);
         -webkit-backdrop-filter:saturate(180%) blur(20px); border-top:1px solid var(--mac-line); }
  .row4 button { border-radius:10px; }
  @media (prefers-color-scheme: dark) {
    body { background:#262b36; color:#f2f2f7; }
    h1 { color:#f2f2f7; }
    .card, .pitem, .bar { background:#262b36; border-color:rgba(255,255,255,.08); }
    .pcode { color:#fff; }
    input { background:rgba(118,118,128,.24); border-color:rgba(255,255,255,.12); color:#f2f2f7; }
    .zones button, .filters button { color:#ebebf5; }
    .zones button:not(.ghost), .filters button:not(.ghost) { background:rgba(255,255,255,.18); color:#fff; }
  }
</style>
<style>
:root{--neu-up:8px 8px 18px rgba(163,177,198,.55),-8px -8px 18px rgba(255,255,255,.95);--neu-up-sm:4px 4px 10px rgba(163,177,198,.55),-4px -4px 10px rgba(255,255,255,.95);--neu-in:inset 5px 5px 10px rgba(163,177,198,.5),inset -5px -5px 10px rgba(255,255,255,.9);--neu-in-sm:inset 4px 4px 8px rgba(163,177,198,.5),inset -4px -4px 8px rgba(255,255,255,.9);}
input:not([type=checkbox]):not([type=radio]):not([type=range]),select,textarea{background:#e0e5ec!important;border:0!important;box-shadow:var(--neu-in)!important}
button{border:0;box-shadow:var(--neu-up-sm)}
button.ghost{background:#e0e5ec;box-shadow:var(--neu-up-sm)}
button:active{box-shadow:var(--neu-in-sm)}
@media (prefers-color-scheme:dark){:root{--neu-up:8px 8px 18px rgba(8,10,16,.6),-8px -8px 18px rgba(255,255,255,.06);--neu-up-sm:4px 4px 10px rgba(8,10,16,.6),-4px -4px 10px rgba(255,255,255,.06);--neu-in:inset 5px 5px 10px rgba(8,10,16,.6),inset -5px -5px 10px rgba(255,255,255,.05);--neu-in-sm:inset 4px 4px 8px rgba(8,10,16,.6),inset -4px -4px 8px rgba(255,255,255,.05)}input:not([type=checkbox]):not([type=radio]):not([type=range]),select,textarea{background:#262b36!important}button.ghost{background:#262b36}}
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
          --line:rgba(60,60,67,.12); --fill:rgba(120,120,128,.12); --glass:#e0e5ec; }
  body { margin:0; padding:12px; min-height:100vh; color:var(--ink);
         font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
         letter-spacing:-.01em; -webkit-font-smoothing:antialiased;
         background:#e0e5ec; }
  .card { background:var(--glass); backdrop-filter:saturate(180%) blur(20px);
          -webkit-backdrop-filter:saturate(180%) blur(20px); border:0;
          border-radius:14px; padding:12px; margin-bottom:10px; box-shadow:var(--neu-up); }
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
    body { background:#262b36; color:#f2f2f7; }
    .card { background:#262b36; border-color:rgba(255,255,255,.08); }
    .kv b, .s, .muted, .total { color:#a1a1a6; }
    h2 { color:#f2f2f7; }
    .bar input { background:rgba(118,118,128,.24); border-color:rgba(255,255,255,.12); color:#f2f2f7; }
  }
</style>
<style>
:root{--neu-up:8px 8px 18px rgba(163,177,198,.55),-8px -8px 18px rgba(255,255,255,.95);--neu-up-sm:4px 4px 10px rgba(163,177,198,.55),-4px -4px 10px rgba(255,255,255,.95);--neu-in:inset 5px 5px 10px rgba(163,177,198,.5),inset -5px -5px 10px rgba(255,255,255,.9);--neu-in-sm:inset 4px 4px 8px rgba(163,177,198,.5),inset -4px -4px 8px rgba(255,255,255,.9);}
input:not([type=checkbox]):not([type=radio]):not([type=range]),select,textarea{background:#e0e5ec!important;border:0!important;box-shadow:var(--neu-in)!important}
button{border:0;box-shadow:var(--neu-up-sm)}
button.ghost{background:#e0e5ec;box-shadow:var(--neu-up-sm)}
button:active{box-shadow:var(--neu-in-sm)}
@media (prefers-color-scheme:dark){:root{--neu-up:8px 8px 18px rgba(8,10,16,.6),-8px -8px 18px rgba(255,255,255,.06);--neu-up-sm:4px 4px 10px rgba(8,10,16,.6),-4px -4px 10px rgba(255,255,255,.06);--neu-in:inset 5px 5px 10px rgba(8,10,16,.6),inset -5px -5px 10px rgba(255,255,255,.05);--neu-in-sm:inset 4px 4px 8px rgba(8,10,16,.6),inset -4px -4px 8px rgba(255,255,255,.05)}input:not([type=checkbox]):not([type=radio]):not([type=range]),select,textarea{background:#262b36!important}button.ghost{background:#262b36}}
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
  :root { --bg:#e0e5ec; --card:#e0e5ec; --sub:#6b7280; --line:rgba(60,60,67,.10); }
  * { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
  body { margin:0; padding:10px 10px 40px; background:var(--bg); color:#111;
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif; }
  header { display:flex; align-items:baseline; gap:8px; padding:2px 3px 8px; }
  header b { font-size:17px; }
  .top { position:sticky; top:0; z-index:9; background:#e0e5ec; box-shadow:var(--neu-up);
         backdrop-filter:saturate(180%) blur(14px); border-radius:14px; padding:10px;
         display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
  input[type=text] { flex:1 1 130px; min-width:110px; padding:11px 12px; font-size:17px;
         border:1px solid #d7dbe0; border-radius:10px; }
  button { padding:11px 14px; font-size:15px; font-weight:700; border:0; border-radius:10px;
           background:#0b5394; color:#fff; }
  button.g { background:#e8eef5; color:#0b5394; }
  .sum { font-size:13px; color:var(--sub); margin:9px 3px; }
  .flash { font-size:13px; color:#1B7F35; font-weight:700; margin:0 3px 6px; min-height:18px; }
  .card { background:var(--card); border-radius:14px; padding:4px 12px; margin-top:8px; box-shadow:var(--neu-up); }
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
<style>
:root{--neu-up:8px 8px 18px rgba(163,177,198,.55),-8px -8px 18px rgba(255,255,255,.95);--neu-up-sm:4px 4px 10px rgba(163,177,198,.55),-4px -4px 10px rgba(255,255,255,.95);--neu-in:inset 5px 5px 10px rgba(163,177,198,.5),inset -5px -5px 10px rgba(255,255,255,.9);--neu-in-sm:inset 4px 4px 8px rgba(163,177,198,.5),inset -4px -4px 8px rgba(255,255,255,.9);}
input:not([type=checkbox]):not([type=radio]):not([type=range]),select,textarea{background:#e0e5ec!important;border:0!important;box-shadow:var(--neu-in)!important}
button{border:0;box-shadow:var(--neu-up-sm)}
button.ghost{background:#e0e5ec;box-shadow:var(--neu-up-sm)}
button:active{box-shadow:var(--neu-in-sm)}
@media (prefers-color-scheme:dark){:root{--neu-up:8px 8px 18px rgba(8,10,16,.6),-8px -8px 18px rgba(255,255,255,.06);--neu-up-sm:4px 4px 10px rgba(8,10,16,.6),-4px -4px 10px rgba(255,255,255,.06);--neu-in:inset 5px 5px 10px rgba(8,10,16,.6),inset -5px -5px 10px rgba(255,255,255,.05);--neu-in-sm:inset 4px 4px 8px rgba(8,10,16,.6),inset -4px -4px 8px rgba(255,255,255,.05)}input:not([type=checkbox]):not([type=radio]):not([type=range]),select,textarea{background:#262b36!important}button.ghost{background:#262b36}}
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
  HIDDEN = {};   /* 拉取全量数据 → 恢复显示（只保留本次生成后的临时隐藏） */
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
          --line:rgba(60,60,67,.12); --fill:rgba(120,120,128,.12); --glass:#e0e5ec; }
  body { margin:0; padding:12px; min-height:100vh; color:var(--ink);
         font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
         letter-spacing:-.01em; -webkit-font-smoothing:antialiased;
         background:#e0e5ec; }
  .card { background:var(--glass); backdrop-filter:saturate(180%) blur(20px);
          -webkit-backdrop-filter:saturate(180%) blur(20px); border:0;
          border-radius:14px; padding:12px; margin-bottom:10px; box-shadow:var(--neu-up); }
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
    body { background:#262b36; color:#f2f2f7; }
    .card { background:#262b36; border-color:rgba(255,255,255,.08); }
    .muted, .num, .sub, .legend { color:#a1a1a6; }
    .num b { color:#f2f2f7; }
    .bar input, .ctl select { background:rgba(118,118,128,.24); border-color:rgba(255,255,255,.12); color:#f2f2f7; }
  }
</style>
<style>
:root{--neu-up:8px 8px 18px rgba(163,177,198,.55),-8px -8px 18px rgba(255,255,255,.95);--neu-up-sm:4px 4px 10px rgba(163,177,198,.55),-4px -4px 10px rgba(255,255,255,.95);--neu-in:inset 5px 5px 10px rgba(163,177,198,.5),inset -5px -5px 10px rgba(255,255,255,.9);--neu-in-sm:inset 4px 4px 8px rgba(163,177,198,.5),inset -4px -4px 8px rgba(255,255,255,.9);}
input:not([type=checkbox]):not([type=radio]):not([type=range]),select,textarea{background:#e0e5ec!important;border:0!important;box-shadow:var(--neu-in)!important}
button{border:0;box-shadow:var(--neu-up-sm)}
button.ghost{background:#e0e5ec;box-shadow:var(--neu-up-sm)}
button:active{box-shadow:var(--neu-in-sm)}
@media (prefers-color-scheme:dark){:root{--neu-up:8px 8px 18px rgba(8,10,16,.6),-8px -8px 18px rgba(255,255,255,.06);--neu-up-sm:4px 4px 10px rgba(8,10,16,.6),-4px -4px 10px rgba(255,255,255,.06);--neu-in:inset 5px 5px 10px rgba(8,10,16,.6),inset -5px -5px 10px rgba(255,255,255,.05);--neu-in-sm:inset 4px 4px 8px rgba(8,10,16,.6),inset -4px -4px 8px rgba(255,255,255,.05)}input:not([type=checkbox]):not([type=radio]):not([type=range]),select,textarea{background:#262b36!important}button.ghost{background:#262b36}}
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
  <div id="wbar"></div>
  <div class="rec" id="rec"></div>
</div>
<div class="card" id="list" style="max-height:66vh; overflow:auto"></div>

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
/* ---- 最近生成的波次（可一次两个：中通 + 申通）：常驻显示，各自一键拣完 ---- */
const WKEY = 'km_stock_lastwave';
let HIDDEN = {};   /* 生成过波次的编码：先藏起来；**下次拉取全量数据即恢复**
                      （货发走后订单变少，靠"从多到少"的排序自然沉底，不必永久隐藏） */
function markWaved(code){ if(code){ HIDDEN[String(code).toUpperCase()] = 1; } }
function normWbar(v){
  if(!v) return [];
  if(Array.isArray(v)) return v.filter(function(x){ return x && x.wave_code; });
  if(v.wave_code) return [v];
  return [];
}
function loadWbar(){
  let v = null;
  try{ v = JSON.parse(localStorage.getItem(WKEY) || 'null'); }catch(e){ v = null; }
  renderWbar(normWbar(v));
}
function saveWbar(list){
  const arr = normWbar(list);
  try{ localStorage.setItem(WKEY, JSON.stringify(arr.length ? arr : null)); }catch(e){}
  renderWbar(arr);
}
function renderWbar(list){
  const el = $('wbar'); if(!el) return;
  const arr = normWbar(list);
  if(!arr.length){ el.style.display = 'none'; el.innerHTML = ''; return; }
  el.style.display = '';
  let h = '<div class="card" style="border-left:4px solid #0b5394">'
        + '<div style="font-size:15px;font-weight:800">最近生成（' + arr.length + ' 个波次）</div>';
  arr.forEach(function(w, i){
    h += '<div style="margin-top:8px;padding-top:8px' + (i ? ';border-top:1px solid rgba(60,60,67,.12)' : '') + '">'
       + '<div style="font-size:16px;font-weight:800">波次 <span style="color:#0b5394">' + esc(w.wave_code) + '</span>　'
       + esc(w.carrier || '') + ' ' + esc(w.qty == null ? '' : w.qty) + ' 件'
       + (w.code ? ('　（' + esc(w.code) + '）') : '')
       + (w.done ? '　<span class="tag ok">已拣完</span>' : '') + '</div>'
       + '<div style="margin-top:6px">'
       + ((w.wave_id && !w.done) ? ('<button class="sbtn wbar-fin" data-i="' + i + '">一键拣完</button>') : '')
       + '</div></div>';
  });
  h += '<div style="margin-top:8px"><button class="sbtn" id="wbarClear">清除</button></div>'
     + '<div class="muted" style="margin-top:6px">生成新波次时会替换这里；「一键拣完」先只读预览、确认后才提交（不可撤销）。</div></div>';
  el.innerHTML = h;
  el.querySelectorAll('.sbtn.wbar-fin').forEach(function(b){
    b.onclick = function(){ wbarFinish(arr[+b.dataset.i], b); };
  });
  const cb = $('wbarClear');
  if(cb){ cb.onclick = function(){ saveWbar([]); }; }
}
function wbarFinish(w, b){
  if(!w || !w.wave_id){ flash('这个波次没有 id，请到「波次记录」页一键拣完'); return; }
  const restore = function(){ if(b){ b.disabled = false; b.textContent = '一键拣完'; } };
  if(b){ b.disabled = true; b.textContent = '只读预览中…'; }
  fetch(withSid('/api/wave/finish'), {method:'POST', cache:'no-store',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({wave_id: w.wave_id, confirm: false})})
    .then(function(r){ return r.json(); })
    .then(function(d){
      if(d && d.error){ throw new Error(d.error); }
      const n = (d && (d.item_count != null ? d.item_count
                       : (d.count != null ? d.count : (d.items && d.items.length) || '?'))) || '?';
      if(!confirm('一键拣完 · 只读预览（尚未提交）\n波次 ' + w.wave_code + '（' + (w.carrier || '') + ' '
                  + (w.qty || '') + ' 件）\n分拣明细：' + n
                  + '\n\n确认提交？会把该波次标记为「拣选完成」（不可撤销）。')){ restore(); return; }
      if(b){ b.textContent = '提交中（手动拣选）…'; }
      return fetch(withSid('/api/wave/finish'), {method:'POST', cache:'no-store',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({wave_id: w.wave_id, confirm: true})})
        .then(function(r){ return r.json(); })
        .then(function(j){
          if(j && (j.ok || j.finished || j.status_cn)){
            flash('波次 ' + w.wave_code + ' 已一键拣完（' + (w.carrier || '') + '）');
            let arr = [];
            try{ arr = normWbar(JSON.parse(localStorage.getItem(WKEY) || 'null')); }catch(e){ arr = []; }
            arr.forEach(function(x){ if(String(x.wave_code) === String(w.wave_code)) x.done = 1; });
            const still = arr.some(function(x){ return x.code && String(x.code) === String(w.code) && !x.done; });
            if(w.code && !still){ HIDDEN[String(w.code).toUpperCase()] = 1; }
            saveWbar(arr);
            render();
          } else {
            flash('一键拣完失败：' + ((j && (j.error || j.msg)) || '未知'));
            restore();
          }
        });
    })
    .catch(function(e){ flash('一键拣完出错：' + e.message); restore(); });
}
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
  const vis = ROWS.filter(function(r){ return !(HIDE_SENT && r.sent) && !r.waved && !HIDDEN[String(r.c).toUpperCase()]; });
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
      
      + (CAN('wave.create') ? ('<button class="sbtn wave" data-w="' + esc(r.c) + '">生成波次</button>') : '')
      + (CAN('stock.edit') ? ('<button class="sbtn adj" data-c="' + esc(r.c) + '">改库存</button>') : '')
      + (CAN('stock.zero') ? ('<button class="sbtn zero" data-c="' + esc(r.c) + '">盘0</button>') : '')
      + '</div></div>';
  }).join('') + (vis.length > head.length
      ? ('<div class="muted">只显示前 ' + head.length + ' 条，其余 ' + (vis.length - head.length) + ' 条请用「导出 Excel」或加关键词。</div>') : '');
   /* 「生成波次」：先**实时查快麦订单**（/api/wave/lookup，实时查 ERP，不是本地缓存），
     再把 中通/申通 各自的可生成件数摆成按钮让用户点选；选完才真的成波。
     成波走与「生成波次」页完全同一套接口/校验：一单一件口径、货位库存预检、成波排队锁、波次号回读。 */
  box.querySelectorAll('.sbtn.wave').forEach(function(b){
    b.onclick = function(){
      const code = b.dataset.w;
      const row = ROWS.filter(function(r){ return r.c === code; })[0] || {};
      const f = parseInt(row.f, 10) || 0;
      if(f <= 0){ flash(code + '：可发 ' + f + ' 件，没有可成波的「一单一件」'); return; }
      const cell = b.parentNode;
      b.disabled = true; b.textContent = '查询中…';
      fetch(withSid('/api/wave/lookup?code=' + encodeURIComponent(code)), {cache:'no-store'})
        .then(function(r){ return r.json(); })
        .then(function(d){
          if(d && d.error){ throw new Error(d.error); }
          const per = (d && d.carriers) || {};
          let keys = ['中通', '申通'].filter(function(k){ return per[k] != null; });
          if(!keys.length){ keys = Object.keys(per); }
          if(!keys.length){ flash(code + '：没有可成波订单（可能已生成波次 / 已打印 / 是多件单）'); render(); return; }
          let h = '';
          keys.forEach(function(k){
            const n = parseInt(per[k], 10) || 0;
            const q = Math.min(f, n);
            h += '<input class="qin" data-k="' + esc(k) + '" type="number" min="1" max="' + (n > 0 ? q : 1)
               + '" value="' + (n > 0 ? q : 1) + '" style="width:56px;margin-left:6px" title="要生成多少件（最多 '
               + q + ' 件）">'
               + '<button class="sbtn wave-go" data-k="' + esc(k) + '" data-q="' + (n > 0 ? q : 0) + '"'
               + (n > 0 ? '' : ' disabled') + '>' + esc(k) + ' ' + (n > 0 ? (q + ' 件') : '0') + '</button>';
          });
          const _pos = keys.filter(function(k){ return (parseInt(per[k], 10) || 0) > 0; });
          if(_pos.length > 1){
            h += '<button class="sbtn wave-go2">两个都生成（' + _pos.join(' + ') + '）</button>';
          }
          h += '<button class="sbtn wave-cancel">取消</button>';
          cell.innerHTML = h;
          cell.querySelectorAll('.sbtn.wave-go').forEach(function(g){
            g.onclick = function(){ waveGo(g, code, f); };
          });
          cell.querySelectorAll('.sbtn.wave-go2').forEach(function(g){
            g.onclick = function(){ waveGoBoth(cell, code, f, per, keys); };
          });
          const cb = cell.querySelector('.sbtn.wave-cancel');
          if(cb){ cb.onclick = function(){ render(); }; }
        })
        .catch(function(e){ flash('✗ ' + code + '：' + e.message); render(); });
    };
  });

  /* 选好快递后：真正成波（实时查到的订单；件数 = min(可发, 该快递可生成)） */
  function waveGo(g, code, f){
    const carrier = g.dataset.k;
    const _maxQ = parseInt(g.dataset.q, 10) || 0;
    let qty = _maxQ;
    const _inp = g.parentNode ? g.parentNode.querySelector('input.qin[data-k="' + (g.dataset.k || '') + '"]') : null;
    if(_inp){ const _v = parseInt(_inp.value, 10) || 0; if(_v > 0) qty = _v; }
    if(_maxQ > 0 && qty > _maxQ) qty = _maxQ;
    if(qty <= 0){ flash(code + '：' + carrier + ' 没有可成波订单'); return; }
    const cell = g.parentNode;
    cell.innerHTML = '<span class="muted">生成中…（' + esc(carrier) + ' ' + qty + ' 件）</span>';
    fetch(withSid('/api/wave/create'), {method:'POST', cache:'no-store',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({items:[{code:code, qty:qty}], carrier:carrier, confirm:true})})
      .then(function(r){ return r.json(); })
      .then(function(w){
        if(w && (w.wave_code || w.created)){
          markWaved(code);
          saveWbar([{wave_code: w.wave_code || '', wave_id: w.wave_id || '',
                    carrier: carrier, qty: ((w.codes && w.codes[0] && w.codes[0].actual) || qty),
                    code: code, ts: Date.now()}]);
          /* ★ 成波后刷新这个编码的可生成数：立刻减掉实际件数，再以 ERP 实时值为准。
             （以前不刷新 → 再扫同一个编码还是显示成波前的旧数字，用户反馈过） */
          try{
            const _imp = {};
            _imp[code] = ((w.codes && w.codes[0] && w.codes[0].actual) || qty);
            refreshMaxForCodes([code], _imp);
          }catch(e){}
          flash('✅ ' + code + ' 波次 ' + (w.wave_code || '?') + '（' + carrier + ' ' + ((w.codes && w.codes[0] && w.codes[0].actual) || qty) + ' 件）' + (w.capped_note ? '　' + w.capped_note : ''));
        } else {
          flash('✗ ' + code + '：' + ((w && (w.error || w.verify_error)) || '未生成（详情见「生成波次」页）'));
        }
        render();
      })
      .catch(function(e){ flash('✗ ' + code + '：' + e.message); render(); });
  }
  /* 一次把两个快递都成波：中通一个波次 + 申通一个波次（顺序执行，避免并发冲突） */
  function waveGoBoth(cell, code, f, per, keys){
    const todo = keys.filter(function(k){ return (parseInt(per[k], 10) || 0) > 0; })
                     .map(function(k){
                       const _max = Math.min(f, parseInt(per[k], 10) || 0);
                       const _inp = cell.querySelector('input.qin[data-k="' + k + '"]');
                       let _q = _inp ? (parseInt(_inp.value, 10) || 0) : _max;
                       if(_q <= 0 || _q > _max) _q = _max;
                       return {carrier: k, qty: _q};
                     });
    if(!todo.length){ flash(code + '：没有可成波订单'); return; }
    cell.innerHTML = '<span class="muted">生成中…（' + todo.map(function(t){ return esc(t.carrier); }).join(' + ') + '）</span>';
    const out = [];
    let chain = Promise.resolve();
    todo.forEach(function(t){
      chain = chain.then(function(){
        return fetch(withSid('/api/wave/create'), {method:'POST', cache:'no-store',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({items:[{code:code, qty:t.qty}], carrier:t.carrier, confirm:true})})
          .then(function(r){ return r.json(); })
          .then(function(w){ out.push({carrier: t.carrier, qty: t.qty, w: w || {}}); })
          .catch(function(e){ out.push({carrier: t.carrier, qty: t.qty, w: {error: e.message}}); });
      });
    });
    chain.then(function(){
      const ws = [], parts = [];
      out.forEach(function(o){
        const w = o.w || {};
        if(w.wave_code || w.created){
          const act = ((w.codes && w.codes[0] && w.codes[0].actual) || o.qty);
          ws.push({wave_code: w.wave_code || '', wave_id: w.wave_id || '', carrier: o.carrier,
                   qty: act, code: code});
          parts.push((w.wave_code ? ('波次 ' + w.wave_code) : '已生成') + '（' + o.carrier + ' ' + act + ' 件）');
        } else {
          parts.push(o.carrier + ' 失败：' + ((w.error || w.verify_error) || '未生成'));
        }
      });
      if(ws.length){ markWaved(code); saveWbar(ws); }
      /* ★ 成波后刷新这个编码的「最大可生成」：立刻减掉实际成波件数，再以 ERP 为准 */
      try{
        const imp = {};
        out.forEach(function(o){
          const w = o.w || {};
          if(w.wave_code || w.created){
            imp[code] = (imp[code] || 0) + (((w.codes && w.codes[0] && w.codes[0].actual)) || o.qty);
          }
        });
        if(Object.keys(imp).length) refreshMaxForCodes([code], imp);
      }catch(e){}
      flash(code + '：' + parts.join('　'));
      render();
    });
  }
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
loadWbar();                    /* 进页面先显示上次生成的波次号（常驻，直到生成新的） */
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
          --line:rgba(60,60,67,.12); --fill:rgba(120,120,128,.10); --glass:#e0e5ec; }
  body { margin:0; padding:12px 12px 96px; color:var(--ink);
         font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
         letter-spacing:-.01em; -webkit-font-smoothing:antialiased; font-size:16px;
         background:#e0e5ec; }
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
          -webkit-backdrop-filter:saturate(180%) blur(20px); border:0;
          border-radius:14px; padding:6px 12px; box-shadow:var(--neu-up); margin-bottom:12px; }
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
         background:#e0e5ec; backdrop-filter:saturate(180%) blur(20px);
         -webkit-backdrop-filter:saturate(180%) blur(20px); border-top:1px solid var(--line); }
  .bar button { flex:1; padding:14px 8px; font-size:16px; font-weight:700; border:0; border-radius:12px;
         background:var(--blue); color:#fff; font-family:inherit; }
  .bar button.g { flex:0 0 auto; padding:14px 12px; background:var(--fill); color:var(--blue); font-size:14.5px; }
  .bar button:disabled { opacity:.5; }
  @media (prefers-color-scheme: dark) {
    body { background:#262b36; color:#f2f2f7; }
    .card, .chip { background:#262b36; border-color:rgba(255,255,255,.08); }
    .chip.on { background:var(--blue); }
    .bar { background:#262b36; border-top-color:rgba(255,255,255,.08); }
    .sw i { background:rgba(120,120,128,.28); }
  }
</style>
<style>
:root{--neu-up:8px 8px 18px rgba(163,177,198,.55),-8px -8px 18px rgba(255,255,255,.95);--neu-up-sm:4px 4px 10px rgba(163,177,198,.55),-4px -4px 10px rgba(255,255,255,.95);--neu-in:inset 5px 5px 10px rgba(163,177,198,.5),inset -5px -5px 10px rgba(255,255,255,.9);--neu-in-sm:inset 4px 4px 8px rgba(163,177,198,.5),inset -4px -4px 8px rgba(255,255,255,.9);}
input:not([type=checkbox]):not([type=radio]):not([type=range]),select,textarea{background:#e0e5ec!important;border:0!important;box-shadow:var(--neu-in)!important}
button{border:0;box-shadow:var(--neu-up-sm)}
button.ghost{background:#e0e5ec;box-shadow:var(--neu-up-sm)}
button:active{box-shadow:var(--neu-in-sm)}
@media (prefers-color-scheme:dark){:root{--neu-up:8px 8px 18px rgba(8,10,16,.6),-8px -8px 18px rgba(255,255,255,.06);--neu-up-sm:4px 4px 10px rgba(8,10,16,.6),-4px -4px 10px rgba(255,255,255,.06);--neu-in:inset 5px 5px 10px rgba(8,10,16,.6),inset -5px -5px 10px rgba(255,255,255,.05);--neu-in-sm:inset 4px 4px 8px rgba(8,10,16,.6),inset -4px -4px 8px rgba(255,255,255,.05)}input:not([type=checkbox]):not([type=radio]):not([type=range]),select,textarea{background:#262b36!important}button.ghost{background:#262b36}}
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
          --line:rgba(60,60,67,.12); --fill:rgba(120,120,128,.12); --glass:#e0e5ec; }
  body { margin:0; padding:12px; min-height:100vh; color:var(--ink); letter-spacing:-.01em;
         -webkit-font-smoothing:antialiased;
         font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
         background:#e0e5ec; }
  header { display:flex; align-items:center; gap:8px; padding:2px 3px 10px; }
  header b { font-size:17px; }
  header .sp { flex:1; }
  header a.home { color:var(--blue); text-decoration:none; font-size:13.5px; font-weight:600;
                  background:var(--fill); border-radius:9px; padding:5px 11px; white-space:nowrap; }
  .card { background:var(--glass); backdrop-filter:saturate(180%) blur(20px);
          -webkit-backdrop-filter:saturate(180%) blur(20px); border:0;
          border-radius:14px; padding:12px; margin-bottom:10px; box-shadow:var(--neu-up); }
  .sums { display:flex; gap:8px; margin-bottom:10px; }
  .sum { flex:1 1 0; min-width:0; text-align:center; padding:11px 4px; border-radius:14px;
         background:var(--glass); backdrop-filter:saturate(180%) blur(20px);
         -webkit-backdrop-filter:saturate(180%) blur(20px); border:0;
         box-shadow:var(--neu-up); }
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
    body { background:#262b36; color:#f2f2f7; }
    .card, .sum { background:#262b36; border-color:rgba(255,255,255,.08); }
    .muted, td.msg { color:#a1a1a6; }
    .legend b { color:#f2f2f7; }
    .sum.run b { color:#5aa9ff; } .sum.wait b { color:#ffb340; } .sum.fail b { color:#ff6b62; }
    .sum.ok b { color:#4cd964; }
    th, td { border-bottom-color:rgba(255,255,255,.08); }
  }
</style>
<style>
:root{--neu-up:8px 8px 18px rgba(163,177,198,.55),-8px -8px 18px rgba(255,255,255,.95);--neu-up-sm:4px 4px 10px rgba(163,177,198,.55),-4px -4px 10px rgba(255,255,255,.95);--neu-in:inset 5px 5px 10px rgba(163,177,198,.5),inset -5px -5px 10px rgba(255,255,255,.9);--neu-in-sm:inset 4px 4px 8px rgba(163,177,198,.5),inset -4px -4px 8px rgba(255,255,255,.9);}
input:not([type=checkbox]):not([type=radio]):not([type=range]),select,textarea{background:#e0e5ec!important;border:0!important;box-shadow:var(--neu-in)!important}
button{border:0;box-shadow:var(--neu-up-sm)}
button.ghost{background:#e0e5ec;box-shadow:var(--neu-up-sm)}
button:active{box-shadow:var(--neu-in-sm)}
@media (prefers-color-scheme:dark){:root{--neu-up:8px 8px 18px rgba(8,10,16,.6),-8px -8px 18px rgba(255,255,255,.06);--neu-up-sm:4px 4px 10px rgba(8,10,16,.6),-4px -4px 10px rgba(255,255,255,.06);--neu-in:inset 5px 5px 10px rgba(8,10,16,.6),inset -5px -5px 10px rgba(255,255,255,.05);--neu-in-sm:inset 4px 4px 8px rgba(8,10,16,.6),inset -4px -4px 8px rgba(255,255,255,.05)}input:not([type=checkbox]):not([type=radio]):not([type=range]),select,textarea{background:#262b36!important}button.ghost{background:#262b36}}
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

# ====================== 网页端：生成波次（扫编码 → 填写件数 → 一个波次） ======================
WAVE_HTML = r"""<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>生成波次 · 快麦</title>
<style>
  * { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
  :root { --blue:#007AFF; --green:#34C759; --red:#FF3B30; --ink:#1d1d1f; --sub:#6e6e73;
          --line:rgba(60,60,67,.12); --fill:rgba(120,120,128,.12); --glass:#e0e5ec; }
  body { margin:0; padding:12px; min-height:100vh; color:var(--ink);
         font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
         letter-spacing:-.01em; -webkit-font-smoothing:antialiased;
         background:#e0e5ec; }
  .card { background:var(--glass); backdrop-filter:saturate(180%) blur(20px);
          -webkit-backdrop-filter:saturate(180%) blur(20px); border:0;
          border-radius:14px; padding:12px; margin-bottom:10px; box-shadow:var(--neu-up); }
  .bar { display:flex; gap:8px; }
  .bar input { flex:1; min-width:0; padding:13px 14px; font-size:19px; color:var(--ink);
               background:rgba(255,255,255,.92); border:1px solid var(--line); border-radius:12px; }
  .bar input:focus { outline:none; border-color:var(--blue); box-shadow:0 0 0 3.5px rgba(0,122,255,.16); }
  .bar button { padding:13px 18px; font-size:16px; font-weight:600; border:0; border-radius:12px;
                background:var(--blue); color:#fff; box-shadow:0 1px 2px rgba(0,0,0,.10); }
  button { font-family:inherit; font-weight:600; border:0; border-radius:11px; padding:11px 16px;
           font-size:15px; background:var(--blue); color:#fff; box-shadow:0 1px 2px rgba(0,0,0,.10); }
  button.ghost { background:var(--fill); color:var(--blue); box-shadow:none; }
  button.del { background:rgba(255,59,48,.12); color:#C7362E; box-shadow:none; padding:8px 12px; font-size:13px; }
  button:active { transform:scale(.97); }
  button:disabled { opacity:.45; }
  .hidden { display:none !important; }
  .seg { flex:0 0 auto; }
  .seg.on { background:var(--blue); color:#fff; }
  h2 { font-size:15px; margin:0 0 8px; font-weight:700; color:var(--ink);
       border-left:3px solid var(--blue); padding-left:8px; }
  .muted { font-size:12.5px; color:var(--sub); line-height:1.7; }
  .rowitem { display:flex; align-items:center; gap:8px; padding:9px 0; border-top:1px solid rgba(60,60,67,.10); }
  .rowitem:first-child { border-top:0; }
  .rowitem .c { flex:1; min-width:0; }
  .rowitem .ccode { font-size:15px; font-weight:600; word-break:break-all; }
  .rowitem .cmax { font-size:12px; color:var(--sub); margin-top:2px; }
.qcode { font-size:17px; font-weight:800; letter-spacing:-.01em; }   /* 编码：加粗放大 */
.cex { color:#FF3B30; font-weight:800; }                            /* 各快递件数：红+粗 */
.mqw { font-weight:800; }                                           /* 多件预留：加粗 */
  .rowitem input { width:74px; padding:9px 10px; font-size:16px; text-align:center; color:var(--ink);
                   background:rgba(255,255,255,.92); border:1px solid var(--line); border-radius:10px; }
  .actions { display:flex; gap:8px; margin-top:12px; }
  .actions button { flex:1; padding:13px; font-size:16px; }
  /* 待成波清单「合计件数」：吸顶常驻 + 大红/大绿，直观看超没超 ERP 单波次上限 500 */
  .wtot { position:sticky; top:0; z-index:6;
          display:flex; align-items:center; justify-content:space-between; gap:12px;
          padding:12px 14px; border-radius:14px; margin:2px 0 10px;
          background:#e0e5ec; color:#7b8494; box-shadow:0 4px 12px rgba(163,177,198,.45); }
  .wtot.ok { background:#d8efdd; color:#1B7F35; }
  .wtot.over { background:#fadadd; color:#c62828;
               box-shadow:0 0 0 2px rgba(255,59,48,.55), 0 4px 12px rgba(163,177,198,.45); }
  .wtot-t { font-size:14px; font-weight:700; }
  .wtot-s { font-size:12px; opacity:.9; margin-top:3px; }
  .wtot-r { flex:0 0 auto; white-space:nowrap; line-height:1; }
  .wtot-r b { font-size:30px; font-weight:800; letter-spacing:-.03em; }
  .wtot-r i { font-size:14px; font-style:normal; font-weight:700; opacity:.7; margin-left:2px; }
  .wtot.over .wtot-r b { font-size:34px; }
  .tag { display:inline-block; font-size:12px; padding:2px 9px; border-radius:8px; background:var(--fill);
         color:var(--sub); margin:0 6px 4px 0; }
  .tag.warn { background:rgba(255,59,48,.15); color:#c62828; }
  .tag.ok { background:rgba(52,199,89,.18); color:#1B7F35; }
  .tag.red { background:#FF3B30; color:#fff; font-weight:800; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th,td { padding:6px 4px; border-bottom:1px solid rgba(60,60,67,.10); text-align:left; word-break:break-all; }
  th { color:var(--sub); font-weight:500; }
  .big { font-size:22px; font-weight:800; letter-spacing:-.02em; }
  .oktext { color:#1B7F35; }
  .badtext { color:#C7362E; }
  .topbar { display:flex; gap:8px; margin-bottom:10px; }
  .topbar a { flex:1; text-align:center; text-decoration:none; padding:10px 12px; border-radius:11px;
              font-size:14px; font-weight:600; background:var(--fill); color:var(--blue); }
  /* 配货明细：每个 SKU 一行（自动换行，不挤在一起） */
  .skus { margin-top:8px; }
  .skus .sku { display:flex; justify-content:space-between; align-items:baseline; gap:12px;
               padding:8px 0; border-top:1px solid rgba(60,60,67,.10); }
  .skus .sku:first-child { border-top:0; }
  .skus .skun { font-size:15px; font-weight:600; word-break:break-all; }
  .skus .skuq { flex:0 0 auto; font-size:15px; font-weight:700; color:var(--blue); white-space:nowrap; }
  @media (prefers-color-scheme: dark) {
    body { background:#262b36; color:#f2f2f7; }
    .card { background:#262b36; border-color:rgba(255,255,255,.08); }
    h2 { color:#f2f2f7; }
    .muted, .rowitem .cmax { color:#a1a1a6; }
    .wtot { background:#2b3140; color:#c9cfdd; }
    .wtot.ok { background:#1e3a28; color:#4cd964; }
    .wtot.over { background:#3d2226; color:#ff6b62; }
    .bar input, .rowitem input { background:rgba(118,118,128,.24); border-color:rgba(255,255,255,.12); color:#f2f2f7; }
  }
</style>
<style>
:root{--neu-up:8px 8px 18px rgba(163,177,198,.55),-8px -8px 18px rgba(255,255,255,.95);--neu-up-sm:4px 4px 10px rgba(163,177,198,.55),-4px -4px 10px rgba(255,255,255,.95);--neu-in:inset 5px 5px 10px rgba(163,177,198,.5),inset -5px -5px 10px rgba(255,255,255,.9);--neu-in-sm:inset 4px 4px 8px rgba(163,177,198,.5),inset -4px -4px 8px rgba(255,255,255,.9);}
input:not([type=checkbox]):not([type=radio]):not([type=range]),select,textarea{background:#e0e5ec!important;border:0!important;box-shadow:var(--neu-in)!important}
button{border:0;box-shadow:var(--neu-up-sm)}
button.ghost{background:#e0e5ec;box-shadow:var(--neu-up-sm)}
button:active{box-shadow:var(--neu-in-sm)}
@media (prefers-color-scheme:dark){:root{--neu-up:8px 8px 18px rgba(8,10,16,.6),-8px -8px 18px rgba(255,255,255,.06);--neu-up-sm:4px 4px 10px rgba(8,10,16,.6),-4px -4px 10px rgba(255,255,255,.06);--neu-in:inset 5px 5px 10px rgba(8,10,16,.6),inset -5px -5px 10px rgba(255,255,255,.05);--neu-in-sm:inset 4px 4px 8px rgba(8,10,16,.6),inset -4px -4px 8px rgba(255,255,255,.05)}input:not([type=checkbox]):not([type=radio]):not([type=range]),select,textarea{background:#262b36!important}button.ghost{background:#262b36}}
</style></head>
<body>
<div class="topbar">
  <a href="/" id="lnkHome">返回扫码</a>
  <a href="/wave-records" id="lnkRec">波次记录</a>
</div>
<div class="card">
  <h2>快递（一个波次只能同一种）</h2>
  <div class="bar" id="cbar">
    <button class="ghost seg on" data-car="中通">中通</button>
    <button class="ghost seg" data-car="申通">申通</button>
    <button class="ghost" id="modeBtn" style="font-size:13px;padding:9px 12px">双快递模式：开</button>
  </div>
  <div class="bar" style="margin-top:8px">
    <input id="code" type="text" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="扫/手动输入商家编码">
    <button id="btnCam" class="ghost">扫码添加</button>
  </div>
  <div class="muted" id="hint" style="margin-top:8px"></div>
  <div class="muted" id="shelfStat" style="margin-top:6px">货位库存：载入中…</div>
</div>
<div id="camBox" class="hidden" style="position:fixed;left:0;top:0;right:0;bottom:0;background:rgba(0,0,0,.72);z-index:999;display:flex;align-items:center;justify-content:center">
  <div style="background:#000;border-radius:14px;padding:10px;width:min(92vw,430px)">
    <video id="video" playsinline muted style="width:100%;border-radius:10px;background:#000"></video>
    <div class="muted" id="camMsg" style="color:#eee;margin-top:8px">对准条码…</div>
    <div class="bar" style="margin-top:8px"><button id="btnCamStop" class="ghost" style="flex:1">关闭</button></div>
  </div>
</div>
<div class="card">
  <h2>待成波清单 <span class="muted" id="cnt"></span></h2>
  <div class="wtot zero" id="wtot">
    <div class="wtot-l">
      <div class="wtot-t">本次波次合计（<span id="wtot-car">中通</span>）</div>
      <div class="wtot-s" id="wtot-note">单波次上限 500</div>
    </div>
    <div class="wtot-r"><b id="wtot-num">0</b><i>/500</i></div>
  </div>
  <div id="list"><div class="muted">还没有添加编码</div></div>
  <div class="actions">
    <button id="prev" class="ghost">预览（不建波）</button>
    <button id="mk" data-perm="wave.create">生成波次</button>
    
  </div>
</div>
<div class="card">
  <h2>一键拣完（对已生成的波次）</h2>
  <div class="bar" style="margin-top:8px">
    <input id="fwid" type="text" inputmode="numeric" autocomplete="off" placeholder="输入波次ID（波次号下方或记录页可查）">
    <button id="fwPrev" class="ghost" data-perm="wave.create">一键拣完</button>
  </div>
</div>
<div id="fwOut"></div>
<div id="out"></div>
<script src="/km/zxing.js?v=8"></script>
<script>
const $ = id => document.getElementById(id);
const esc = s => String(s==null?'':s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const SID = (function(){
  try { const q = new URLSearchParams(location.search).get('sid');
        if(q) localStorage.setItem('km_sid', q);
        return localStorage.getItem('km_sid') || ''; } catch(e){ return ''; }
})();
function withSid(u){ return SID ? (u + (u.indexOf('?') >= 0 ? '&' : '?') + 'sid=' + encodeURIComponent(SID)) : u; }
function bust(u){ return u + (u.indexOf('?') >= 0 ? '&' : '?') + 't=' + Date.now(); }   // 防缓存：每次都让 URL 不同
let BAGS = {'中通': [], '申通': []};   /* 两个快递各一份待成波清单（互不清空） */
let ITEMS = BAGS['中通'];              /* ITEMS 永远指向"当前正在看"的那份清单 */
let CARRIER = '中通';                  // 一个波次只能同一种快递（与服务端 kuaimai_wave.CARRIERS 一致）
const BAGKEY = 'km_wave_bags';

let DUAL = true;    /* true=双快递模式（两份清单）；false=单快递模式（旧：只进当前快递，切换清空） */
const MODEKEY = 'km_wave_dual';
function loadMode(){
  try{ const v = localStorage.getItem(MODEKEY); if(v === '0'){ DUAL = false; } else if(v === '1'){ DUAL = true; } }catch(e){}
  syncModeBtn();
}
function saveMode(){ try{ localStorage.setItem(MODEKEY, DUAL ? '1' : '0'); }catch(e){} syncModeBtn(); }
function syncModeBtn(){
  const b = $('modeBtn'); if(!b) return;
  b.textContent = DUAL ? '双快递模式：开' : '单快递模式（旧）';
  b.title = DUAL ? '扫码：中通进中通清单、申通进申通清单；切换只是换着看，刷新可保留（点一下切回旧模式）'
                 : '旧模式：扫码只进当前快递清单，切换快递会清空当前清单；刷新页面会保留（点一下切回双快递模式）';
  if(DUAL){ b.classList.add('on'); } else { b.classList.remove('on'); }
}
function toggleMode(){
  DUAL = !DUAL; saveMode();
  bagLog('toggle-mode', DUAL ? '→双快递' : '→单快递(旧)');
  if(!DUAL){
    /* 切回旧模式：只保留当前快递那份，其余丢弃（但照样存盘 → 刷新能恢复） */
    const keep = ITEMS.slice();
    BAGS = {'中通': [], '申通': []}; BAGS[CARRIER] = keep; ITEMS = bagOf(CARRIER);
    saveBags();
  } else {
    saveBags();
  }
  syncCarrierButtons(); render();
  $('hint').innerHTML = DUAL
    ? '已切到「双快递模式」：扫码时<b>中通进中通清单、申通进申通清单</b>；切换只是换着看，两边互不清空，刷新可保留。'
    : '已切回「单快递模式（旧）」：扫码只进<b>当前快递</b>清单；切换快递会清空当前清单，<b>刷新页面会保留</b>。';
}

function bagOf(c){ if(!BAGS[c]) BAGS[c] = []; return BAGS[c]; }
function bagCount(c){ return (BAGS[c] || []).length; }
function saveBags(){
  try{ localStorage.setItem(BAGKEY, JSON.stringify({bags: BAGS, carrier: CARRIER})); }catch(e){}
  /* 每份各存一份单独备份：万一哪次把某一份清了，恢复时还能按备份救回 */
  try{
    localStorage.setItem(BAGKEY + '_中通', JSON.stringify(BAGS['中通'] || []));
    localStorage.setItem(BAGKEY + '_申通', JSON.stringify(BAGS['申通'] || []));
  }catch(e){}
}
/* 清单变动埋点：写进服务端日志，方便查「某一份为什么没了」 */
function bagLog(ev, extra){
  try{
    fetch(bust(withSid('/api/wave/baglog')), {method:'POST', cache:'no-store',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ev:ev, carrier:CARRIER, dual:!!DUAL,
                            mid:bagCount('中通'), shen:bagCount('申通'), extra:String(extra||'')})}
    ).catch(function(){});
  }catch(e){}
}
function syncCarrierButtons(){
  document.querySelectorAll('#cbar .seg').forEach(function(b){
    const c = b.getAttribute('data-car');
    const n = bagCount(c);
    b.textContent = c + (n ? ('（' + n + '）') : '');
    b.classList.toggle('on', c === CARRIER);
  });
}
/* 从某快递清单里剔除已进波次的编码（只动这一份，另一份原样保留） */
function dropFromBag(carrier, p, items){
  try{
    const done = {};
    (p && p.codes || []).forEach(function(x){
      if((parseInt(x.actual, 10) || 0) > 0 && x.code){ done[String(x.code).toUpperCase()] = 1; }
    });
    if(!Object.keys(done).length){ (items || []).forEach(function(x){ done[String(x.code).toUpperCase()] = 1; }); }
    const others = {};
    Object.keys(BAGS).forEach(function(k){ if(k !== carrier){ others[k] = BAGS[k]; } });
    BAGS[carrier] = bagOf(carrier).filter(function(x){ return !done[String(x.code).toUpperCase()]; });
    Object.keys(others).forEach(function(k){ BAGS[k] = others[k]; });   /* 另一份原样保留（显式保证） */
    bagLog('drop', carrier + ' →' + bagOf(carrier).length + ' 码=' + Object.keys(done).join(','));
    /* 自愈：若另一份突然空了、但它的备份里还有，立刻按备份恢复（防丢第二道） */
    try{
      Object.keys(BAGS).forEach(function(k){
        if(k !== carrier && (BAGS[k] || []).length === 0){
          let bak = [];
          try{ bak = JSON.parse(localStorage.getItem(BAGKEY + '_' + k) || '[]') || []; }catch(e){ bak = []; }
          if(bak.length){ BAGS[k] = bak; bagLog('heal-from-backup', k + ' 恢复 ' + bak.length + ' 条'); }
        }
      });
      if(CARRIER !== carrier){ ITEMS = bagOf(CARRIER); }
    }catch(e){}
    if(carrier === CARRIER){ ITEMS = bagOf(CARRIER); }
  }catch(e){}
  saveBags(); syncCarrierButtons(); render();
}
/* 刷新/重开页面：有上次的清单就恢复，并给「保留 / 不保留」选择（避免丢数据） */
function restoreBags(){
  let v = null;
  try{ v = JSON.parse(localStorage.getItem(BAGKEY) || 'null'); }catch(e){ v = null; }
  if(!v || !v.bags) return;
  const n1 = (v.bags['中通'] || []).length, n2 = (v.bags['申通'] || []).length;
  if(!n1 && !n2) return;
  BAGS = {'中通': v.bags['中通'] || [], '申通': v.bags['申通'] || []};
  /* 防丢：与「每份单独备份」比对，谁多信谁（宁可多不可少） */
  try{
    ['中通', '申通'].forEach(function(k){
      let bak = [];
      try{ bak = JSON.parse(localStorage.getItem(BAGKEY + '_' + k) || '[]') || []; }catch(e){ bak = []; }
      if(bak.length > (BAGS[k] || []).length){ BAGS[k] = bak; }
    });
  }catch(e){}
  if(v.carrier === '中通' || v.carrier === '申通'){ CARRIER = v.carrier; }
  ITEMS = bagOf(CARRIER);
  syncCarrierButtons(); render();
  bagLog('restore', '中通 ' + n1 + ' 申通 ' + n2);
  $('hint').innerHTML = '已恢复上次的待成波清单（中通 ' + n1 + ' 个 · 申通 ' + n2 + ' 个）—— 要保留吗？ '
    + '<button class="ghost" id="keepBags" style="padding:6px 12px;font-size:14px">保留</button> '
    + '<button class="ghost" id="dropBags" style="padding:6px 12px;font-size:14px">不保留（清空）</button>';
  const kb = $('keepBags');
  if(kb){ kb.onclick = function(){ $('hint').innerHTML = '已保留上次清单（中通 ' + bagCount('中通') + ' 个 · 申通 ' + bagCount('申通') + ' 个）。'; }; }
  const dbb = $('dropBags');
  if(dbb){ dbb.onclick = function(){
    BAGS = {'中通': [], '申通': []}; ITEMS = bagOf(CARRIER); saveBags(); syncCarrierButtons(); render();
    $('hint').innerHTML = '已清空待成波清单。';
  }; }
}
function setCarrier(c){
  if(c === CARRIER) return;
  if(!DUAL){
    if(ITEMS.length && !confirm('切换快递会清空当前清单（一个波次只能同一种快递）。继续？')) return;
    bagLog('clear-on-switch', CARRIER + ' 旧模式切走时清空');
    BAGS[CARRIER] = [];                    /* 旧模式：切快递即清空当前那份 */
  }
  CARRIER = c; ITEMS = bagOf(c); saveBags(); render(); syncCarrierButtons();
  $('hint').innerHTML = DUAL
    ? ('当前快递：<b>' + esc(c) + '</b>（这份清单 ' + ITEMS.length + ' 个编码）。两个快递的清单各自保留，切换只是换着看。')
    : ('当前快递：<b>' + esc(c) + '</b>（单快递模式：扫码只进这份清单）。');
}

/* 在架数量 + 货位（本机索引；在架 0 也保留货位）+ 建议多件预留。
   o 可以是 API 响应（含 shelf_index_empty/shelf_qty/bins_text/multi_qty），
   也可以是清单项里存的 info 对象（字段同名）。 */
function shelfBits(o){
  o = o || {};
  const parts = [];
  if(o.shelf_index_empty){
    parts.push('货位索引为空（请先在主程序点「刷新货位库存」）');
  } else {
    const q = (o.shelf_qty == null) ? '-' : o.shelf_qty;
    const bt = o.bins_text ? esc(o.bins_text) : '无货位记录';
    parts.push('在架 <b>' + esc(q) + '</b> 件');
    parts.push('货位 ' + bt);
  }
  const mq = parseInt(o.multi_qty, 10) || 0;
  parts.push('建议多件预留 <b class="mqw">' + mq + '</b> 件');
  return parts.join('　·　');
}

/* ---- 货位库存"实时"：不同步拉全量；由服务端在超过 5 分钟/索引为空时后台刷一次，
       页面只读本机缓存并轮询状态。进页面即触发，刷完自动更新数字。 ---- */
let shelfPollTimer = null;
let shelfRetryTimer = null;
function shelfStatRender(d){
  const el = $('shelfStat'); if(!el) return;
  if(d && d.ok){
    el.innerHTML = esc(d.note || '货位库存：未知')
      + (d.codes ? '（' + d.codes + ' 个编码）' : '')
      + (d.refreshing ? '…' : '');
  } else {
    el.innerHTML = '<span class="muted">货位库存：暂时读不到状态（自动重试中…）</span>';
    if(!shelfRetryTimer){
      shelfRetryTimer = setTimeout(function(){ shelfRetryTimer = null; refreshShelfStatus(); }, 5000);
    }
  }
}
function pollShelfWhenFresh(d){
  if(shelfPollTimer){ clearTimeout(shelfPollTimer); shelfPollTimer = null; }
  if(!d || !d.refreshing) return;         /* 刷完就停，不空转 */
  shelfPollTimer = setTimeout(function(){ refreshShelfStatus(); loadShelfForItems(); }, 3000);
}
function refreshShelfStatus(){
  fetch(bust(withSid('/api/wave/shelf_status')), {cache:'no-store'})
    .then(function(r){ if(r.status === 401){ return null; } return r.json(); })
    .then(function(d){ if(d){ shelfStatRender(d); pollShelfWhenFresh(d); } })
    .catch(function(){});
}
function loadShelfForItems(){
  const codes = ITEMS.map(function(x){ return x.code; });
  if(!codes.length) return;
  fetch(bust(withSid('/api/wave/shelf?codes=' + encodeURIComponent(codes.join(',')))), {cache:'no-store'})
    .then(function(r){ if(r.status === 401){ return null; } return r.json(); })
    .then(function(d){
      if(!d || !d.items) return;
      ITEMS.forEach(function(it){
        const s = d.items[it.code];
        if(s && it.info){
          it.info.shelf_qty = s.shelf_qty;
          it.info.bins_text = s.bins_text;
          it.info.shelf_index_empty = s.shelf_index_empty;
        }
      });
      render();
    }).catch(function(){});
}

const WAVE_LIMIT = 500;   /* 快麦 ERP 单个波次的订单上限 */
/* 待成波清单「合计件数」：当前快递清单里所有 SKU 的数量相加（≈ 这一波要挑多少单/多少件） */
function updateTotal(){
  const wt = $('wtot'); if(!wt) return;
  let total = 0;
  ITEMS.forEach(function(x){ total += (parseInt(x.qty, 10) || 0); });
  const car = $('wtot-car'); if(car) car.textContent = CARRIER;
  const num = $('wtot-num'); if(num) num.textContent = total;
  const note = $('wtot-note');
  if(total > WAVE_LIMIT){
    wt.className = 'wtot over';
    if(note) note.textContent = '⚠ 已超上限 ' + (total - WAVE_LIMIT) + ' 件！请减少后再成波';
  } else if(total > 0){
    wt.className = 'wtot ok';
    if(note) note.textContent = '未超上限，还可加 ' + (WAVE_LIMIT - total) + ' 件';
  } else {
    wt.className = 'wtot zero';
    if(note) note.textContent = '单波次上限 ' + WAVE_LIMIT;
  }
}
function render(){
  $('cnt').textContent = (ITEMS.length ? ('共 ' + ITEMS.length + ' 个编码') : '')
    + (DUAL ? ('　｜　中通 ' + bagCount('中通') + ' 条 · 申通 ' + bagCount('申通') + ' 条') : '');
  updateTotal();
  if(!ITEMS.length){ $('list').innerHTML = '<div class="muted">还没有添加编码</div>'; return; }
  let h = '';
  ITEMS.forEach(function(it, i){
    h += '<div class="rowitem">'
       + '<div class="c"><div class="ccode">' + esc(it.code) + '</div>'
       + '<div class="cmax">最大可生成 ' + esc(it.max) + ' 件（' + esc(CARRIER) + '）</div></div>'
       + '<input type="number" min="0" value="' + esc(it.qty) + '" data-i="' + i + '">'
       + '<button class="del" data-d="' + i + '">删除</button></div>';
  });
  $('list').innerHTML = h;
  $('list').querySelectorAll('input[data-i]').forEach(function(el){
    el.onchange = function(){
      const i = +el.getAttribute('data-i');
      ITEMS[i].qty = Math.max(0, parseInt(el.value,10) || 0);
      updateTotal(); saveBags();
    };
  });
  $('list').querySelectorAll('button[data-d]').forEach(function(el){
    el.onclick = function(){ ITEMS.splice(+el.getAttribute('data-d'), 1); render(); };
  });
}

function addCode(code){
  code = (code || '').trim();
  if(!code){ $('hint').textContent = '请先输入商家编码'; return; }
  $('hint').textContent = '正在查 ' + code + ' 的最大可生成件数…';
  fetch(bust(withSid('/api/wave/lookup?code=' + encodeURIComponent(code))), {cache:'no-store'})
    .then(function(r){ if(r.status === 401){ location.href = '/login'; throw new Error('请重新登录'); } return r.json(); })
    .then(function(d){
      if(d.error){ $('hint').innerHTML = '<span class="badtext">' + esc(d.error) + '</span>'; return; }
      refreshShelfStatus();
      const per = d.carriers || {};
      const all = Object.keys(per).map(function(k){ return k + ' ' + per[k] + ' 件'; }).join('　/　');
      const mq = parseInt(d.multi_qty, 10) || 0;
      const info = {shelf_index_empty: !!d.shelf_index_empty, shelf_qty: d.shelf_qty,
                    bins_text: d.bins_text || '', multi_qty: mq};
      const extra = '<div class="muted" style="margin-top:6px;line-height:1.7">' + shelfBits(d) + '</div>';
      /* 旧模式（单快递）：只处理当前快递，没有就提示可切到另一个快递 */
      if(!DUAL){
        const cnum = parseInt(per[CARRIER], 10) || 0;
        const cname0 = String(d.code || code).toUpperCase();
        if(cnum > 0){
          if(ITEMS.some(function(x){ return String(x.code).toUpperCase() === cname0; })){
            $('hint').innerHTML = esc(d.code || code) + ' 已在清单里' + extra; return;
          }
          ITEMS.push({code: d.code || code, qty: cnum, max: cnum, info: info});
          saveBags(); render(); syncCarrierButtons();
          $('hint').innerHTML = '<span class="qcode">' + esc(d.code || code) + '</span>：快递 <b>' + esc(CARRIER)
            + '</b> 最大可生成 <b>' + cnum + ' 件</b>'
            + (all ? '（全部：<span class="cex">' + esc(all) + '</span>）' : '') + extra;
          return;
        }
        const oth = Object.keys(per).filter(function(k){
          return k !== CARRIER && (parseInt(per[k], 10) || 0) > 0;
        });
        if(oth.length){
          const o = oth[0], n0 = parseInt(per[o], 10) || 0;
          $('hint').innerHTML = '<span class="badtext">' + esc(d.code || code) + '：快递 <b>' + esc(CARRIER)
            + '</b> 没有可成波订单</span>，但 <b>' + esc(o) + '</b> 有 <b>' + n0 + '</b> 件 — '
            + '<button class="ghost" id="swBtn" style="padding:7px 12px;font-size:14px">切到 '
            + esc(o) + ' 并添加</button>' + extra;
          const b = $('swBtn');
          if(b){ b.onclick = function(){ setCarrier(o); setTimeout(function(){ addCode(d.code || code); }, 80); }; }
          return;
        }
        $('hint').innerHTML = '<span class="badtext">' + esc(d.code || code) + '：没有可成波订单</span>'
          + '<div class="muted">该编码在火火火仓库没有「待发货 + 未成波 + 一单一件」的订单'
          + '（可能已生成波次 / 已打印 / 是多件单）。</div>' + extra;
        return;
      }
      /* 双快递模式：按快递分别入清单：有中通就进中通那份，有申通就进申通那份（两边都进也没问题） */
      const added = [], skipped = [];
      const cname = String(d.code || code).toUpperCase();
      Object.keys(per).forEach(function(k){
        const n = parseInt(per[k], 10) || 0;
        if(!(n > 0)) return;
        const bag = bagOf(k);
        if(bag.some(function(x){ return String(x.code).toUpperCase() === cname; })){ skipped.push(k); return; }
        bag.push({code: d.code || code, qty: n, max: n, info: info});
        added.push(k + ' ' + n + ' 件');
      });
      if(added.length){
        saveBags(); syncCarrierButtons(); render();
        bagLog('add', added.join(' '));
        $('hint').innerHTML = '<span class="qcode">' + esc(d.code || code) + '</span>：已加入 <b>'
          + esc(added.join('　·　')) + '</b>'
          + (skipped.length ? ('（' + esc(skipped.join('/')) + ' 清单已有，未重复）') : '')
          + (all ? '　全部：<span class="cex">' + esc(all) + '</span>' : '') + extra;
        return;
      }
      if(skipped.length){
        $('hint').innerHTML = '<span class="qcode">' + esc(d.code || code) + '</span>：'
          + esc(skipped.join('/')) + ' 清单里已有（未重复添加）'
          + (all ? '　全部：<span class="cex">' + esc(all) + '</span>' : '') + extra;
        return;
      }
      $('hint').innerHTML = '<span class="badtext">' + esc(d.code || code)
        + '：没有可成波订单</span>'
        + '<div class="muted">该编码在火火火仓库没有「待发货 + 未成波 + 一单一件」的订单'
        + '（可能已生成波次 / 已打印 / 是多件单）。</div>' + extra;
    })
    .catch(function(e){ $('hint').textContent = '查询失败：' + e.message; });
}

function bodyItems(){
  return ITEMS.filter(function(x){ return parseInt(x.qty,10) > 0; })
              .map(function(x){ return {code:x.code, qty:parseInt(x.qty,10)}; });
}

function post(path, obj){
  return fetch(bust(withSid(path)), {method:'POST', cache:'no-store',
      headers:{'Content-Type':'application/json'}, body:JSON.stringify(obj)})
    .then(function(r){ if(r.status === 401){ location.href = '/login'; throw new Error('请重新登录'); } return r.json(); });
}

/* ---- v1.61：成波排队「看得见」----
   成波是串行的（多账号一起用会排队，最多等 3 分钟）。等结果期间轮询
   /api/wave/queue，把提示从「正在挑单并成波…」换成「前面还有 N 个波次，已等 X 秒」，
   免得看着像卡死。 */
let _qTimer = null, _qT0 = 0, _qBox = null;
function qMsg(html){
  if(_qBox && _qBox.parentNode){ _qBox.innerHTML = html; }
}
function qSecs(){ return Math.max(0, Math.round((Date.now() - _qT0) / 1000)); }
function qTick(){
  if(!_qBox || !_qBox.parentNode){ stopQueueWatch(); return; }
  const s = qSecs();
  fetch(bust(withSid('/api/wave/queue')), {cache:'no-store'})
    .then(function(r){ return r.json(); })
    .then(function(d){
      if(!d || !d.ok){ qMsg('正在挑单并成波…已等 <b>' + s + '</b> 秒'); return; }
      if(d.running && d.waiting > 0){
        qMsg('<b>排队中</b>：前面还有 <b>' + d.waiting + '</b> 个波次在生成，已等 <b>' + s + '</b> 秒…');
      } else if(d.running){
        qMsg('正在挑单并成波…已等 <b>' + s + '</b> 秒（一个波次通常十几秒）');
      } else {
        qMsg('正在挑单并成波…已等 <b>' + s + '</b> 秒');
      }
    })
    .catch(function(){ qMsg('正在挑单并成波…已等 <b>' + s + '</b> 秒'); });
}
function startQueueWatch(){
  stopQueueWatch();
  _qBox = document.querySelector('#out .wq');
  _qT0 = Date.now();
  qTick();
  _qTimer = setInterval(qTick, 1500);
}
function stopQueueWatch(){
  if(_qTimer){ clearInterval(_qTimer); _qTimer = null; }
  _qBox = null;
}

function renderPlan(p){
  const cs = p.codes || [];
  let h = '<div class="card"><h2>预览（干跑，不建波）' + (p.carrier ? '　·　快递 ' + esc(p.carrier) : '') + '</h2>';
  h += '<table><thead><tr><th>编码</th><th>目标</th><th>最大</th><th>实际成波</th></tr></thead><tbody>';
  cs.forEach(function(c){
    const capped = c.target > c.max;
    h += '<tr><td>' + esc(c.code) + '</td><td>' + esc(c.target) + '</td><td>' + esc(c.max) + '</td>'
       + '<td class="' + (c.actual < c.target ? 'badtext' : 'oktext') + '">' + esc(c.actual)
       + (capped ? ' <span class="tag warn">按最大</span>' : '') + '</td></tr>';
  });
  h += '</tbody></table>';
  h += '<div style="margin-top:8px">将成波 <b>' + (p.sids || []).length + '</b> 张订单（1 个波次）</div>';
  h += '<div class="muted" style="margin-top:6px">挑单顺序：已超时 → 加急 → 剩余时间少优先</div>';
  h += '<table style="margin-top:8px"><thead><tr><th>sid</th><th>剩余</th><th>加急</th><th>贡献</th></tr></thead><tbody>';
  (p.picks || []).forEach(function(k){
    const r = (k.remain == null) ? '?' : (Math.round(k.remain * 10) / 10 + 'h');
    const cs2 = Object.keys(k.contribute || {}).map(function(c){ return c + '×' + k.contribute[c]; }).join(' ');
    h += '<tr><td>' + esc(k.sid) + '</td><td>' + esc(r) + '</td><td>' + (k.urgent ? '是' : '') + '</td><td>' + esc(cs2) + '</td></tr>';
  });
  h += '</tbody></table></div>';
  $('out').innerHTML = h;
}

document.querySelectorAll('#cbar .seg').forEach(function(b){
  b.onclick = function(){ setCarrier(b.getAttribute('data-car')); };
});
(function(){
  const mb = $('modeBtn');
  if(mb){ mb.onclick = function(){ toggleMode(); }; }
})();
/* ---------- 摄像头扫码添加（优先 BarcodeDetector，不支持则用中转注入的 ZXing）---------- */
let stream=null, scanTimer=null, zxReader=null;
function camShow(on){ $('camBox').classList.toggle('hidden', !on); }
function camHit(v){
  stopCam();
  const code=String(v||'').trim();
  if(code){ addCode(code); }
}
function zxHints(){
  const Z=window.ZXing, F=Z.BarcodeFormat;
  const list=[F.CODE_128,F.CODE_39,F.CODE_93,F.ITF,F.EAN_13,F.EAN_8,F.UPC_A,F.UPC_E,F.QR_CODE,F.DATA_MATRIX];
  const h=new Map();
  h.set(Z.DecodeHintType.POSSIBLE_FORMATS, list);
  h.set(Z.DecodeHintType.TRY_HARDER, true);
  return h;
}
async function startCam(){
  camShow(true);
  $('camMsg').textContent='正在打开摄像头…';
  /* ① 优先 ZXing（首页那套）。小米/部分国产浏览器自带 BarcodeDetector 是空壳：
        画面打得开但永远识别不到 —— 所以不能先试它。 */
  if(window.ZXing && window.ZXing.BrowserMultiFormatReader){
    try {
      zxReader=new window.ZXing.BrowserMultiFormatReader();
      try { if(zxReader.reader && zxReader.reader.setHints) zxReader.reader.setHints(zxHints()); } catch(e){}
      const cb=function(res,err){ if(res){ camHit(res.getText()); } };
      if(zxReader.decodeFromConstraints){
        zxReader.decodeFromConstraints({video:{facingMode:'environment'}}, $('video'), cb);
      } else {
        zxReader.decodeFromVideoDevice(null, $('video'), cb);
      }
      $('camMsg').textContent='对准条码…';
      return;
    } catch(e){
      $('camMsg').textContent='ZXing 启动失败，改用浏览器自带识别…';
      try { if(zxReader){ zxReader.reset(); } } catch(_){}
      zxReader=null;
    }
  }
  /* ② 退回 BarcodeDetector（桌面 Chrome/Edge 一般可用） */
  try { stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'environment'}}); }
  catch(e){ alert('无法打开摄像头：'+e.message+'\n（手机浏览器需用 https 打开本页）'); camShow(false); return; }
  try { $('video').srcObject=stream; await $('video').play(); } catch(e){}
  if('BarcodeDetector' in window){
    $('camMsg').textContent='对准条码…';
    const det=new window.BarcodeDetector();
    scanTimer=setInterval(async function(){
      try { const c=await det.detect($('video')); if(c&&c.length){ camHit(c[0].rawValue); } } catch(e){}
    }, 400);
  } else {
    $('camMsg').textContent='此浏览器不支持摄像头识别条码，请用扫码枪或手动输入';
  }
}
function stopCam(){
  if(scanTimer){ clearInterval(scanTimer); scanTimer=null; }
  try { if(zxReader){ zxReader.reset(); zxReader=null; } } catch(e){}
  if(stream){ try { stream.getTracks().forEach(function(t){ t.stop(); }); } catch(e){} stream=null; }
  camShow(false);
}
$('btnCam').onclick=startCam; $('btnCamStop').onclick=stopCam;
$('lnkHome').href = withSid('/');
$('lnkRec').href = withSid('/wave-records');
/* scan.js（中转本地提供的扫码增强层，和首页同一套）扫到码后会调 window.query(code)。
   它接管条件：#btnCam + #video + #camBox 都在；缺了才走我自己上面那套。 */
window.query = function(code){ if(code){ addCode(String(code).trim()); } };

/* ---- PDA 扫码枪兼容（v1.45）----
   1) 有些枪不带回车后缀：一串快速输入后停 ~150ms 就当"扫完了"，自动提交；
   2) 有些 PDA 浏览器不给/丢失自动聚焦：没聚焦时在页面层也接住（打字落到 body）；
   3) 点页面空白处自动把焦点放回编码框。 */
function kmWedge(el, submit, clearAfter){
  /* 扫码枪**带回车后缀**：只认回车提交，不做「快输入自动提交」（避免误触发）。 */
  if(!el || !submit) return;
  el.addEventListener('keydown', function(e){
    if(e.key === 'Enter'){
      e.preventDefault();
      var v=(el.value||'').trim();
      if(v){ submit(v); if(clearAfter){ el.value=''; } }
    }
  });
}
kmWedge($('code'), function(v){ addCode(v); }, true);
/* 没聚焦时也接住（打字落到 body）：回车 / 一串≥6 字符快输入 就提交 */
(function(){
  var buf='';
  document.addEventListener('keydown', function(e){
    var tg=e.target||{};
    if(tg.tagName==='INPUT'||tg.tagName==='TEXTAREA'||tg.isContentEditable) return;
    if(e.key==='Enter'){ var v=buf.trim(); buf=''; if(v.length>=4){ addCode(v); } return; }
    if(e.key && e.key.length===1){ buf += e.key; }   /* 没聚焦时先攒着，等回车再提交 */
  });
  /* 点空白处把焦点放回编码框（PDA 浏览器常丢焦点） */
  document.addEventListener('click', function(e){
    var tg=e.target||{};
    if(tg.tagName==='BUTTON'||tg.tagName==='INPUT'||tg.tagName==='SELECT'||tg.tagName==='TEXTAREA'||tg.tagName==='A') return;
    try{ $('code').focus(); }catch(_){}
  });
})();

$('prev').onclick = function(){
  const items = bodyItems();
  if(!items.length){ alert('请先添加编码并填写件数'); return; }
  $('out').innerHTML = '<div class="card"><div class="muted">正在干跑挑单…</div></div>';
  post('/api/wave/preview', {items:items, carrier:CARRIER}).then(function(p){
    if(p.error){ $('out').innerHTML = '<div class="card"><div class="badtext">' + esc(p.error) + '</div></div>'; return; }
    renderPlan(p);
  }).catch(function(e){ $('out').innerHTML = '<div class="card"><div class="badtext">预览失败：' + esc(e.message) + '</div></div>'; });
};

$('mk').onclick = function(){
  saveBags();                        /* 成波前先落盘：两份清单都存好 */
  const items = bodyItems();
  if(!items.length){ alert('请先添加编码并填写件数'); return; }
  if(!confirm('将用「' + CARRIER + '」生成 1 个波次（清单里所有编码合并成一个波次，只含该快递）。真要建波吗？')) return;
  $('out').innerHTML = '<div class="card"><div class="muted wq">正在挑单并成波…（请稍候）</div></div>';
  startQueueWatch();
  /* v1.46：波次号由 ERP「波次管理」列表回读（含未拣选波次）。created=true 才显示成功样式；
     save 返回 success 但回读不到 → 显示「ERP 未建出波次（未确认），请重试」，不冒充成功。 */
  post('/api/wave/create', {items:items, carrier:CARRIER, confirm:true}).then(function(p){
    stopQueueWatch();
    let h = '';
    if(p.busy){
      h += '<div class="card"><h2>正在生成波次</h2><div class="badtext">'
         + esc(p.error || '正在生成波次，请稍候再试') + '</div></div>';
      $('out').innerHTML = h + planCard(p);
      return;
    }
    if(!p.save_ok){
      h += '<div class="card"><h2>成波失败</h2><div class="badtext">' + esc(p.error || '未返回 success') + '</div>';
      if(p.save_msg) h += '<div class="muted" style="margin-top:6px">' + esc(p.save_msg) + '</div>';
      h += '</div>';
      $('out').innerHTML = h + planCard(p);
      return;
    }
    const v = p.verify || {};
    if(p.created === true || v.ok){
      dropFromBag(CARRIER, p, items);   /* 只从「当前快递」清单移除已进波次的编码 */
      /* ★ 成波成功后刷新「最大可生成」：本次用的编码从清单移除了，
         但**同一个编码可能还在另一个快递的清单里**（中通/申通两份清单），
         而且用户会马上再查同一个编码 —— 必须让数字立刻反映剩余量。 */
      try{
        const imp = {};
        (p.codes || []).forEach(function(c){ if(c && c.code) imp[c.code] = c.actual; });
        refreshMaxForCodes(Object.keys(imp), imp);
      }catch(e){}
      h += '<div class="card"><h2>成波成功</h2>';
      h += '<div class="big oktext">波次号：' + esc(p.wave_code || v.wave_code || p.wave_id || '-') + '</div>'
         + '<div style="margin-top:6px"><span class="tag">状态 ' + esc(v.status_cn || v.status || '未拣') + '</span>'
         + '<span class="tag ok">已建出 ' + esc(v.item_count == null ? (p.sids || []).length : v.item_count) + ' 件</span>'
         + '<span class="tag">订单数 ' + esc((p.sids || []).length) + '</span>';
      h += '</div>';
      h += '<h2 style="margin-top:12px">配货明细（每个 SKU 一行）</h2>' + skuLines(p)
         + '<div class="muted" style="margin-top:6px">波次号实时回读快麦 ERP「波次管理」。</div>';
      const wid = p.wave_id || v.wave_id || p.wave_code;
      if(wid){
        h += '<div class="actions" style="margin-top:10px"><button id="fwFromCreate" class="ghost" data-wid="'
           + esc(wid) + '">一键拣完（不用输入）</button></div>';
      }
      h += '</div>';
    } else {
      h += '<div class="card"><h2>成波未确认</h2>'
         + '<div class="badtext">ERP 未建出波次（未确认），请重试</div>'
         + '<div class="muted" style="margin-top:6px">' + esc(p.verify_error || v.error || '回读未找到新波次') + '</div>'
         + '</div>';
    }
    $('out').innerHTML = h + planCard(p);
    wireFinishFromCreate();
  }).catch(function(e){ stopQueueWatch(); $('out').innerHTML = '<div class="card"><div class="badtext">成波请求失败：' + esc(e.message) + '</div></div>'; });
};

/* ★ 成波后刷新「最大可生成」。
   踩过的坑（用户反馈）：生成 210 件之后，同一个编码还显示成波前的 600 件，
   应该变成 490 左右 —— 因为 it.max 是**加入清单那一刻**存下的旧值，成波后从不重算。
   ERP 侧其实是实时的（实测：524 → 生成 1 件 → 立刻变 523），所以只要重新查一次就行。

   immediate：本次已知的实际成波件数 {编码: 件数}，先本地减掉，让数字立刻变小，
             等实时查询回来再以 ERP 的为准（避免网络慢时看着像"没变"）。 */
function refreshMaxForCodes(codes, immediate){
  (codes || []).forEach(function(code){
    const key = String(code).toUpperCase();
    const imp = immediate && immediate[code] != null ? parseInt(immediate[code], 10) : null;
    ITEMS.forEach(function(it){
      if(String(it.code).toUpperCase() !== key) return;
      if(imp != null && !isNaN(imp) && imp > 0 && it.info && it.info.mode !== 'multi'){
        it.max = Math.max(0, (parseInt(it.max, 10) || 0) - imp);
        it.qty = Math.max(0, (parseInt(it.qty, 10) || 0) - imp);
      }
    });
    fetch(bust(withSid('/api/wave/lookup?code=' + encodeURIComponent(code))), {cache:'no-store'})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(!d || d.error) return;
        const per = d.carriers || {};
        const cnum = parseInt(per[CARRIER], 10) || 0;
        ITEMS.forEach(function(it){
          if(String(it.code).toUpperCase() !== key) return;
          /* 单快递模式：以该快递的可生成数为准；双快递：取两个快递之和 */
          const tot = DUAL ? Object.keys(per).reduce(function(a,k){ return a + (parseInt(per[k],10)||0); }, 0) : cnum;
          it.max = tot;
          if((parseInt(it.qty, 10) || 0) > tot) it.qty = tot;
          if(it.info){
            it.info.shelf_qty = d.shelf_qty;
            it.info.bins_text = d.bins_text || '';
            it.info.shelf_index_empty = d.shelf_index_empty;
          }
        });
        saveBags(); render();
      })
      .catch(function(){});
  });
}

/* ★ 把清单里**所有编码**的最大可生成数重算一遍（进页面 / 定时）。
   为什么需要：成波后如果只靠成波事件去刷新，用户从别处（另一台电脑、手机、
   或者刷新页面）回来时看到的还是旧数字。这里主动校一遍最稳。 */
function refreshAllMaxQuiet(){
  if(!ITEMS || !ITEMS.length) return;
  ITEMS.slice().forEach(function(it){
    const code = it.code;
    const key = String(code).toUpperCase();
    fetch(bust(withSid('/api/wave/lookup?code=' + encodeURIComponent(code))), {cache:'no-store'})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(!d || d.error) return;
        const per = d.carriers || {};
        const cnum = parseInt(per[CARRIER], 10) || 0;
        const tot = DUAL ? Object.keys(per).reduce(function(a,k){ return a + (parseInt(per[k],10)||0); }, 0) : cnum;
        let changed = false;
        ITEMS.forEach(function(x){
          if(String(x.code).toUpperCase() !== key) return;
          if((parseInt(x.max, 10) || 0) !== tot){ x.max = tot; changed = true; }
          /* 只剩下这么多了，输入框别停在超量值上 */
          if((parseInt(x.qty, 10) || 0) > tot){ x.qty = tot; changed = true; }
          if(x.info){
            x.info.shelf_qty = d.shelf_qty;
            x.info.bins_text = d.bins_text || '';
            x.info.shelf_index_empty = d.shelf_index_empty;
          }
        });
        if(changed){ saveBags(); render(); }
      })
      .catch(function(){});
  });
}

function planCard(p){
  const cs = p.codes || [];
  let h = '<div class="card"><h2>本次挑单</h2><table><thead><tr><th>编码</th><th>目标</th><th>实际</th></tr></thead><tbody>';
  cs.forEach(function(c){ h += '<tr><td>' + esc(c.code) + '</td><td>' + esc(c.target) + '</td><td>' + esc(c.actual) + '</td></tr>'; });
  h += '</tbody></table><div class="muted" style="margin-top:6px">sid：' + esc((p.sids || []).join(', ')) + '</div></div>';
  return h;
}

/* 配货明细：每个 SKU 一行，形如 「7107-燕麦色S  38 件」（自动换行，不挤成一行） */
function skuLines(p){
  const cs = p.codes || [];
  if(!cs.length) return '<div class="muted">（无编码明细）</div>';
  let h = '<div class="skus">';
  cs.forEach(function(c){
    h += '<div class="sku"><span class="skun">' + esc(c.code) + '</span>'
       + '<span class="skuq">' + esc(c.actual) + ' 件</span></div>';
  });
  h += '</div>';
  return h;
}

/* ---------------- 一键拣完：两段（先只读回读预览 → 再确认提交） ---------------- */
function finishRenderPreview(d){
  if(!d || d.ok === false){
    return '<div class="card"><h2>一键拣完 · 预览</h2><div class="badtext">'
      + esc((d && d.error) || '预览失败') + '</div></div>';
  }
  let h = '<div class="card"><h2>一键拣完 · 预览（只读，尚未提交）</h2>';
  h += '<div style="margin-top:6px"><span class="tag">波次 ' + esc(d.wave_code || d.wave_id) + '</span>'
     + '<span class="tag">订单数 ' + esc(d.tradesCount == null ? '-' : d.tradesCount) + '</span>'
     + '<span class="tag">件数 ' + esc(d.itemCount == null ? '-' : d.itemCount) + '</span>'
     + '<span class="tag' + (d.picked ? ' ok' : '') + '">' + (d.picked ? '已拣' : '未拣') + '</span></div>';
  h += '<div class="muted" style="margin-top:6px">拣货完成时间：' + esc(d.pickEndTime || '（无）') + '</div>';
  h += '<div style="margin-top:8px">将执行：<b>'
     + esc(d.will_execute || ('手动拣选(ids=' + d.wave_id + ')')) + '</b>　—　只读预览，尚未提交（不会写）</div>';
  if(d.warning) h += '<div class="badtext" style="margin-top:6px">' + esc(d.warning) + '</div>';
  h += '<div class="muted" style="margin-top:8px">点「确认拣完」会真的把该波次标记为 <b>拣选完成</b>'
     + '（网页随即显示<b>等待验货</b>），<b>不可撤销</b>。</div>'
     + '<div class="actions"><button id="fwGo" class="ghost">确认拣完（不可撤销）</button></div></div>';
  return h;
}
function finishCommit(wid){
  if(!confirm('确认把波次 ' + wid + ' 标记为「拣选完成（等待验货）」？\n会写入快麦 ERP，不可撤销。')) return;
  $('fwOut').innerHTML = '<div class="card"><div class="muted">正在提交（手动拣选）…</div></div>';
  post('/api/wave/finish', {wave_id: wid, confirm: true}).then(function(d){
    let h = '<div class="card"><h2>一键拣完 · 结果</h2>';
    if(d && d.ok){
      h += '<div class="big oktext">波次 ' + esc(d.wave_code || d.wave_id) + ' 拣选完成（等待验货）</div>'
         + '<div style="margin-top:6px"><span class="tag ok">新状态 ' + esc(d.status_cn || d.status || '?')
         + '</span><span class="tag">' + (d.picked ? '已拣' : '未拣') + '</span>'
         + '<span class="tag">件数 ' + esc(d.itemCount == null ? '-' : d.itemCount) + '</span></div>'
         + '<div class="muted" style="margin-top:6px">拣货完成时间：' + esc(d.pickEndTime || '（无）') + '</div>';
      if(d.warning) h += '<div class="muted" style="margin-top:6px">' + esc(d.warning) + '</div>';
    } else {
      h += '<div class="badtext">未成功：' + esc((d && d.error) || '未知失败') + '</div>';
      if(d && d.pick_hand) h += '<div class="muted" style="margin-top:6px">pick.hand：' + esc(JSON.stringify(d.pick_hand)) + '</div>';
    }
    h += '<div class="muted" style="margin-top:8px">状态为实时回读快麦 ERP。</div></div>';
    $('fwOut').innerHTML = h;
  }).catch(function(e){ $('fwOut').innerHTML = '<div class="card"><div class="badtext">提交失败：' + esc(e.message) + '</div></div>'; });
}
function finishPreview(wid){
  $('fwOut').innerHTML = '<div class="card"><div class="muted">正在只读回读波次…</div></div>';
  post('/api/wave/finish', {wave_id: wid, confirm: false}).then(function(d){
    $('fwOut').innerHTML = finishRenderPreview(d);
    const b = $('fwGo');
    if(b) b.onclick = function(){ finishCommit(wid); };
  }).catch(function(e){ $('fwOut').innerHTML = '<div class="card"><div class="badtext">预览失败：' + esc(e.message) + '</div></div>'; });
}
function wireFinishFromCreate(){
  const b = $('fwFromCreate');
  if(!b) return;
  b.onclick = function(){
    const wid = b.getAttribute('data-wid');
    if(!wid){ alert('本次未拿到波次ID，请在「波次记录」页用该波次的一键拣完，或手动输入波次ID'); return; }
    if($('fwid')) $('fwid').value = wid;
    finishPreview(wid);
    const t = $('fwOut');
    if(t && t.scrollIntoView) t.scrollIntoView({behavior:'smooth', block:'center'});
  };
}
$('fwPrev').onclick = function(){
  const wid = ($('fwid').value || '').trim();
  if(!wid){ alert('请先输入波次ID'); return; }
  finishPreview(wid);
};

loadMode();                              /* 恢复上次选的模式（双快递 / 单快递旧模式） */
restoreBags();                           /* 双快递模式下：刷新/重开时恢复上次两份清单，并问「保留/不保留」 */
render();
syncCarrierButtons();
$('code').focus();
refreshShelfStatus();                     /* 进页面：读货位时间戳并按需后台刷一次 */
setInterval(refreshShelfStatus, 30000);   /* 停留时每 30s 校一次新鲜度 */
try{ refreshAllMaxQuiet(); }catch(e){}    /* ★ 进页面：把清单里各编码的可生成数按 ERP 重算一遍 */
setInterval(function(){ try{ refreshAllMaxQuiet(); }catch(e){} }, 60000);  /* 停留时每分钟校一次 */
</script>
<script src="/km/scan.js?v=8"></script>
</body></html>
"""

# ============================ 网页「波次记录」页（/wave-records） ============================
# 数据来自 GET /api/wave/records：本地只存「我自己生成过哪些波次号」，
# 每条的 状态 / 件数 / 订单数 一律实时回读快麦 ERP（erp.trade.waves.query），不读本机缓存。
WAVE_RECORDS_HTML = r"""<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>波次记录 · 快麦</title>
<style>
  * { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
  :root { --blue:#007AFF; --green:#34C759; --red:#FF3B30; --orange:#FF9500; --ink:#1d1d1f; --sub:#6e6e73;
          --line:rgba(60,60,67,.12); --fill:rgba(120,120,128,.12); --glass:#e0e5ec; }
  body { margin:0; padding:12px; min-height:100vh; color:var(--ink); letter-spacing:-.01em;
         -webkit-font-smoothing:antialiased;
         font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
         background:#e0e5ec; }
  header { display:flex; align-items:center; gap:8px; padding:2px 3px 10px; flex-wrap:wrap; }
  header b { font-size:17px; }
  header .sp { flex:1; }
  header a.home { color:var(--blue); text-decoration:none; font-size:13.5px; font-weight:600;
                  background:var(--fill); border-radius:9px; padding:5px 11px; white-space:nowrap; }
  .card { background:var(--glass); backdrop-filter:saturate(180%) blur(20px);
          -webkit-backdrop-filter:saturate(180%) blur(20px); border:0;
          border-radius:14px; padding:12px; margin-bottom:10px; box-shadow:var(--neu-up); }
  .card h2 { font-size:15px; margin:0 0 8px; font-weight:700; border-left:3px solid var(--blue); padding-left:8px; }
  .muted { font-size:12.5px; color:var(--sub); line-height:1.7; }
  /* 窄屏 PDA：表格可横滑，关键列不换行、数字等宽，长波次号/时间不错乱 */
  .tw { overflow-x:auto; -webkit-overflow-scrolling:touch; margin:0 -2px; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th,td { padding:9px 8px; border-bottom:1px solid rgba(60,60,67,.10); text-align:left; vertical-align:middle; }
  th { color:var(--sub); font-weight:700; font-size:11.5px; letter-spacing:.03em; white-space:nowrap;
       background:var(--glass); position:sticky; top:0; z-index:1; }
  td.code { font-weight:800; font-size:14.5px; white-space:nowrap; font-variant-numeric:tabular-nums; }
  td.time { white-space:nowrap; color:var(--sub); font-size:12.5px; font-variant-numeric:tabular-nums; }
  td.num { white-space:nowrap; font-variant-numeric:tabular-nums; font-weight:600; }
  td.act { white-space:nowrap; }
  tbody tr:nth-child(even) td { background:rgba(120,120,128,.05); }
  .pill { display:inline-block; padding:3px 10px; border-radius:999px; font-size:12px; font-weight:800; white-space:nowrap; }
  .pill.wait { background:rgba(255,149,0,.16); color:#a35c00; }
  .pill.ok { background:rgba(52,199,89,.15); color:#1B7F35; }
  .pill.cancel { background:rgba(255,59,48,.13); color:#c62828; }
  .pill.raw { background:var(--fill); color:var(--sub); }
  .skus .sku { display:flex; justify-content:space-between; gap:10px; padding:3px 0;
               border-top:1px dashed rgba(60,60,67,.10); }
  .skus .sku:first-child { border-top:0; }
  .skus .skun { word-break:break-all; }
  .skus .skuq { flex:0 0 auto; font-weight:700; color:var(--blue); white-space:nowrap; }
  .badtext { color:#C7362E; }
  .fin { padding:5px 11px; border-radius:9px; border:1px solid rgba(0,122,255,.35); background:rgba(0,122,255,.10);
         color:#0060D0; font-weight:700; font-size:12.5px; white-space:nowrap; cursor:pointer; }
  .fin:active { transform:scale(.97); }
  @media (max-width:430px) {
    body { padding:8px; }
    th,td { padding:8px 6px; }
    td.code { font-size:13.5px; }
  }
  @media (prefers-color-scheme: dark) {
    body { background:#262b36; color:#f2f2f7; }
    .card { background:#262b36; border-color:rgba(255,255,255,.08); }
    .muted { color:#a1a1a6; }
    th,td { border-bottom-color:rgba(255,255,255,.08); }
    th { background:#262b36; }
    tbody tr:nth-child(even) td { background:rgba(255,255,255,.04); }
  }
</style>
<style>
:root{--neu-up:8px 8px 18px rgba(163,177,198,.55),-8px -8px 18px rgba(255,255,255,.95);--neu-up-sm:4px 4px 10px rgba(163,177,198,.55),-4px -4px 10px rgba(255,255,255,.95);--neu-in:inset 5px 5px 10px rgba(163,177,198,.5),inset -5px -5px 10px rgba(255,255,255,.9);--neu-in-sm:inset 4px 4px 8px rgba(163,177,198,.5),inset -4px -4px 8px rgba(255,255,255,.9);}
input:not([type=checkbox]):not([type=radio]):not([type=range]),select,textarea{background:#e0e5ec!important;border:0!important;box-shadow:var(--neu-in)!important}
button{border:0;box-shadow:var(--neu-up-sm)}
button.ghost{background:#e0e5ec;box-shadow:var(--neu-up-sm)}
button:active{box-shadow:var(--neu-in-sm)}
@media (prefers-color-scheme:dark){:root{--neu-up:8px 8px 18px rgba(8,10,16,.6),-8px -8px 18px rgba(255,255,255,.06);--neu-up-sm:4px 4px 10px rgba(8,10,16,.6),-4px -4px 10px rgba(255,255,255,.06);--neu-in:inset 5px 5px 10px rgba(8,10,16,.6),inset -5px -5px 10px rgba(255,255,255,.05);--neu-in-sm:inset 4px 4px 8px rgba(8,10,16,.6),inset -4px -4px 8px rgba(255,255,255,.05)}input:not([type=checkbox]):not([type=radio]):not([type=range]),select,textarea{background:#262b36!important}button.ghost{background:#262b36}}
</style></head>
<body>
<header><span id="hdrTitle"></span><b>波次记录</b><span class="sp"></span>
  <span class="muted" id="upd">载入中…</span>
  <a class="home" href="#" id="refresh">刷新</a>
  <a class="home" href="#" id="home">返回扫码</a></header>
<div class="card">
  <div class="muted">状态 / 件数 / 订单数 <b>实时来自快麦 ERP</b>（每次打开/刷新都重新回读，近 24 小时）。
    「<b>生成账号</b>」是<b>本系统</b>里点「生成波次」的那个账号 —— ERP 那边只有同一个登录，
    分不出是谁在本系统操作的，所以这一列取自本机记录（只存「波次号 → 账号」）。</div>
</div>
<div class="card">
  <h2>最近 ERP 波次</h2>
  <div class="tw">
  <table><thead><tr><th>波次号</th><th>状态</th><th>订单数</th><th>件数</th><th>生成账号</th><th>操作</th></tr></thead>
  <tbody id="recentBody"><tr><td colspan="6" class="muted">载入中…</td></tr></tbody></table>
  </div>
</div>
<script>
const $ = id => document.getElementById(id);
const esc = s => String(s==null?'':s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const SID = (function(){
  try { const q = new URLSearchParams(location.search).get('sid');
        if(q) localStorage.setItem('km_sid', q);
        return localStorage.getItem('km_sid') || ''; } catch(e){ return ''; }
})();
function withSid(u){ return SID ? (u + (u.indexOf('?') >= 0 ? '&' : '?') + 'sid=' + encodeURIComponent(SID)) : u; }
function bust(u){ return u + (u.indexOf('?') >= 0 ? '&' : '?') + 't=' + Date.now(); }

function pill(status, status_cn){
  const s = String(status_cn || status || '');
  let cls = 'raw';
  const raw = String(status);
  if(s === '已完成' || raw === '3') cls = 'ok';
  else if(s === '已取消' || raw === '4') cls = 'cancel';
  else if(s === '未完成' || raw === '1') cls = 'wait';
  const label = status_cn ? (status_cn + (raw ? '（' + raw + '）' : '')) : (raw || '?');
  return '<span class="pill ' + cls + '">' + esc(label) + '</span>';
}

function skuCell(codes){   /* 保留备用：波次记录页已改为「最近 ERP 波次」单表，暂不显示 SKU 明细 */
  if(!codes || !codes.length) return '<span class="muted">-</span>';
  let h = '<div class="skus">';
  codes.forEach(function(c){
    h += '<div class="sku"><span class="skun">' + esc(c.code) + '</span>'
       + '<span class="skuq">' + esc(c.actual) + ' 件</span></div>';
  });
  return h + '</div>';
}

function load(){
  $('upd').textContent = '查询中…';
  fetch(bust(withSid('/api/wave/records')), {cache:'no-store'})
    .then(function(r){ if(r.status === 401){ location.href = '/login'; throw new Error('请重新登录'); } return r.json(); })
    .then(function(d){
      if(!d || d.error && !d.records){ $('upd').innerHTML = '<span class="badtext">' + esc((d&&d.error)||'读取失败') + '</span>'; return; }
      const recent = d.recent || [];
      if(recent.length){
        let h = '';
        recent.forEach(function(w){
          const who = w.who ? esc(w.who)
              : (w.known ? '<span class="muted">（旧记录无账号）</span>'
                         : '<span class="muted">（非本系统）</span>');
          h += '<tr><td class="code">' + esc(w.wave_code || '-') + '</td>'
             + '<td>' + pill(w.status, w.status_cn) + '</td>'
             + '<td class="num">' + esc(w.tradesCount == null ? '-' : w.tradesCount) + '</td>'
             + '<td class="num">' + esc(w.itemCount == null ? '-' : w.itemCount) + '</td>'
             + '<td class="who">' + who + '</td>'
             + '<td class="act">' + (w.wave_id
                 ? ('<button class="fin" data-fw="' + esc(w.wave_id) + '" data-fwc="' + esc(w.wave_code || '') + '">一键拣完</button>')
                 : '<span class="muted">-</span>') + '</td></tr>';
        });
        $('recentBody').innerHTML = h;
      } else {
        $('recentBody').innerHTML = '<tr><td colspan="6" class="muted">近 24h 无波次</td></tr>';
      }
      $('upd').innerHTML = (d.live ? '实时已更新 ' : '实时回读失败：')
        + '<b>' + new Date().toLocaleTimeString() + '</b>'
        + (d.error ? ' <span class="badtext">' + esc(d.error) + '</span>' : '');
    })
    .catch(function(e){ $('upd').innerHTML = '<span class="badtext">查询失败：' + esc(e.message) + '</span>'; });
}

$('refresh').onclick = function(e){ if(e) e.preventDefault(); load(); return false; };

/* ---------------- 一键拣完：先只读回读预览 → 再确认提交（不可撤销） ---------------- */
function fwPreview(wid, wcode){
  $('recentBody').insertAdjacentHTML('beforeend',
    '<tr id="fwRow"><td colspan="6"><div id="fwBox"><span class="muted">正在只读回读波次…</span></div></td></tr>');
  $('fwBox').scrollIntoView({behavior:'smooth', block:'center'});
  fetch(bust(withSid('/api/wave/finish')), {method:'POST', cache:'no-store',
      headers:{'Content-Type':'application/json'}, body:JSON.stringify({wave_id:wid, confirm:false})})
    .then(function(r){ if(r.status === 401){ location.href = '/login'; throw new Error('请重新登录'); } return r.json(); })
    .then(function(d){
      if(!d || d.ok === false){ $('fwBox').innerHTML = '<span class="badtext">' + esc((d&&d.error)||'预览失败') + '</span>'; return; }
      let h = '<div><b>波次 ' + esc(d.wave_code || wcode || wid) + '</b>'
         + '　订单数 ' + esc(d.tradesCount == null ? '-' : d.tradesCount)
         + '　件数 ' + esc(d.itemCount == null ? '-' : d.itemCount)
         + '　' + (d.picked ? '已拣' : '未拣') + '</div>';
      h += '<div class="muted">拣货完成时间：' + esc(d.pickEndTime || '（无）')
         + '　将执行：' + esc(d.will_execute || ('手动拣选(ids=' + wid + ')')) + '（只读预览，未提交）</div>';
      if(d.warning) h += '<div class="badtext">' + esc(d.warning) + '</div>';
      h += '<div class="bar" style="margin-top:6px"><button class="fin" id="fwGo">确认拣完（不可撤销）</button>'
         + '<button class="fin" id="fwCancel">取消</button></div>';
      $('fwBox').innerHTML = h;
      $('fwCancel').onclick = function(){ const r = $('fwRow'); if(r) r.remove(); };
      $('fwGo').onclick = function(){
        if(!confirm('确认把波次 ' + (wcode || wid) + ' 标记为「拣选完成（等待验货）」？\n会写入快麦 ERP，不可撤销。')) return;
        $('fwBox').innerHTML = '<span class="muted">正在提交（手动拣选）…</span>';
        fetch(bust(withSid('/api/wave/finish')), {method:'POST', cache:'no-store',
            headers:{'Content-Type':'application/json'}, body:JSON.stringify({wave_id:wid, confirm:true})})
          .then(function(r){ return r.json(); })
          .then(function(d2){
            if(d2 && d2.ok){
              $('fwBox').innerHTML = '<div style="color:#1B7F35"><b>拣选完成（等待验货）</b> '
                + esc(d2.wave_code || wid) + '　新状态：' + esc(d2.status_cn || d2.status || '?')
                + '　件数 ' + esc(d2.itemCount == null ? '-' : d2.itemCount)
                + '　拣货完成 ' + esc(d2.pickEndTime || '（无）') + '</div>';
              setTimeout(load, 1500);
            } else {
              $('fwBox').innerHTML = '<span class="badtext">未成功：' + esc((d2&&d2.error)||'未知失败') + '</span>';
            }
          });
      };
    })
    .catch(function(e){ $('fwBox').innerHTML = '<span class="badtext">预览失败：' + esc(e.message) + '</span>'; });
}
$('recentBody').addEventListener('click', function(e){
  const b = e.target && e.target.closest ? e.target.closest('button[data-fw]') : null;
  if(b) fwPreview(b.getAttribute('data-fw'), b.getAttribute('data-fwc'));
});
$('home').href = withSid('/');
window.addEventListener('focus', load);
load();
setInterval(load, 30000);   // 页面停留时每 30s 实时刷新一次
</script>
</body></html>
"""
