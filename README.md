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
- **现货可发（`/stock`，手机 + 电脑版）**：每个编码显示 **货位 / 在架数 / 待发货件数（一单一件·一单多件）/ 可发**；按款号查（`7107` → 全部 `7107-*`）；默认排序「**加急有货优先（可发多→少）**」，另有 可发/加急件数/在架/待发货/编码；筛选默认「**只看可发（>0）**」；**「已发」按钮** —— 拣完点一下本地隐藏、**所有账号共用**、拉到新数据后自动清空；一键**导出 Excel**
- **加急标记**：订单页顶部红色「加急」标 + 平台标签 + 异常明细；**拣货页加急单红框 + 「加急」徽标 + 快递单号红字**；电脑版批次清单序号前加 `★`
- **订单页（`/order`）对齐快麦 ERP 手机版版式**：订单信息（店铺名称 / 平台单号 / 系统单号 / 付款时间 / 发货仓库 / 快递公司 / 快递模板 / 快递单号 / 异常状态 / 卖家备注 / 系统备注）+ 商品行（图 / 标题 / **规格别名 / 编码 / 平台规格 / 备注** / 货位 / **成交金额**）+ 商品总数量（N 种）；**不显示运费/毛利**
- **电脑版登录 + 主/子客户端**：电脑版启动先登录（和网页端同一套账号）；**管理员账号 = 主客户端**（数据、快麦凭据都在那台电脑上），**普通账号 = 子客户端**（连局域网里的主客户端取数，本机不存快麦凭据、也不对外服务）；主账号可在「子客户端管理」里管账号 / 配权限 / 看在线设备 / 踢下线
- **加急按快递拆开**：现货可发 + 扫码结果里把**一单一件的加急**按快递拆开显示（只统计**中通 / 申通**，例：「加急·中通 3 单 申通 1 单」）；Excel 与权限页不受影响

## 目录结构

```
desktop/                  电脑版（Windows 桌面程序 + 内嵌网页服务）
  kuaimai_scan.py         主程序（Tkinter GUI + 内置 HTTP 服务，端口 8790）+ 子客户端所需接口
  kuaimai_db.py           订单缓存 SQLite 存储层
  kuaimai_webui.py        手机网页界面（打包进程序，无需 Node）
  kuaimai_auth.py         账号 / 会话 token / 踢下线（kuaimai_users.json）
  kuaimai_perms.py        权限点清单（网页端 + 桌面端共用，权限键的唯一来源）
  kuaimai_login_ui.py     网页登录页 HTML
  kuaimai_client.py       桌面端登录会话 / 局域网自动发现 / 远程接口（子客户端用）
  kuaimai_login_window.py 桌面版登录窗（本机主客户端 / 连主客户端）
  kuaimai_admin_panel.py  主账号的「子客户端管理」面板（在线设备 / 账号 / 权限）
  _selftest_login.py      登录 + 主/子客户端自检（71 项，临时目录 + 临时端口，不碰真账号文件）
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

## 登录与主/子客户端（电脑版）

电脑版启动后**先弹登录窗**，登录成功才开主界面。身份完全由登录账号决定：

| 登录账号 | 身份 | 能做什么 |
| --- | --- | --- |
| `role=admin`（管理员） | **主客户端** | 全部功能 + 账号管理 / 权限配置 / 在线设备 / 踢下线；手机网页服务、局域网广播只在这台上跑 |
| `role=user`（子账号） | **子客户端** | 只显示主账号给你开的按钮；数据实时来自主客户端；**API 设置 / 刷新数据 / 清空日志 / 读 ERP 导出文件**等主机专有功能一律置灰 |

- **主客户端那台电脑**＝跑着程序、持有数据与快麦凭据的那台（就是现在跑 `快麦扫码查询.exe` 的电脑）。
- **子客户端**：登录窗选「子客户端（连主客户端）」→「自动发现」（局域网 UDP 广播）或手写 `192.168.1.5` 这类地址 →「测试连接」→ 输账号密码。
- **首次设置 / 重置管理员密码只能在主客户端那台本机上做**（服务端只认回环地址、且没经过 HTTPS 中转）；子客户端上不可能凭空变成主客户端。
- **权限是服务端的事**：界面置灰只是体验，每个动作都走 `http://<主端>:8790` 接口，服务端按账号权限表再卡一次（无权限直接 403，且**动作一步也不执行**）。
- 同一账号同时只能在一处登录；主账号在「子客户端管理」里**踢下线**后，那台设备 10 分钟内不能再登录（登录窗会写清剩余时间）。
- 子客户端不启动本机 HTTP 服务、不广播，也不会把快麦凭据写到本机。

