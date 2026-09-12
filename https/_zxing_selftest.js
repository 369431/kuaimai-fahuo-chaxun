// _zxing_probe.js - 定位解码失败原因
// 关键疑点：ZXing JS 的 RGBLuminanceSource 期望「每像素 1 字节亮度」，
// 传 RGBA（每像素 4 字节）会让行跨度变成 4 倍宽 → 必然解不出来。
process.on('uncaughtException', function (e) {
  console.log('UNCAUGHT: ' + String(e && e.message).slice(0, 200));
  process.exit(1);
});
process.on('unhandledRejection', function (e) {
  console.log('REJECTED: ' + String(e && e.message).slice(0, 200));
  process.exit(1);
});

const path = require('path');
const ZXing = require(path.join(__dirname, 'static', 'zxing.js'));

const C39 = {
  '0': 'nnnwwnwnn', '1': 'wnnwnnnnw', '2': 'nnwwnnnnw', '3': 'wnwwnnnnn', '4': 'nnnwwnnnw',
  '5': 'wnnwwnnnn', '6': 'nnwwwnnnn', '7': 'nnnwnnwnw', '8': 'wnnwnnwnn', '9': 'nnwwnnwnn',
  'A': 'wnnnnwnnw', 'B': 'nnwnnwnnw', 'C': 'wnwnnwnnn', 'D': 'nnnnwwnnw', 'E': 'wnnnwwnnn',
  'F': 'nnwnwwnnn', 'G': 'nnnnnwwnw', 'H': 'wnnnnwwnn', 'I': 'nnwnnwwnn', 'J': 'nnnnwwwnn',
  'K': 'wnnnnnnww', 'L': 'nnwnnnnww', 'M': 'wnwnnnnwn', 'N': 'nnnnwnnww', 'O': 'wnnnwnnwn',
  'P': 'nnwnwnnwn', 'Q': 'nnnnnnwww', 'R': 'wnnnnnwwn', 'S': 'nnwnnnwwn', 'T': 'nnnnwnwwn',
  'U': 'wwnnnnnnw', 'V': 'nwwnnnnnw', 'W': 'wwwnnnnnn', 'X': 'nwnnwnnnw', 'Y': 'wwnnwnnnn',
  'Z': 'nwwnwnnnn', '-': 'nwnnnnwnw', '.': 'wwnnnnwnn', ' ': 'nwwnnnwnn', '$': 'nwnwnwnnn',
  '/': 'nwnwnnnwn', '+': 'nwnnnwnwn', '%': 'nnnwnwnwn', '*': 'nwnnwnwnn',
};

function build(text, wideUnits, quiet, height) {
  const seq = [];
  for (const ch of ('*' + text + '*')) {
    const pat = C39[ch];
    if (!pat) throw new Error('unsupported char ' + ch);
    for (let i = 0; i < 9; i++) seq.push(pat[i] === 'w' ? wideUnits : 1);
    seq.push(1);
  }
  const width = quiet * 2 + seq.reduce(function (a, b) { return a + b; }, 0);
  const rows = [];
  for (let y = 0; y < height; y++) {
    const row = new Uint8Array(width).fill(1);
    let x = quiet;
    for (let i = 0; i < seq.length; i++) {
      if (i % 2 === 0) for (let k = 0; k < seq[i]; k++) row[x + k] = 0;
      x += seq[i];
    }
    rows.push(row);
  }
  return { rows: rows, width: width, height: height };
}

function toBitmap(img, asRGB) {
  const n = img.width * img.height;
  let buf;
  if (asRGB) {
    buf = new Uint8ClampedArray(n * 4);
    for (let y = 0; y < img.height; y++) {
      for (let x = 0; x < img.width; x++) {
        const v = img.rows[y][x] ? 255 : 0;
        const i = (y * img.width + x) * 4;
        buf[i] = v; buf[i + 1] = v; buf[i + 2] = v; buf[i + 3] = 255;
      }
    }
  } else {
    buf = new Uint8ClampedArray(n);
    for (let y = 0; y < img.height; y++) {
      for (let x = 0; x < img.width; x++) buf[y * img.width + x] = img.rows[y][x] ? 255 : 0;
    }
  }
  const src = new ZXing.RGBLuminanceSource(buf, img.width, img.height);
  return new ZXing.BinaryBitmap(new ZXing.HybridBinarizer(src));
}

function tryIt(label, fn) {
  try {
    console.log('OK   ' + label + ' -> ' + fn());
  } catch (e) {
    const nm = (e && e.constructor && e.constructor.name) || typeof e;
    const msg = (e && e.message) ? e.message : String(e);
    console.log('ERR  ' + label + ' -> [' + nm + '] ' + String(msg).slice(0, 90));
  }
}

const TEXT = 'SP-8866';
for (const asRGB of [true, false]) {
  const img = build(TEXT, 3, 30, 120);
  console.log('--- 输入=' + (asRGB ? 'RGBA(4字节/像素)' : '亮度(1字节/像素)') + '  ' + img.width + 'x' + img.height + ' ---');
  tryIt('Code39Reader', function () { return new ZXing.Code39Reader().decode(toBitmap(img, asRGB)).getText(); });
  tryIt('MultiFormatOneDReader', function () { return new ZXing.MultiFormatOneDReader(new Map()).decode(toBitmap(img, asRGB)).getText(); });
  tryIt('MultiFormatReader+hints', function () {
    const h = new Map();
    h.set(ZXing.DecodeHintType.POSSIBLE_FORMATS, [ZXing.BarcodeFormat.CODE_128, ZXing.BarcodeFormat.CODE_39, ZXing.BarcodeFormat.EAN_13]);
    const r = new ZXing.MultiFormatReader(); r.setHints(h);
    return r.decode(toBitmap(img, asRGB)).getText();
  });
}
