# kuaimai发货查询

快麦 ERP 待发货数量 / 货架在架数 扫码查询工具。包含**电脑版（Tkinter 桌面程序）**和**手机网页版（内嵌 HTTP 服务 + HTTPS 入口，手机摄像头扫码）**。

> **注意：本仓库不含任何真实凭据。** 程序**不带默认密钥**：首次运行会弹出「API 设置」窗口填写 AppKey / AppSecret / RefreshToken / SessionId，保存到程序同目录的 `kuaimai_api.json`（已被 `.gitignore` 忽略）。可先在窗口里点「测试连接」验证再保存。**不要把真实值提交上来。**

## 功能

- 扫商家编码 → 结果面板显示：编码（黑色加粗）/ **待发货一单一件** / **待发货一单多件** / **货位（含在架数）**；在架少于待发货件数时红字提示**需补货**
- **编码不分大小写**（`9681-黑色s` 与 `9681-黑色S` 等价）
- 声音提示（有待发货订单 = 好听的提示音；无/异常 = 报警音）
- **后台扫码监听**：程序最小化或切到别的软件时也能扫，右下角弹浮窗显示结果（不抢焦点，10 秒自动消失）
- 单实例保护（第二个实例只弹提示，不会抢同一个数据库）
- 订单商品数量筛选（> / < / = N）
- 订单缓存用 **SQLite**（`kuaimai_data.db`），全量拉取事务内整体替换、增量按 sid UPSERT；拉取失败或结果为空**绝不覆盖**已有数据
- 扫码记录、导出 CSV（手机端）/ Excel（电脑端）
- **API 设置**窗口：换账号 / 换网关 / 换 API 版本不用重新打包
- 手机网页版：局域网/外网访问，手机**摄像头扫码**（也可用扫码枪或手动输入）
- **批次查询**：输入打印批次号 → 按**打印顺序**列出该批次（编码 / 件数 / 货位 / 在架），另有「按单」「按货位汇总」「按分区」「明细表」多个视图；也可直接读 ERP 导出的 xlsx / csv
- **手机拣货页**（`/pick`）：**一张快递单一张卡**（单内多商品逐个打勾 0/N → N/N）、同 SKU 多件只算一行一次点完、**语音播报**（分区 + 编码逐位念 + 件数）、拣货完成 / 无货（无货位时显示「无货位」）、进度持久化（退出页面、重启程序都能续上）、待拣按**快递单号**统计、可手选分区 A/B/C/D 优先拣
- **主编码系列查询**：输入主编码（如 `9687`）→ 列出该主编码下**全部规格**的货位/在架/待发货/锁定；输入完整编码（`9687-黑色S`）仍只查这一个

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

1. 运行 `python desktop/kuaimai_scan.py`（源码里**不含任何密钥**）。
2. 首次运行会弹出「**API 设置**」窗口：填 appKey / appSecret / refreshToken / sessionId(accessToken) 四项，可先点「测试连接」验证，再点「保存并应用」。
   参数保存在程序同目录的 `kuaimai_api.json`（不建议提交，已加入 `.gitignore`）。
3. 保存后自动开始「全量拉取」（约 20 分钟，界面有进度）；数据落在同目录的 `kuaimai_data.db`（SQLite）。
4. 程序在 `0.0.0.0:8790`（同时监听 IPv6）提供手机网页服务，界面底部会显示访问地址和访问口令。

打包 exe（可选）：

```bash
python -m PyInstaller --noconfirm --onefile desktop/kuaimai_scan.py
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

## 拣货（手机端）

手机打开 `http://<本机IP>:8790/pick?k=口令`（走 HTTPS 入口同理：`https://<域名>/pick?k=口令`）：

1. 输入**打印批次号** → 开始拣货（服务端调 `erp.trade.trace.list` 反查该批次订单，再批量取订单明细）
2. **一张快递单一张卡**：卡上列出该单所有商品（序号 · 编码 · 需拣件数 · 货位 · 状态）；顶栏显示进度（待拣货 N **单**（按快递单号）/ 共 X 个商品 / 已拣 Y 个商品）
3. **逐个商品打勾**：一单 4 个商品 → 按钮显示进度（0/4 → 4/4），点 4 次；**同一 SKU 买 10 件只算一行，一次点完**；缺货点「无货」（没有货位时按钮显示「无货位」）
4. 进页 / 每点一次都有**语音播报**（分区 + 编码逐位念 + 件数，多商品单会报“第 k/L 个”）；可切按打印顺序或按分区、手选先拣 A/B/C/D（或含「无货位」那类）
5. 进度存在程序端 SQLite 的 `pick_batch` 表：**退出页面、关浏览器、重启程序都能续上**，点「结束批次」才结束；同一时间只保留一个进行中批次
6. 「按货位汇总」看按货位的归类；「重新拉取」按最新数据重建该批次（会清掉已拣状态）

相关接口（本机内网用，自带访问口令校验）：

```
GET /api/pick/list?batch=<批次号>&days=3[&refresh=1]   开/续一个拣货会话
GET /api/pick/current                                  查当前未结束的批次（用于自动续上）
GET /api/pick/mark?batch=<>&g=<第几单>&line=<单内第几个商品>&state=done|short|pending
GET /api/pick/end?batch=<>                             结束批次
```

> **打印批次号来自订单操作日志**：`erp.trade.trace.list` 的「打印快递单」动作，`content` 里带 `打印批次号 / 打印序号 / 第几次打印` —— 快麦开放平台**没有独立的“打印批次”接口**，而且这份日志**覆盖不完整**（实测有的批次连序号都会有缺行）。**要精确对齐请用 ERP 页面导出的文件**：电脑版「批次查询」→「读导出文件…」（支持 xlsx / csv，自动认表头）。

> 占位 / 补偿类商品（编码首段 `1166`、名称含「买家秀」「圆虹包」等）不计件数、不进拣货清单；编码比较一律忽略大小写。

## 隐私

仓库只包含程序代码。以下内容**不提交**（见 `.gitignore`）：`kuaimai_api.json`（AppKey/AppSecret/RefreshToken/SessionId）、`kuaimai_settings.json`、`aliyun/` 凭据、`lego/` 证书与账号私钥、各类 `kuaimai_*.json` 缓存、`*.db` 数据、`*.log`、打包产物。

## 第三方

`https/static/zxing.js` 来自 [@zxing/library](https://github.com/zxing-js/library) 0.21.3（Apache-2.0），仅用于本地条码解码，不依赖任何 CDN。
