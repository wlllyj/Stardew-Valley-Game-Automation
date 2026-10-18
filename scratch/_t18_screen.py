"""只读截图工具：PrintWindow(PW_RENDERFULLCONTENT) 抓游戏窗口 → PNG。

用法：
  PYTHONUTF8=1 python scratch\\_t18_screen.py scratch\\out.png

不碰游戏状态（只调用 user32/gdi32 读取窗口像素）。找不到窗口或 PrintWindow 失败时
如实打印原因并 rc=2（不许猜、不许当成功）。
"""
from __future__ import annotations

import ctypes
import struct
import sys
import zlib
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

TITLE_HINTS = ("Stardew Valley",)
PW_RENDERFULLCONTENT = 2


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


def find_window():
    found = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        title = buf.value
        if any(h in title for h in TITLE_HINTS):
            found.append((hwnd, title))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found


def grab(hwnd: int) -> bytes:
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise OSError(f"GetClientRect failed: {ctypes.get_last_error()}")
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        raise OSError(f"client rect empty: {w}x{h}")
    hdc = user32.GetDC(hwnd)
    if not hdc:
        raise OSError("GetDC failed")
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    old = gdi32.SelectObject(mdc, bmp)
    try:
        ok = user32.PrintWindow(hwnd, mdc, PW_RENDERFULLCONTENT)
        if not ok:
            ok = user32.PrintWindow(hwnd, mdc, 0)
        if not ok:
            raise OSError(f"PrintWindow failed: {ctypes.get_last_error()}")
        bi = BITMAPINFOHEADER()
        bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.biWidth = w
        bi.biHeight = -h
        bi.biPlanes = 1
        bi.biBitCount = 32
        buf = ctypes.create_string_buffer(w * h * 4)
        got = gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
        if got != h:
            raise OSError(f"GetDIBits got {got} rows, want {h}")
    finally:
        gdi32.SelectObject(mdc, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mdc)
        user32.ReleaseDC(hwnd, hdc)

    raw = buf.raw
    rows = []
    for y in range(h):
        row = raw[y * w * 4:(y + 1) * w * 4]
        px = bytearray()
        for x in range(w):
            b, g, r, _a = row[x * 4:x * 4 + 4]
            px += bytes((r, g, b))
        rows.append(b"\x00" + bytes(px))

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"".join(rows), 6))
        + chunk(b"IEND", b"")
    )
    return png


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python scratch\\_t18_screen.py <out.png>")
        return 2
    wins = find_window()
    print("windows=", [(h, t) for h, t in wins])
    if not wins:
        print("FAIL: 没找到标题含 Stardew Valley 的可见窗口")
        return 2
    hwnd, title = wins[0]
    try:
        png = grab(hwnd)
    except OSError as exc:
        print(f"FAIL: {exc}")
        return 2
    out = sys.argv[1]
    with open(out, "wb") as fh:
        fh.write(png)
    print(f"OK: {out} {len(png)}B hwnd={hwnd} title={title!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
