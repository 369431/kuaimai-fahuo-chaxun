/* scan.js - 扫码增强层：用本地 ZXing 解码，不依赖浏览器的 BarcodeDetector。
   由 km_https.py 注入到快麦网页末尾（只影响 9443 这个 HTTPS 入口；原 8790 页面不变）。

   行为：一次扫码 = 一次查询，识别到就立刻停摄像头。

   ── v11（回退速度／修黑屏，保留放大补光）──
   1) 分辨率回退到 1280×720：v10 提到 1920×1080 后每帧像素多一倍，实测**解码变慢**，
      识别率也没有提升（条码大字反而更吃 CPU）。慢/不准 → 先回这个值。
   2) TRY_HARDER 回退到 3 秒（v10 提前到 1.5 秒反而更吃 CPU、拖慢前 1.5 秒的识别）。
   3) 保留 v10 的「放大 2×」「补光」按钮（纯增益，按机身能力显示）。
   4) 修「先黑屏一下再撑开」：注入 CSS 给 #camBox/#video 预留固定高度，
      摄像头画面出现时布局不再跳一下，黑屏时间也短了。

   ── 已踩过的坑（别改回去）──
   • 不能用 blur() 收键盘：会让页面滚动/重排，手机浏览器把滚出视口的 <video> 停止送帧，
     ZXing 拿不到新帧就永远识别不到。改用 inputmode="none"。
   • 解码回调可能早于 decodeFromConstraints 的 Promise 返回，那时 controls 还是 null，
     controls.stop() 停不掉循环 → 会每帧重复查询。先同步置位 handled 丢弃后续帧。
   • BrowserMultiFormatReader 没有 setHints()（v8 踩过），要改码制只能改内部 reader.setHints()。
   • 分辨率不是越高越好：1280×720 → 1920×1080 实测更慢且更不准（v11 回退）。
*/
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var btn = $('btnCam'), stopBtn = $('btnCamStop'), video = $('video'), box = $('camBox');
  if (!btn || !video || !box) return;

  // 预留摄像头区域高度：避免画面出现时布局跳一下（"先黑屏再撑开"）
  try {
    var st = document.createElement('style');
    st.textContent = '#camBox{min-height:240px;background:#000;border-radius:12px;overflow:hidden}'
      + '#camBox.hidden{min-height:0;background:transparent}'
      + '#video{display:block;width:100%;min-height:240px;background:#000}';
    document.head.appendChild(st);
  } catch (e) { }

  // ---- 状态条 ----
  var bar = document.createElement('div');
  bar.id = 'kmScanBar';
  bar.style.cssText = 'margin-top:6px;font-size:12px;line-height:1.6;white-space:pre-wrap;word-break:break-all;color:#444';
  box.parentNode.insertBefore(bar, box.nextSibling);
  function say(msg, color) { bar.style.color = color || '#444'; bar.textContent = msg; }
  window.__kmSay = say;

  var ZX = window.ZXing;
  if (!ZX || !ZX.BrowserMultiFormatReader) {
    say('ZXing 没加载成功，仍用浏览器自带的 BarcodeDetector。', '#c62828');
    return;
  }

  var controls = null;
  var busy = false;
  var handled = false;
  var lastCode = '', lastAt = 0, DEDUP_MS = 2500;
  var unmuteTimer = null, statTimer = null;
  var attempts = 0, startedAt = 0, tier = 1, tierTimer = null;
  var TIER2_AFTER = 3000;                  // 3 秒还没有结果才加 TRY_HARDER
  var track = null, caps = {}, zoomOn = false, torchOn = false;

  // ---- 输入法抑制（不用 blur）----
  var codeEl = $('code');
  var savedInputMode = codeEl ? codeEl.getAttribute('inputmode') : null;
  var kbMuted = false;

  function muteKeyboard() {
    if (!codeEl || kbMuted) return;
    kbMuted = true;
    codeEl.setAttribute('inputmode', 'none');
    codeEl.setAttribute('autocomplete', 'off');
  }
  function unmuteKeyboard() {
    if (!codeEl || !kbMuted) return;
    kbMuted = false;
    if (savedInputMode === null) codeEl.removeAttribute('inputmode');
    else codeEl.setAttribute('inputmode', savedInputMode);
  }
  if (codeEl) {
    codeEl.addEventListener('pointerdown', unmuteKeyboard, true);
    codeEl.addEventListener('touchstart', unmuteKeyboard, true);
  }

  // ---- 码制 ----
  var ONE_D = [
    ZX.BarcodeFormat.CODE_128, ZX.BarcodeFormat.CODE_39,
    ZX.BarcodeFormat.CODE_93, ZX.BarcodeFormat.ITF
  ];
  var MORE = [ZX.BarcodeFormat.EAN_13, ZX.BarcodeFormat.EAN_8,
    ZX.BarcodeFormat.UPC_A, ZX.BarcodeFormat.UPC_E,
    ZX.BarcodeFormat.QR_CODE, ZX.BarcodeFormat.DATA_MATRIX];

  function hintsFor(list, hard) {
    var h = new Map();
    h.set(ZX.DecodeHintType.POSSIBLE_FORMATS, list);
    if (hard) h.set(ZX.DecodeHintType.TRY_HARDER, true);
    return h;
  }

  // ---- 补光 / 放大 ----
  var extra = document.createElement('div');
  extra.id = 'kmScanExtra';
  extra.style.cssText = 'margin-top:5px;display:flex;gap:6px;flex-wrap:wrap';
  box.parentNode.insertBefore(extra, bar.nextSibling);

  function apply(key, val) {
    if (!track || !track.applyConstraints) return false;
    try {
      var adv = {};
      adv[key] = val;
      track.applyConstraints({ advanced: [adv] });
      return true;
    } catch (e) { return false; }
  }

  function mkBtn(text, fn) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'ghost';
    b.textContent = text;
    b.onclick = fn;
    extra.appendChild(b);
    return b;
  }

  function refreshExtras() {
    extra.innerHTML = '';
    if (caps.zoom) {
      mkBtn(zoomOn ? '放大 关' : '放大 2×', function () {
        zoomOn = !zoomOn;
        var z = zoomOn ? Math.min(2, (caps.zoom && caps.zoom.max) || 2) : ((caps.zoom && caps.zoom.min) || 1);
        apply('zoom', z);
        refreshExtras();
        say(zoomOn ? '已放大（扫远处小码用），再点一次关掉。' : '已恢复原倍率。');
      });
    }
    if (caps.torch) {
      mkBtn(torchOn ? '补光 关' : '补光', function () {
        torchOn = !torchOn;
        var ok = apply('torch', torchOn);
        refreshExtras();
        say(ok ? (torchOn ? '已打开补光。' : '已关闭补光。') : '这台机器的摄像头不支持补光。',
            ok ? '#444' : '#c62828');
      });
    }
    extra.style.display = (caps.zoom || caps.torch) ? '' : 'none';
  }

  function grabTrack() {
    try {
      var s = video.srcObject;
      track = (s && s.getVideoTracks) ? s.getVideoTracks()[0] : null;
    } catch (e) { track = null; }
    try { caps = (track && track.getCapabilities) ? (track.getCapabilities() || {}) : {}; } catch (e) { caps = {}; }
    refreshExtras();
  }

  function teardown() {
    busy = false;
    var c = controls;
    controls = null;
    if (c) { try { c.stop(); } catch (e) { } }
    var s = video.srcObject;
    if (s) {
      try { s.getTracks().forEach(function (t) { t.stop(); }); } catch (e) { }
      video.srcObject = null;
    }
    try { if (typeof window.stopCam === 'function') window.stopCam(); } catch (e) { }
    if (statTimer) { clearInterval(statTimer); statTimer = null; }
    if (tierTimer) { clearTimeout(tierTimer); tierTimer = null; }
    track = null; caps = {}; zoomOn = false; torchOn = false;
    extra.innerHTML = '';
  }

  function stop(msg) {
    handled = false;
    if (unmuteTimer) { clearTimeout(unmuteTimer); unmuteTimer = null; }
    unmuteKeyboard();
    teardown();
    say(msg || '已停止。');
  }

  function onResult(result, err) {
    if (handled) return;
    attempts++;
    if (result) {
      var code = result.getText();
      if (!code) return;
      var now = Date.now();
      if (code === lastCode && (now - lastAt) < DEDUP_MS) return;
      lastCode = code;
      lastAt = now;
      handled = true;
      var secs = ((now - startedAt) / 1000).toFixed(1);
      say('识别到：' + code + '（用时 ' + secs + ' 秒，尝试 ' + attempts + ' 次）', '#1e9e4a');
      teardown();
      try { window.query(code); } catch (e) { }
      if (unmuteTimer) clearTimeout(unmuteTimer);
      unmuteTimer = setTimeout(function () { unmuteTimer = null; unmuteKeyboard(); }, 1500);
    } else if (err && !(err instanceof ZX.NotFoundException)) {
      say('解码异常：' + (err && err.message ? err.message : String(err)), '#c62828');
    }
  }

  function start() {
    if (busy) { stop(); return; }
    handled = false;
    attempts = 0;
    startedAt = Date.now();
    tier = 1;
    box.classList.remove('hidden');
    say('正在打开摄像头…');
    muteKeyboard();

    var reader = new ZX.BrowserMultiFormatReader(
      hintsFor(ONE_D.concat(MORE), false),
      0                                   // 尝试间隔 0 = 每帧都试
    );

    reader.decodeFromConstraints(
      {
        video: {
          facingMode: { ideal: 'environment' },
          width: { ideal: 1280 },         // v11：回退到 720p（1080p 实测更慢更不准）
          height: { ideal: 720 },
          advanced: [{ focusMode: 'continuous' }]
        }
      },
      video,
      onResult
    ).then(function (c) {
      if (handled) { try { c.stop(); } catch (e) { } return; }
      controls = c;
      busy = true;
      grabTrack();

      // 3 秒还没结果 → 才加 TRY_HARDER（提前开会拖慢前几秒）
      tierTimer = setTimeout(function () {
        if (!busy || handled) return;
        tier = 2;
        try {
          var inner = reader.reader;
          if (inner && typeof inner.setHints === 'function') {
            inner.setHints(hintsFor(ONE_D.concat(MORE), true));
          }
        } catch (e) { }
      }, TIER2_AFTER);

      statTimer = setInterval(function () {
        if (!busy || handled) return;
        var secs = (Date.now() - startedAt) / 1000;
        var rate = secs > 0.5 ? (attempts / secs).toFixed(0) : '-';
        say('扫描中… 已尝试 ' + attempts + ' 次 · 约 ' + rate + ' 次/秒'
          + (tier === 2 ? '（已开 TRY_HARDER）' : '')
          + '\n扫不出时：❶ 条码横向、占画面一半 ❷ 前后挪到 10-20cm ❸ 点「放大 2×」或「补光」');
      }, 1000);
    }).catch(function (e) {
      busy = false;
      unmuteKeyboard();
      say('打开摄像头失败：' + (e && e.message ? e.message : String(e)), '#c62828');
    });
  }

  btn.onclick = start;
  if (stopBtn) stopBtn.onclick = function () { stop(); };
  console.log('[km] ZXing 增强扫码已接管「摄像头扫码」（v11：720p 回退 + 放大/补光 + 3s TRY_HARDER + 预留高度不跳版）');
})();