主账号的「子客户端管理」面板（`子客户端管理` 按钮）：

- **在线设备**：账号 / 角色 / 电脑名 / Windows 用户名 / 来源 IP / 客户端类型 / 登录时间 / 最后活跃（3 分钟内有心跳算在线），可单个踢下线
- **账号**：新增子账号 / 改密码 / 删除 / 踢下线（新登录会把旧设备顶下线）
- **权限**：按分组勾选子账号能用的按钮，支持「全选 / 全不选 / 恢复默认」

新增的桌面权限点（和网页端共用一份清单，见 `desktop/kuaimai_perms.py`）：

| 权限键 | 显示名 | 默认 |
| --- | --- | --- |
| `scan.record` | 扫码记录（查看 / 刷新） | 开 |
| `scan.printed` | 扫码记录 · 标记「已打」 | 开 |
| `batch.query` | 批次查询（按打印批次号） | 开 |
| `batch.file` | 批次查询 · 读取 ERP 导出文件 | 开 |
| `data.refresh` | 刷新数据（增量 / 全量 / 货位 / 锁定） | 关 |
| `export.excel` | 导出 Excel（扫码记录 / 批次） | 关 |
| `api.settings` | API 设置（换账号 / 换网关） | 关 |
| `stock.sent.clear` | 现货可发 · 清空已发 | 关 |
| `desktop.admin` | 子客户端管理（账号 / 权限 / 在线设备） | 关（仅管理员） |
| `gateway.settings` | 对外访问设置（域名 / frp / 证书） | 关（仅管理员） |

主客户端侧额外接口（子客户端 / 自动发现用，自带账号校验）：

```
GET  /api/ping                免登录：我是谁、端口、要不要首次设置、有没有人登录（测试连接 / 发现用）
GET  /api/devices             在线设备 + 本机（主机）信息（需 desktop.admin）
GET  /api/scans               扫码记录 JSON（需 scan.record）
GET  /api/scans/export        扫码记录 Excel（需 export.excel）
POST /api/scans/printed       标记「已打」（需 scan.printed）  body: {id, flag}
GET  /api/batch?batch=&days=  批次查询（需 batch.query）
GET  /api/stock/bins?code=    货位数量（改库存前对照，需 stock.edit 或 stock.zero）
POST /api/client/info         子客户端心跳（刷「最后活跃 / 电脑名 / Windows 用户」）
UDP  8791                     广播应答（子客户端「自动发现」，只在本机服务跑着时开）
```

> 桌面端请求都用 `X-KM-Token` 头带会话 token（不依赖 Cookie），并且**不走系统代理**——否则客户电脑上装了代理/安全软件时，局域网请求会被拐跑。

## 对外访问设置（域名 / frp / 证书）

原来这些是**安装向导**里填的（frp 服务器地址/端口/token + 证书两个文件）。现在装完也能在软件里改：
主界面「操作」区 → **对外访问设置**（仅管理员 / 主客户端可用，子客户端上直接置灰）。

- **域名 / frp 服务器地址 / 服务器端口 / frp token / 对外 HTTPS 端口 / 是否同时映射 443**
  → 存在 `kuaimai_gateway.json`，保存时按**与安装包同一套模板**重写 `frp\frpc.toml`
- **证书**：「选择 .crt 和 .key 并安装…」→ 先用 `ssl.load_cert_chain` **真校验是不是一对**（不匹配直接拒），
  再放成 `kuaimai_https\lego\certificates\<域名>.crt / .key`（域名从证书里读，Cloudflare 的 `_bundle` 后缀自动去掉）
  · 状态区显示**当前证书到期日**；剩余 < 15 天会提示；换证书不用重装
