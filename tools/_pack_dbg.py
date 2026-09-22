# -*- coding: utf-8 -*-
import sys
EXE = r"C:\Users\Kerwin\Desktop\发布\_build_v124\dist\快麦扫码查询.exe"
import PyInstaller
print("PyInstaller", PyInstaller.__version__)
from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader
import inspect
print("CArchiveReader methods:", [m for m in dir(CArchiveReader) if not m.startswith("_")])
ca = CArchiveReader(EXE)
print("toc sample:")
for t in list(ca.toc)[:8]:
    print("   ", t)
print("toc len", len(list(ca.toc)))
print("ZlibArchiveReader init sig:", inspect.signature(ZlibArchiveReader.__init__))
print("has open_embedded_archive:", hasattr(ca, "open_embedded_archive"))
# find any entry whose name mentions pyz
cands = [t for t in ca.toc if "pyz" in str(t[0]).lower()]
print("pyz candidates:", cands[:5])
