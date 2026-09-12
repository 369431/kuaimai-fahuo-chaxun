/* scan.js - 扫码增强层：用本地 ZXing 解码，不依赖浏览器的 BarcodeDetector。
   由 km_https.py 注入到快麦网页末尾（只影响 9443 这个 HTTPS 入口；原 8790 页面不变）。

   为什么需要：部分手机浏览器会把 BarcodeDetector 暴露成空壳，或对 <video> 解码不工作，
   表现就是「摄像头能开，但永远扫不出」。ZXing 是纯 JS 解码，只要能开摄像头就能用。

   行为：一次扫码 = 一次查询，识别到就立刻停摄像头。
   （竞态说明：解码回调可能早于 decodeFromConstraints 的 Promise 返回，
     那时 controls 还是 null，光靠 controls.stop() 停不掉循环，会一帧一次重复查询。
     所以用 handled 先置位丢弃后续回调，Promise 晚到时就地停掉。）

   收键盘：网页的 query() 结尾有 $('code').focus()，手机上 focus 输入框会弹输入法。
   ★ 不能用 blur() 去收 —— blur 会让页面滚动/重排，手机浏览器会把滚出画面的 <video>
     停止送帧，ZXing 拿不到新帧就永远识别不到（踩过这个坑）。
   改用 inputmode="none"：只让输入框不唤起输入法，不碰焦点、不引起滚动。
   用户点输入框时自动恢复，不影响手输。
*/
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var btn = $('btnCam'), stopBtn = $('btnCamStop'), video = $('video'), box = $('camBox');
  if (!btn || !video || !box) return;

  // ---- 页面上的状态条（方便你和我看到到底走到哪一步）----
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
  var busy = false;      // 摄像头是否正在扫
  var handled = false;   // 本次是否已经识别到（丢弃后续帧）
  var lastCode = '', lastAt = 0, DEDUP_MS = 2500;
  var unmuteTimer = null;

  // ---- 输入法抑制（不用 blur）----
  var codeEl = $('code');
  var savedInputMode = codeEl ? codeEl.getAttribute('inputmode') : null;
  var kbMuted = false;

  function muteKeyboard() {
    if (!codeEl || kbMuted) return;
    kbMuted = true;
    codeEl.setAttribute('inputmode', 'none');   // 焦点还在输入框里，但不弹输入法
    codeEl.setAttribute('autocomplete', 'off');
  }

  function unmuteKeyboard() {
    if (!codeEl || !kbMuted) return;
    kbMuted = false;
    if (savedInputMode === null) codeEl.removeAttribute('inputmode');
    else codeEl.setAttribute('inputmode', savedInputMode);
  }

  if (codeEl) {
    // 用户自己点输入框（想手输/扫码枪）时恢复
    codeEl.addEventListener('pointerdown', unmuteKeyboard, true);
    codeEl.addEventListener('touchstart', unmuteKeyboard, true);
  }

  var hints = new Map();
  hints.set(ZX.DecodeHintType.POSSIBLE_FORMATS, [
    ZX.BarcodeFormat.CODE_128, ZX.BarcodeFormat.CODE_39, ZX.BarcodeFormat.CODE_93,
    ZX.BarcodeFormat.ITF, ZX.BarcodeFormat.EAN_13, ZX.BarcodeFormat.EAN_8,
    ZX.BarcodeFormat.UPC_A, ZX.BarcodeFormat.UPC_E,
    ZX.BarcodeFormat.QR_CODE, ZX.BarcodeFormat.DATA_MATRIX
  ]);

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
  }

  function stop(msg) {
    handled = false;
    if (unmuteTimer) { clearTimeout(unmuteTimer); unmuteTimer = null; }
    unmuteKeyboard();
    teardown();
    say(msg || '已停止。');
  }

  function onResult(result, err) {
    if (handled) return;                       // 已识别，后续帧一律忽略
    if (result) {
      var code = result.getText();
      if (!code) return;
      var now = Date.now();
      if (code === lastCode && (now - lastAt) < DEDUP_MS) return;   // 同一条码短时间内不重复
      lastCode = code;
      lastAt = now;
      handled = true;                          // 先置位（同步），再停
      say('识别到：' + code, '#1e9e4a');
      teardown();
      try { window.query(code); } catch (e) { }
      // query() 结尾的 focus() 被 inputmode=none 挡住，不会弹输入法；
      // 1.5 秒后恢复，用户想手输时也随时能点开。
      if (unmuteTimer) clearTimeout(unmuteTimer);
      unmuteTimer = setTimeout(function () { unmuteTimer = null; unmuteKeyboard(); }, 1500);
    } else if (err && !(err instanceof ZX.NotFoundException)) {
      say('解码异常：' + (err && err.message ? err.message : String(err)), '#c62828');
    }
  }

  function start() {
    if (busy) { stop(); return; }              // 正在扫，再点一次＝停止
    handled = false;
    box.classList.remove('hidden');
    say('正在打开摄像头…');
    muteKeyboard();                            // 扫完后不弹输入法（不 blur，避免视频被挂起）
    var reader = new ZX.BrowserMultiFormatReader(hints, { delayBetweenScanAttempts: 150 });
    reader.decodeFromConstraints(
      { video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } } },
      video,
      onResult
    ).then(function (c) {
      if (handled) { try { c.stop(); } catch (e) { } return; }   // 回调先抢到结果了，就地停掉
      controls = c;
      busy = true;
      say('摄像头已开启（本地 ZXing 解码）。把条码横向放进画面、离 10-20cm，扫到即停。');
    }).catch(function (e) {
      busy = false;
      unmuteKeyboard();
      say('打开摄像头失败：' + (e && e.message ? e.message : String(e)), '#c62828');
    });
  }

  btn.onclick = start;
  if (stopBtn) stopBtn.onclick = function () { stop(); };
  console.log('[km] ZXing 增强扫码已接管「摄像头扫码」按钮（一次扫码＝一次查询；inputmode 收键盘）');
})();
