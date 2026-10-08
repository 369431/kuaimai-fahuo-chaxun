; 快麦扫码查询 一体化安装脚本（入库版，全相对路径）
;
; 编译（在仓库根目录跑；packaging\build.ps1 会自动做这一步）：
;   "<Inno Setup 6>\ISCC.exe" packaging\快麦扫码查询.iss /DMyAppVersion=1.25
;
; 依赖同目录的「staging\」——build.ps1 会先按 §3 把安装内容摆进去：
;   快麦扫码查询.exe（spec 产物）、客户安装手册.txt、启动全部.*、装开机自启.*、
;   kuaimai_gateway.json、kuaimai.ico、kuaimai_https\（%REPO%\https 的转发脚本 + static）、
;   frp\frpc.exe（download_frp.ps1 抓的，不入库）
;
; 占位符：build.ps1 会 /DMyAppVersion=… 传进来；不传则用下面这行默认值。

#ifndef MyAppVersion
  #define MyAppVersion "1.31"
#endif

#define MyAppName "快麦扫码查询"
#define MyAppExeName "快麦扫码查询.exe"
#define MyAppPublisher "火火火服饰"
#define MyAppId "{{7C4B1E92-3A55-4F0C-9D2E-2B7A5C8E1F30}"
#define StageDir AddBackslash(SourcePath) + "staging"
#define OutDir AddBackslash(SourcePath) + "out"
; 预填在网关设置里的 frp 服务器（客户可改）
#define DefaultServer "106.52.122.158"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\KuaimaiScan
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#OutDir}
OutputBaseFilename=快麦扫码查询_安装版_v{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile={#StageDir}\kuaimai.ico
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "chs"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："
Name: "autostart"; Description: "开机自动启动（程序 + HTTPS中转，用计划任务）"; GroupDescription: "附加任务："
Name: "bootstart"; Description: "真·开机自启（9443中转/frp 无需登录就跑 + 看门狗巡检，需要管理员）"; GroupDescription: "附加任务："

[Files]
Source: "{#StageDir}\快麦扫码查询.exe"; DestDir: "{app}"; Flags: ignoreversion
; v1.73：改成 onedir 打包（启动快 10 倍），依赖都在 _internal 里
Source: "{#StageDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#StageDir}\客户安装手册.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\启动全部.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\启动全部.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\装开机自启.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\装开机自启.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\注册真开机自启.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\注册真开机自启.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\看门狗.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\开启自动登录.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\开启自动登录.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\kuaimai_https\*"; DestDir: "{app}\kuaimai_https"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#StageDir}\frp\frpc.exe"; DestDir: "{app}\frp"; Flags: ignoreversion
Source: "{#StageDir}\kuaimai_gateway.json"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\启动全部（程序+中转）"; Filename: "{app}\启动全部.cmd"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\客户安装手册"; Filename: "{app}\客户安装手册.txt"
Name: "{group}\注册开机自启（登录后启动）"; Filename: "{app}\装开机自启.cmd"
Name: "{group}\注册真·开机自启（推荐）"; Filename: "{app}\注册真开机自启.cmd"
Name: "{group}\开启 Windows 自动登录"; Filename: "{app}\开启自动登录.cmd"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName} 启动"; Filename: "{app}\启动全部.cmd"; Tasks: autostart

[Run]
Filename: "{app}\装开机自启.cmd"; Flags: runhidden waituntilterminated
; 勾了"真·开机自启"才跑（会弹一次 UAC，因为要注册 SYSTEM 身份的开机任务）
Filename: "{app}\注册真开机自启.cmd"; Tasks: bootstart; Flags: shellexec nowait postinstall skipifsilent
Filename: "{app}\启动全部.cmd"; Description: "立即启动 快麦扫码查询 + HTTPS中转"; Flags: nowait postinstall