- **一键启动**：「只重启 HTTPS 中转」/「保存并重启隧道」（frpc + 中转）/「一键启动全部」/ **开机自启开关**
  （frpc 有开机自启任务 `KuaimaiFrpc` 就走任务，否则直接起进程）
- **状态区**一眼看：对外地址 `https://<域名>:9443/`、8790 / 9443 有没有在听、frpc 在不在跑、证书到期、frpc.toml 有没有

对应文件：`desktop/kuaimai_gateway.py`（逻辑）、`desktop/kuaimai_gateway_ui.py`（窗口）。

自检（无界面，临时目录 + 临时端口，不会动你的真账号/真数据库）：

```bash
python desktop/_selftest_login.py     # 71 项：登录 / 权限拦截 / 踢下线 / 发现 / 子客户端远程模式 / 主机模式
```

### 几个已踩过的坑（桌面端登录）

- **主客户端要有人登录，子客户端才连得上**：局域网广播和对外服务都在“主机模式”下才开；登录阶段的服务只绑回环（`127.0.0.1`），不会提前把 8790 暴露到局域网。
- **不能只看按钮置灰就以为安全**：拒绝必须靠服务端 `_need()` 抛 `_Denied` 在 `do_GET/do_POST` 顶层统一转 403；直接返回一个“拒绝”对象是拦不住的（`_json()` 已经把响应发出去了）。自检里专门验“被拒的动作计数没涨”。
- **Windows 上 `SO_REUSEADDR` 会“抢”端口**：自检不能用 8790，否则请求会跑到真程序那边（看起来像权限全乱）；测试一律随机挑空闲端口。
- **电脑上装了 HTTP 代理时** `urllib` 会把 `127.0.0.1`/局域网请求也发给代理（返回 502）→ 桌面端一律用 `ProxyHandler({})` 的 opener。
- **别把测试账号写进真 `kuaimai_users.json`**：自检脚本必须 `import kuaimai_scan` **之后**再改 `auth.USERS_FILE`，并在跑完比对真文件哈希（脚本里两道闸）。

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
- **打包成 exe 后 `__file__` 指向 PyInstaller 的临时解包目录**（`%TEMP%\_MEIxxxx`，每次启动都是新的、退出即删）：数据文件（账号、缓存、日志）必须用 `sys.executable` 所在目录定位，否则会「每次打开都像第一次用」。账号文件 `kuaimai_users.json` 现在跟 exe 同目录。
- **`ssl.SSLContext.wrap_socket()` 会 detach 原 socket 的 fd**：之后对原 socket 调 `getpeername()` 会报 `WinError 10038`。中转要取客户端来源 IP（用来判断"是不是本机"）必须在 wrap **之前**取。
- **中转要给后端请求头加日志时，要先起「客户端 → 后端」的转发线程再读响应头**：否则 POST 的请求体还没送到后端、后端在等请求体、中转在等响应头，两边死等（GET 看不出来，只有登录这类 POST 会卡住）。
- **传了 `.spec` 就不能再传 `--onefile`**（报 `makespec options not valid when a .spec file is given`）：`python -m PyInstaller --noconfirm --distpath "%TEMP%\km_dist" --workpath "%TEMP%\km_build" 快麦扫码查询.spec`。
- **网页改完别只检查 HTML 里有没有那串字**：JS 的 `ReferenceError` 会被 try/catch 吞掉（表现成"一直重试/一直载入中"）。用 node 起真 JS 引擎跑一遍页面脚本（存根 `document`/`localStorage`/`fetch`）才能发现。
- **控制台是 GBK**：脚本里 `print` 带 `−`（U+2212）这类字符会 `UnicodeEncodeError` 把自检脚本打断（看着像功能坏了，其实只是打印），开头加 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`。
- **PowerShell 不支持 heredoc**（`<<'EOF'` 不是字符串、`>` 还会被当重定向），内联 `python -c "…"` 里的引号也会被控制台编码吃掉 → 长脚本一律**写成 .py 文件再跑**。

## 现货可发（`/stock`）——「能发出去的件数」

**口径：`可发 = min(在架数, 待发货件数) − 一单多件件数`**

> 例：一单一件 100 件 + 一单多件 20 件 = 订单共要 120 件，库存只有 80 件 → 最多发 80 件，其中 20 件留给多件单 → **可发 60 件**（“只有 60 件货”）。

- 只给**多件单**预留库存；`1166` / 买家秀 / 圆虹包 等占位补偿商品不显示
- **加急** = 快麦接口 `isUrgent`；带加急且有货的编码**默认排最前**（`加急·有货` 红标）
- **已发**：拣完点一下 → **所有账号都看不到这条**（标记存在服务端，共用一套），**拉到新数据后自动清空**；可「撤回」「清空已发」
- **货位**：直接显示在编码下方（导出也带一列）
- 电脑版：主界面「操作」区 → **现货可发** 按钮（同一套口径 + 标记已发 / 撤回 / 清空已发 / 隐藏已发 + 导出）

⚠️ 加急数据依赖订单表里的 `urgent` 列（老库启动时自动 `ALTER TABLE` 补列）；**升级后需要一次「全量重拉」才会把加急标记补进本地库**（增量刷新只更新变动订单）。

接口：

```
GET  /stock                        现货可发页（手机 / 电脑）
GET  /api/stock?kw=&only=&sort=    列表
     kw   按款号/编码模糊（忽略大小写）
     only all|free|short|orders|urgent|urg_free
     sort urg_free（默认，加急有货优先）|free|urgent|shelf|pieces|code
