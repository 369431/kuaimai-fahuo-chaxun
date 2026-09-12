/* scan.js - 扫码增强层：用本地 ZXing 解码，不依赖浏览器的 BarcodeDetector。
   由 km_https.py 注入到快麦网页末尾（只影响 9443 这个 HTTPS 入口；原 8790 页面不变）。

   行为：一次扫码 = 一次查询，识别到就立刻停摄像头。

   ── 识别速度（v8 起）──
   1) 码制：v8 原本想「先只试一维码（CODE_128/39/93/ITF），3 秒没结果再自动加上
      EAN/UPC/二维码/DataMatrix」——但 BrowserMultiFormatReader 根本没有 setHints() 方法
      （实测 prototype 与实例上都是 undefined），那句调用抛异常又被 catch 吞掉，
      结果永远只试 4 种一维码，二维码/EAN 类**完全识别不出**（v9 修复）。
      现在：一开始就带上全部码制（= v8 之前能用的行为），3 秒后只额外开 TRY_HARDER。
   2) 取消尝试间隔：原来每次尝试之间强制 delay 150ms，等于每秒最多试 6 次；
      现在设为 0，等于每帧都试一次。
   3) 对焦：加 focusMode=continuous（不支持的浏览器会忽略），减少"糊着扫不出"的时间。

   ── 已踩过的坑 ──
   • 不能用 blur() 收键盘：会让页面滚动/重排，手机浏览器把滚出视口的 <video> 停止送帧，
     ZXing 拿不到新帧就永远识别不到。改用 inputmode="none"。
   • 解码回调可能早于 decodeFromConstraints 的 Promise 返回，那时 controls 还是 null，
     controls.stop() 停不掉循环 → 会每帧重复查询。先同步置位 handled 丢弃后续帧。
*/
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var btn = $('btnCam'), stopBtn = $('btnCamStop'), video = $('video'), box = $('camBox');
  if (!btn || !video || !box) return;

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
  var TIER2_AFTER = 3000;          // 3 秒还没有结果就加上重码制

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

  // ---- 码制分级 ----
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
      0                                   // 尝试间隔 0 = 每帧都试（原来传的是对象，类型不对）
    );

    reader.decodeFromConstraints(
      {
        video: {
          facingMode: { ideal: 'environment' },
          width: { ideal: 1280 },
          height: { ideal: 720 },
          advanced: [{ focusMode: 'continuous' }]     // 不支持会被忽略
        }
      },
      video,
      onResult
    ).then(function (c) {
      if (handled) { try { c.stop(); } catch (e) { } return; }
      controls = c;
      busy = true;

      // 3 秒还没结果 → 额外打开 TRY_HARDER（码制一开始就带全了，见文件头 v9 说明）
      tierTimer = setTimeout(function () {
        if (!busy || handled) return;
        tier = 2;
        try {
          var inner = reader.reader;        // 内部真正的 MultiFormatReader
          if (inner && typeof inner.setHints === 'function') {
            inner.setHints(hintsFor(ONE_D.concat(MORE), true));
          }
        } catch (e) { /* 拿不到就算了，不影响解码 */ }
      }, TIER2_AFTER);

      // 每秒刷新一次进度，方便看"效率"
      statTimer = setInterval(function () {
        if (!busy || handled) return;
        var secs = (Date.now() - startedAt) / 1000;
        var rate = secs > 0.5 ? (attempts / secs).toFixed(0) : '-';
        say('扫描中… 已尝试 ' + attempts + ' 次 · 约 ' + rate + ' 次/秒'
          + (tier === 2 ? '（已开 TRY_HARDER）' : '')
          + '\n把条码横向放进画面、离 10-20cm，扫到即停。');
      }, 1000);
    }).catch(function (e) {
      busy = false;
      unmuteKeyboard();
      say('打开摄像头失败：' + (e && e.message ? e.message : String(e)), '#c62828');
    });
  }

  btn.onclick = start;
  if (stopBtn) stopBtn.onclick = function () { stop(); };
  console.log('[km] ZXing 增强扫码已接管「摄像头扫码」按钮（一维码优先 · 无尝试间隔 · 扫到即停）');
})();
