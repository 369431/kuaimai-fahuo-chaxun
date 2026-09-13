# -*- coding: utf-8 -*-
"""登录页（首次设置管理员 / 登录 / 账号管理），风格与手机网页一致。"""

LOGIN_HTML = r"""<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>登录 · 快麦查询</title>
<style>
  * { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
  :root { --blue:#007AFF; --green:#34C759; --red:#FF3B30; --ink:#1d1d1f; --sub:#6e6e73;
          --line:rgba(60,60,67,.12); --fill:rgba(120,120,128,.12); --glass:rgba(255,255,255,.72); }
  body { margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center; padding:20px;
         font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
         letter-spacing:-.01em; -webkit-font-smoothing:antialiased; color:var(--ink);
         background:linear-gradient(170deg,#eef3fa 0%,#e6edf8 45%,#e1e8f4 100%) fixed; }
  .card { width:100%; max-width:400px; background:var(--glass); backdrop-filter:saturate(180%) blur(20px);
          -webkit-backdrop-filter:saturate(180%) blur(20px); border:1px solid rgba(255,255,255,.62);
          border-radius:20px; box-shadow:0 16px 44px rgba(24,39,75,.14), 0 1px 2px rgba(24,39,75,.05);
          padding:22px; }
  h1 { font-size:21px; margin:2px 0 4px; font-weight:700; letter-spacing:-.02em; }
  .sub { color:var(--sub); font-size:13px; margin-bottom:16px; }
  label { display:block; font-size:13px; color:var(--sub); margin:12px 0 6px; }
  input[type=text], input[type=password] { width:100%; padding:13px 14px; font-size:17px; color:var(--ink);
         background:rgba(255,255,255,.86); border:1px solid var(--line); border-radius:12px; }
  input:focus { outline:none; border-color:var(--blue); box-shadow:0 0 0 3.5px rgba(0,122,255,.16); }
  button { width:100%; margin-top:16px; padding:13px; font-size:16px; font-weight:600; border:0; border-radius:12px;
         background:var(--blue); color:#fff; box-shadow:0 1px 2px rgba(0,0,0,.10); }
  button.ghost { background:var(--fill); color:var(--blue); box-shadow:none; }
  button:active { transform:scale(.98); }
  .chk { display:flex; align-items:center; gap:8px; margin-top:14px; color:var(--ink); font-size:14px; }
  .chk input { width:18px; height:18px; }
  .msg { margin-top:12px; font-size:13.5px; min-height:18px; }
  .msg.err { color:#d70015; font-weight:600; }
  .msg.ok { color:#1B7F35; font-weight:600; }
  .rowline { display:flex; align-items:center; justify-content:space-between; gap:10px;
             padding:10px 0; border-bottom:1px solid rgba(60,60,67,.08); font-size:14px; }
  .rowline:last-child { border-bottom:0; }
  .badge { font-size:12px; padding:2px 8px; border-radius:7px; background:var(--fill); color:var(--sub); }
  .badge.on { background:rgba(52,199,89,.16); color:#1B7F35; }
  .badge.admin { background:rgba(0,122,255,.14); color:#0060d0; }
  .mini { width:auto; margin:0; padding:7px 12px; font-size:13px; border-radius:9px; }
  .hidden { display:none; }
  .sep { height:1px; background:rgba(60,60,67,.10); margin:18px 0; }
  .small { font-size:12.5px; color:var(--sub); margin-top:10px; line-height:1.6; }
  @media (prefers-color-scheme: dark) {
    body { background:linear-gradient(170deg,#1c1c1e,#151517 60%,#1a1a1c) fixed; color:#f2f2f7; }
    .card { background:rgba(28,28,30,.72); border-color:rgba(255,255,255,.08); }
    input { background:rgba(118,118,128,.24); border-color:rgba(255,255,255,.12); color:#f2f2f7; }
    .sub, label, .small { color:#a1a1a6; }
  }
</style></head>
<body>
<div class="card" id="box"><h1>载入中…</h1></div>
<script>
const $ = id => document.getElementById(id);
let ME = null;
const esc = s => String(s==null?'':s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function api(path, body){
  const r = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'},
                               body: JSON.stringify(body||{})});
  let d = {}; try { d = await r.json(); } catch(e){}
  return d;
}
function remember(name, pw, on){
  try {
    if(on){ localStorage.setItem('km_user', name); localStorage.setItem('km_pw', btoa(unescape(encodeURIComponent(pw)))); }
    else { localStorage.removeItem('km_user'); localStorage.removeItem('km_pw'); }
  } catch(e){}
}
function remembered(){
  try {
    const n = localStorage.getItem('km_user') || '';
    let p = '';
    try { p = localStorage.getItem('km_pw') ? decodeURIComponent(escape(atob(localStorage.getItem('km_pw')))) : ''; } catch(e){}
    return {name:n, pw:p};
  } catch(e){ return {name:'', pw:''}; }
}
function setToken(t){ try { if(t) localStorage.setItem('km_sid', t); else localStorage.removeItem('km_sid'); } catch(e){} }
/* 设备标识：登录时带上，管理员踢下线后靠它记住"这台设备 10 分钟内不能再登录" */
function devId(){
  try {
    let d = localStorage.getItem('km_dev');
    if(!d){ d = Math.random().toString(16).slice(2, 10) + Date.now().toString(16); localStorage.setItem('km_dev', d); }
    return d;
  } catch(e){ return ''; }
}
async function modelName(){
  try {
    if(navigator.userAgentData && navigator.userAgentData.getHighEntropyValues){
      const h = await navigator.userAgentData.getHighEntropyValues(['model','platform']);
      return [h.model, h.platform].filter(Boolean).join(' ');
    }
  } catch(e){}
  return '';
}
function gotoApp(){
  let t = '';
  try { t = localStorage.getItem('km_sid') || ''; } catch(e){}
  location.href = '/' + (t ? ('?sid=' + encodeURIComponent(t)) : '');
}

async function boot(tries){
  tries = tries || 0;
  try {
    const r = await fetch('/api/auth/state', {cache:'no-store'});
    const d = await r.json();
    if(d.need_setup) return setupView(d);
    if(!d.user) return loginView(d);
    ME = d; homeView(d);
    return;
  } catch(e){
    if(tries < 8){
      $('box').innerHTML = '<h1>正在连接…</h1><div class="sub">后台程序可能刚重启或网络抖了一下，正在重试（'
        + (tries + 1) + '/8）</div>';
      setTimeout(() => boot(tries + 1), 1500);
      return;
    }
    $('box').innerHTML = '<h1>连不上后台程序</h1>'
      + '<div class="sub">查询服务（电脑上的「快麦扫码查询」）好像没在运行。</div>'
      + '<div class="small">请确认电脑上的程序已启动，然后点下面重试。</div>'
      + '<button id="again">重试</button>';
    $('again').onclick = () => boot(0);
  }
}
function setupView(d){
  if(d && d.local === false){
    $('box').innerHTML = '<h1>需要在本机设置</h1>'
      + '<div class="sub">这台服务还没有管理员账号。为了不让陌生人设密码，<b>第一次设置只能在跑程序的这台电脑上做</b>。</div>'
      + '<div class="small">请在电脑上打开 <b>http://127.0.0.1:8790/login</b> 设置管理员账号；设好之后，手机和外面的电脑都在这一页正常登录。</div>';
    return;
  }
  const first = !(d && d.need_setup === false);
  $('box').innerHTML = '<h1>' + (first ? '设置管理员账号' : '重置管理员密码') + '</h1>'
    + '<div class="sub">' + (first
        ? '这台机器第一次使用，请先设置管理员（只有管理员能加/删账号）'
        : '本机操作：管理员账号已存在就重置密码，不存在就新建一个管理员') + '</div>'
    + '<label>管理员账号</label><input id="u" type="text" autocomplete="username" placeholder="例如 admin">'
    + '<label>密码（至少 4 位）</label><input id="p" type="password" autocomplete="new-password">'
    + '<label>确认密码</label><input id="p2" type="password" autocomplete="new-password">'
    + '<button id="go">创建并进入</button><div class="msg" id="m"></div>'
    + '<div class="small">账号存在程序目录的 kuaimai_users.json，密码只存加盐 SHA-256。</div>';
  $('go').onclick = async () => {
    const u = $('u').value.trim(), p = $('p').value, p2 = $('p2').value;
    if(!u || !p) return msg('err', '账号和密码不能为空');
    if(p !== p2) return msg('err', '两次密码不一致');
    const d = await api('/api/auth/setup', {name:u, pw:p, dev_id:devId(), model:await modelName()});
    if(d.error) return msg('err', d.error);
    setToken(d.token);
    gotoApp();
  };
}
function loginView(d){
  const r = remembered();
  $('box').innerHTML = '<h1>登录</h1><div class="sub">快麦扫码查询 · 请用你的账号登录</div>'
    + '<label>账号</label><input id="u" type="text" autocomplete="username" value="' + esc(r.name) + '">'
    + '<label>密码</label><input id="p" type="password" autocomplete="current-password" value="' + esc(r.pw) + '">'
    + '<div class="chk"><input id="rm" type="checkbox"' + (r.name ? ' checked' : '') + '><label for="rm" style="margin:0">记住密码</label></div>'
    + '<button id="go">登录</button><div class="msg" id="m"></div>'
    + '<div class="small">同一账号同一时间只能在一台设备登录，新登录会把旧设备踢下线。</div>'
    + (d && d.local ? '<div class="small"><a href="#" id="lsetup">本机：设置 / 重置管理员账号</a></div>' : '');
  const go = async () => {
    const u = ($('u').value || '').trim(), p = $('p').value;
    if(!u || !p) return msg('err', '请输入账号和密码');
    const d = await api('/api/auth/login', {name:u, pw:p, dev_id:devId(), model:await modelName()});
    if(d.error) return msg('err', d.error);
    setToken(d.token);
    remember(u, p, $('rm').checked);
    gotoApp();
  };
  $('go').onclick = go;
  $('p').addEventListener('keydown', e => { if(e.key === 'Enter') go(); });
  const ls = $('lsetup');
  if(ls) ls.onclick = ev => { ev.preventDefault(); setupView({local:true, need_setup:false}); };
}
function homeView(d){
  const isAdmin = d.role === 'admin';
  $('box').innerHTML = '<h1>已登录</h1><div class="sub">当前账号：' + esc(d.user)
    + '（' + (isAdmin ? '管理员' : '普通账号') + '）</div>'
    + '<button id="enter">进入查询页</button>'
    + '<button class="ghost" id="out" style="margin-top:10px">退出登录</button>'
    + (isAdmin ? ('<div class="sep"></div><h1 style="font-size:17px">账号管理</h1>'
       + '<div class="sub">可以添加 / 删除账号、改密码、踢下线（被踢的设备 10 分钟内不能再登录）</div><div id="ulist"></div>'
       + '<label>新账号</label><input id="nu" type="text" placeholder="账号名">'
       + '<label>新密码</label><input id="np" type="password" placeholder="至少 4 位">'
       + '<button id="add" style="margin-top:14px">添加账号</button><div class="msg" id="m"></div>') : '');
  $('enter').onclick = () => gotoApp();
  $('out').onclick = async () => { await api('/api/auth/logout', {}); setToken(''); location.href = '/login'; };
  if(isAdmin){
    renderUsers(d.users || []);
    $('add').onclick = async () => {
      const u = $('nu').value.trim(), p = $('np').value;
      if(!u || !p) return msg('err', '账号和密码不能为空');
      const r = await api('/api/users', {action:'add', name:u, pw:p});
      if(r.error) return msg('err', r.error);
      msg('ok', '已添加 ' + u);
      $('nu').value = ''; $('np').value = '';
      renderUsers(r.users || []);
    };
  }
}
function renderUsers(us){
  const box = $('ulist');
  if(!box) return;
  box.innerHTML = us.map(u =>
    '<div class="rowline"><span>' + esc(u.name)
    + (u.role === 'admin' ? ' <span class="badge admin">管理员</span>' : '')
    + ' <span class="badge' + (u.online ? ' on' : '') + '">' + (u.online ? '在线' : '离线') + '</span>'
    + '<div class="small" style="margin:0">最近登录：' + esc(u.last_login || '—')
    + (u.device ? '　登录设备：' + esc(u.device.slice(0, 30)) : '')
    + (u.kicked_at ? '　（已踢下线）' : '') + '</div></span>'
    + '<span style="display:flex;gap:6px;flex:0 0 auto">'
    + '<button class="ghost mini" data-pw="' + esc(u.name) + '">改密码</button>'
    + ((ME && ME.user === u.name) ? '' : '<button class="ghost mini" data-kick="' + esc(u.name) + '">踢下线</button>')
    + '<button class="ghost mini" data-del="' + esc(u.name) + '">删除</button></span></div>').join('')
    || '<div class="small">还没有账号</div>';
  box.querySelectorAll('button[data-del]').forEach(b => {
    b.onclick = async () => {
      const n = b.dataset.del;
      if(!confirm('删除账号 ' + n + ' ？')) return;
      const r = await api('/api/users', {action:'del', name:n});
      if(r.error) return msg('err', r.error);
      msg('ok', '已删除 ' + n);
      renderUsers(r.users || []);
    };
  });
  box.querySelectorAll('button[data-pw]').forEach(b => {
    b.onclick = async () => {
      const n = b.dataset.pw;
      const p = prompt('给「' + n + '」设置新密码（至少 4 位）');
      if(p === null) return;
      if(String(p).length < 4) return msg('err', '密码至少 4 位');
      const r = await api('/api/users', {action:'passwd', name:n, pw:p});
      if(r.error) return msg('err', r.error);
      msg('ok', '已改密码：' + n + (n === (ME && ME.user) ? '' : '（那台设备 10 分钟内不能再登录）'));
      renderUsers(r.users || []);
    };
  });
  box.querySelectorAll('button[data-kick]').forEach(b => {
    b.onclick = async () => {
      const n = b.dataset.kick;
      if(!confirm('把「' + n + '」踢下线？那台设备 10 分钟内不能再登录')) return;
      const r = await api('/api/users', {action:'kick', name:n});
      if(r.error) return msg('err', r.error);
      msg('ok', '已踢下线：' + n);
      renderUsers(r.users || []);
    };
  });
}
function msg(kind, text){
  const m = $('m'); if(!m) return;
  m.className = 'msg ' + kind; m.textContent = text;
}
/* 会话失效（在别处登录）→ 回登录页 */
const _f = window.fetch;
window.fetch = function(u, o){
  return _f(u, o).then(r => { if(r.status === 401 && location.pathname !== '/login'){ location.href = '/login'; } return r; });
};
boot();
</script>
</body></html>
"""
