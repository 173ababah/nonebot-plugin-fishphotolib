"""粗筛：这张图是「露」还是「安全」，以及像不像二次元。

⚠️ 这只是**粗筛**，用来在没接视觉模型时先挡一道、少发错图；
真要准确请开 `FISHLIB_VISION` 并接一个识图接口（`classify.verify_with` 给了接口）。

两个指标都是可解释的：

| 指标 | 怎么算 | 用途 |
|------|--------|------|
| `skin` | 近似 YCbCr 的暖色 + 中等亮度像素占比 | 露不露 |
| `flat` | 颜色直方图的集中度（纯色块多 = 二次元/表情包） | 像不像二次元 |

真实照片也常常 `skin` 高，所以阈值别调太低，并且**永远配合人工标签**用。
"""

from __future__ import annotations

import io
from typing import Any, Callable, Dict, Optional


def _deps():
    try:
        import numpy as np
        from PIL import Image
        return np, Image
    except Exception:
        return None, None


def measure(img_bytes: bytes, *, size: int = 128) -> Optional[Dict[str, float]]:
    """量一张图：`{skin, flat, sat, bright}`（0~1）。读不了返回 None。"""
    np, Image = _deps()
    if np is None or not img_bytes:
        return None
    try:
        im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        im.thumbnail((size, size))
        arr = np.asarray(im).astype(np.int16)
    except Exception:
        return None
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    total = arr.shape[0] * arr.shape[1]
    if total == 0:
        return None
    cr = (r - g) * 0.5 + 128
    cb = (b - g) * 0.5 + 128
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    skin = ((r > 95) & (g > 40) & (b > 20) & (r > g) & (r > b)
            & (abs(cr - cb) >= 10) & (lum > 60) & (lum < 245))
    mx = arr.max(axis=2)
    mn = arr.min(axis=2)
    sat = (mx - mn) / np.maximum(1, mx)
    # 纯色块占比：把颜色量化到 32 级，看最大一桶占多少
    q = (arr // 32).astype(np.int32)
    flat_keys = (q[..., 0] * 64 + q[..., 1] * 8 + q[..., 2]).reshape(-1)
    counts = np.bincount(flat_keys, minlength=512)
    flat = float(counts.max()) / float(total)
    return {"skin": float(skin.sum()) / total,
            "flat": flat,
            "sat": float(sat.mean()),
            "bright": float(lum.mean()) / 255.0}


def verdict(m: Optional[Dict[str, float]], *, skin_thresh: float = 0.28) -> str:
    """`lewd` / `safe` / `unknown`（量不出来）。"""
    if not m:
        return "unknown"
    return "lewd" if m["skin"] >= float(skin_thresh) else "safe"


def is_anime_like(m: Optional[Dict[str, float]], *, flat_thresh: float = 0.06,
                  sat_thresh: float = 0.28) -> bool:
    """二次元/插画通常色块集中、饱和度更高；照片碎、饱和度低。"""
    if not m:
        return False
    return m["flat"] >= flat_thresh or m["sat"] >= sat_thresh


def verify_with(img_bytes: bytes, fn: Callable[[bytes], Optional[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    """交给外部视觉模型做二次校验。

    `fn` 返回 `{"nsfw": bool, "anime": bool, "why": str}` 之类；抛异常/返回 None 视为"没结论"。
    插件里没接模型时这一步直接跳过 —— **不要因为没接模型就默认放行**，
    粗筛结果仍然是最终判断（见 README）。
    """
    if not callable(fn):
        return None
    try:
        return fn(img_bytes)
    except Exception:
        return None
