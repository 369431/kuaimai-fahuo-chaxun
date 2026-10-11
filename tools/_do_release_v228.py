# -*- coding: utf-8 -*-
"""发布 v2.28：彻底修「更新后又出现旧版窗口」（抓到真凶 + 三层保险）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.28.exe")
NOTES = (
    "**v2.28：彻底修「更新后又出现旧版窗口」**\n"
    "\n"
    "**这次抓到真凶了**\n"
    "· 用 Win32 枚举所有顶层窗口，实测抓到：\n"
    "    pid=32952  hwnd=2692536  窗口类=TkTopLevel  可见=True\n"
    "    标题=「快麦扫码查待发货 + 货架在架数」   ← 旧 Tk 界面真的处于可见状态\n"
    "· 也就是说之前几次没修干净：旧的 Tk 根窗确实会被重新显示出来。\n"
    "\n"
    "**为什么前几次按不住（三个原因，各修各的）**\n"
    "· Tk 的窗口操作**必须在主线程**做；后台线程调 withdraw() 有时被 Tk 直接忽略\n"
    "  → 之前那个后台看门狗就是因此失效的。\n"
    "· 真正把窗口弄出来的是 `wm_geometry` / `wm_minsize` 等**另一批** wm_* 方法\n"
    "  （ScanApp 初始化里就在调 geometry/minsize），只拦 deiconify/attributes 拦不完。\n"
    "· 看门狗原来挂在 start() 最后，中途任何一步失败就没人保护根窗了\n"
    "  （更新重启时正好容易走到这种路径）。\n"
    "\n"
    "**这一版的三层保险**\n"
    "① **Tk 主循环看门狗**：挂在 Tk 的 after 事件循环里，每秒检查，只要根窗处于 mapped\n"
    "   就立刻 withdraw（主线程操作，符合 Tk 规矩）。\n"
    "② **Win32 看门狗**：后台线程用 `ShowWindow(hwnd, SW_HIDE)` 强制隐藏\n"
    "   —— **完全不碰 Tk API**，绕开线程不安全的问题，这是最硬的一层。\n"
    "③ 拦截 deiconify / wm_deiconify / attributes / lift（防止被显式调出来）。\n"
    "另外：根窗一建好就挂防护（不再等到最后），把口子提前堵上。\n"
    "\n"
    "**实测（都通过）**\n"
    "· 修复前：可见的 Tk 窗口 1 个（标题=快麦扫码查待发货+货架在架数）\n"
    "· 修复后：可见的 Tk 窗口 **0 个**（根窗 标题=快麦扫码查询 v2.28，可见=False）\n"
    "· 重启后连续观察 120 秒：出现可见 Tk 窗口 **0 次**\n"
    "· 最小化/还原各 3 轮：旧界面出现 **0 次**\n"
    "· 8 个设置窗仍能正常弹出（锁死根窗不影响弹窗）\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.28", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