GET  /api/stock/export?...         导出 Excel（编码/货位/一单一件/一单多件/多件件数/加急/待发货/在架/可发/加急有货）
POST /api/stock/sent               {codes:[...], undo?} 标记/撤回「已发」；{clear:true} 清空
```

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

## 登录（网页版账号）

网页版（`http://127.0.0.1:8790/` 或 `https://<域名>:9443/`）要账号密码才能进查询页：

- **首次设置只能在跑程序的这台电脑上做**（本机直连回环地址、且请求没经过 HTTPS 中转）。外网/手机打开而没有管理员时，只显示一句提示、**不给表单**——否则谁先打开谁就能当管理员。
- 中转（`https/km_https.py`）转发前会剥掉客户端自带的 `X-Forwarded-For` / `X-Real-IP`，再打上真实来源 IP；后端就是用"有没有这个头"区分"本机"与"外面"。
- 账号存 `kuaimai_users.json`（exe 同目录，加盐 SHA-256，不提交）。管理员可加/删账号、改密码、**踢下线**。
- **踢下线 / 管理员改密码**：那台设备 10 分钟内不能再登录（设备标识是登录页 localStorage 里的随机 `km_dev`，随登录请求上报）；改自己的密码不锁自己。
- 同一账号同一时间只能一处登录，新登录会把旧设备顶下线。
- 账号列表显示「登录设备：机型 · 系统 · 浏览器」：机型优先用 `navigator.userAgentData.getHighEntropyValues(['model'])`（Chrome/Edge），拿不到就从 User-Agent 里抠。
- 页面拿不到 `/api/auth/state` 会自动重试 8 次（1.5s 间隔），再失败给「重试」按钮——不再卡在"载入中"。

相关接口：

```
GET  /login                 登录页（首次设置 / 登录 / 账号管理）
GET  /api/auth/state        {need_setup, local, user, role, users}
POST /api/auth/setup        首次设置（仅本机）/ 本机重置管理员密码
POST /api/auth/login        登录（body: name, pw, dev_id, model）
POST /api/auth/logout       退出
POST /api/users             {action: list|add|del|passwd|kick}（仅管理员）
```

## 隐私

仓库只包含程序代码。以下内容**不提交**（见 `.gitignore`）：`kuaimai_api.json`（AppKey/AppSecret/RefreshToken/SessionId）、`kuaimai_settings.json`、`aliyun/` 凭据、`lego/` 证书与账号私钥、各类 `kuaimai_*.json` 缓存、`*.db` 数据、`*.log`、打包产物。

## 第三方

`https/static/zxing.js` 来自 [@zxing/library](https://github.com/zxing-js/library) 0.21.3（Apache-2.0），仅用于本地条码解码，不依赖任何 CDN。
