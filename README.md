# kuaimai发货查询

快麦 ERP 待发货数量 / 货架在架数 扫码查询工具。包含**电脑版（Tkinter 桌面程序）**和**手机网页版（内嵌 HTTP 服务 + HTTPS 入口，手机摄像头扫码）**。

> ⚠️ 本仓库不含任何真实凭据。`desktop/kuaimai_scan.py` 里的 AppKey / AppSecret / RefreshToken / SessionId 都是占位符 `YOUR_*`，运行前需自己填写，**不要把真实值提交上来**。

## 功能

- 扫商家编码 → 查该编码的**待发货订单数**、**货架在架数**、件数、锁定数、在架货位
- 声音提示（有待发货订单 = 好听的提示音；无/异常 = 报警音）
- 订单商品数量筛选（> / < / = N）
- 扫码记录、导出 CSV
- 手机网页版：局域网/外网访问，手机**摄像头扫码**（也可用扫码枪或手动输入）

## 目录结构

```
desktop/                  电脑版（Windows 桌面程序 + 内嵌网页服务）
  kuaimai_scan.py         主程序（Tkinter GUI + 内置 HTTP 服务，端口 8790）
  kuaimai_db.py           订单缓存 SQLite 存储层
  kuaimai_webui.py        手机网页界面（打包进程序，无需 Node）
https/                    手机网页版的 HTTPS 入口（浏览器调摄像头必须 https）
  km_https.py             9443 端口 TLS 终止 → 明文转发 127.0.0.1:8790，并注入扫码增强脚本
  static/scan.js          注入的扫码逻辑（本地 ZXing 解码，不依赖 BarcodeDetector）
  static/zxing.js         第三方库 @zxing/library 0.21.3 的 UMD 构建（Apache-2.0）
  lego_run.ps1            用本地凭据文件调用 lego 申请/续期证书
  fill_accesskey.ps1      引导把阿里云 AccessKey 填进本地文件（不打印内容）
  allow_9443.ps1          放行 9443 入站（自动 UAC 提权）
  renew_cert.cmd          证书续期入口（给计划任务调用）
  certinfo.py             打印证书域名/有效期/链
  _selftest.py            HTTPS 中转自测（临时自签证书 + 桩后端）
  _zxing_selftest.js      ZXing 1D 解码自测（自造 Code39 位图往返）
```

## 电脑版

依赖：Python 3.10+（仅标准库 + tkinter，无第三方包）。

1. 打开 `desktop/kuaimai_scan.py`，填好文件顶部 `【配置区域】` 的 `KM_APP_KEY` / `KM_APP_SECRET` / `KM_REFRESH_TOKEN` / `INIT_SESSION_ID`。
2. 运行 `python kuaimai_scan.py`。
3. 程序启动后会在 `0.0.0.0:8790`（同时监听 IPv6）提供手机网页服务，界面底部会显示访问地址和访问口令。

打包 exe（可选）：

```bash
python -m PyInstaller --noconfirm --onefile kuaimai_scan.py
```

## 手机网页版（为什么需要 HTTPS）

浏览器只在**安全上下文**（`https://` 或 `localhost`）下才提供 `navigator.mediaDevices`，所以直接用 `http://<IP>:8790/` 打开网页时，「摄像头扫码」一定失败。

`https/km_https.py` 的做法是在本机另开一个 **9443** 端口做 TLS 终止，其余路径明文转发给 `127.0.0.1:8790`，因此**不需要改动 exe 或主程序**：

```
手机浏览器 ──https──> 本机 9443（km_https.py）──http──> 127.0.0.1:8790（内嵌服务）
```

额外作用：注入 `static/scan.js`，把「摄像头扫码」换成**本地 ZXing 解码**。因为部分手机浏览器（国产 ROM 浏览器、微信内置）会把 `BarcodeDetector` 暴露成空壳，表现是「摄像头能开但永远扫不出」。

证书用 [lego](https://github.com/go-acme/lego) + 阿里云 DNS API（DNS-01）申请 Let's Encrypt 证书，支持自动续期。

```bash
# 1) 准备凭据（两个纯文本文件，只放密钥本身）
#    https/lego/aliyun/access_key.txt        <- AccessKey ID
#    https/lego/aliyun/access_key_secret.txt <- AccessKey Secret
#    阿里云 RAM 子账号，只需授权 AliyunDNSFullAccess

# 2) 申请证书
powershell -File https/lego_run.ps1 issue     # 也可填 status / renew

# 3) 放行 9443（需管理员）
powershell -File https/allow_9443.ps1

# 4) 启动 HTTPS 入口
python https/km_https.py
```

自测：

```bash
python https/_selftest.py        # TLS 终止 / 转发 / 查询串透传 / 明文拒绝
node  https/_zxing_selftest.js   # ZXing 1D 解码往返
```

### 几个已踩过的坑

- **lego 的 DNS 传播校验**默认用 `1.1.1.1:53`，国内网络常不可达 → 必须加 `--dns.resolvers 223.5.5.5:53 --dns.resolvers 223.6.6.6:53`。
- **别用 `blur()` 收输入法**：`blur()` 会让页面滚动/重排，手机浏览器会把滚出视口的 `<video>` 停止送帧，ZXing 拿不到新帧就永远识别不到。用 `inputmode="none"` 代替。
- **解码回调可能早于 `decodeFromConstraints` 的 Promise 返回**，那时 `controls` 还是 `null`，`controls.stop()` 停不掉扫描循环 → 会每帧重复查询。要先同步置位一个 `handled` 标记丢弃后续帧，Promise 晚到时就地 `stop()`。
- **`.ps1` 必须带 UTF-8 BOM**，否则中文会被按 ANSI 解析导致语法错；`.cmd` 要么纯 ASCII 只做启动器，要么存成 GBK。

## 隐私

仓库只包含程序代码。以下内容**不提交**（见 `.gitignore`）：`kuaimai_settings.json`、`aliyun/` 凭据、`lego/` 证书与账号私钥、各类 `kuaimai_*.json` 缓存、`*.db` 数据、`*.log`、打包产物。

## 第三方

`https/static/zxing.js` 来自 [@zxing/library](https://github.com/zxing-js/library) 0.21.3（Apache-2.0），仅用于本地条码解码，不依赖任何 CDN。
