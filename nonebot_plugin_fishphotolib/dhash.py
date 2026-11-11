"""dHash（感知哈希）去重 —— 纯函数。

为什么用 dHash 而不是 md5：**转存/重压缩/改尺寸**之后 md5 全变，
但 dHash 只差 0~4 位。群里同一张图被转发十次，md5 十条记录，dHash 只有一条。

算法（经典 9×8 版）：
  缩成 9×8 灰度 → 每行相邻像素比较 → 8×8 = 64 位。
"""

from __future__ import annotations

import io
from typing import Iterable, Optional


def _pil():
    try:
        from PIL import Image
        return Image
    except Exception:
        return None


def dhash(img_bytes: bytes, size: int = 8) -> Optional[str]:
    """图 → 16 位十六进制哈希（64 bit）。没有 pillow / 坏图返回 None。"""
    Image = _pil()
    if Image is None or not img_bytes:
        return None
    try:
        im = Image.open(io.BytesIO(img_bytes)).convert("L").resize((size + 1, size))
    except Exception:
        return None
    bits = 0
    try:
        px = im.load()
    except Exception:
        return None
    idx = 0
    for y in range(size):
        for x in range(size):
            left = px[x, y]
            right = px[x + 1, y]
            if left > right:
                bits |= (1 << idx)
            idx += 1
    return "%016x" % bits


def hamming(a: str, b: str) -> int:
    """两个哈希差几位（0 = 完全一样）。非法输入返回 64（= 不可能是重复）。"""
    try:
        x = int(str(a), 16)
        y = int(str(b), 16)
    except (TypeError, ValueError):
        return 64
    v = x ^ y
    n = 0
    while v:
        n += v & 1
        v >>= 1
    return n


def is_dup(candidate: str, existing: Iterable[str], *, dist: int = 6) -> bool:
    """和已有哈希里任意一个的汉明距离 ≤ `dist` 就算重复。"""
    if not candidate:
        return False
    return any(hamming(candidate, h) <= int(dist) for h in existing if h)


def nearest(candidate: str, existing: Iterable[str]) -> int:
    """最接近的那个差几位（没有可比对象返回 64）。"""
    vals = [hamming(candidate, h) for h in existing if h]
    return min(vals) if vals else 64
