"""图库存储：索引 / 相册 / 标签 / 搜索 / 随机。

索引 `index.json`，一条记录：

```json
{"id": "20261111-221500-1", "file": "20261111-221500-1.jpg", "at": "2026-11-11 22:15",
 "tags": ["猫", "二次元"], "album": "默认", "bytes": 123456, "dhash": "a1b2…",
 "verdict": "safe", "skin": 0.12, "note": ""}
```

设计取舍：

1. **文件躺在磁盘上，索引只管元信息**：哪天索引丢了还能扫目录重建（`file` 就是文件名）。
2. **标签是自由的字符串**：群里说"来张猫"就该能搜到，不该逼用户先建标签体系。
3. **相册只是一层的分组**：真需要多级目录时用标签，别把相册做成树。
"""

from __future__ import annotations

import json
import os
import random
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

_lock = threading.Lock()
DEFAULT_ALBUM = "默认"


def new_id(uid: str = "0") -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + str(uid or "0")[-4:]


def index_path(root: str) -> str:
    return os.path.join(root, "index.json")


def load(root: str) -> List[Dict[str, Any]]:
    try:
        with open(index_path(root), "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save(root: str, items: List[Dict[str, Any]]) -> bool:
    try:
        os.makedirs(root, exist_ok=True)
        tmp = index_path(root) + ".tmp"
        with _lock:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp, index_path(root))
        return True
    except OSError:
        return False


def add(root: str, data: bytes, *, tags: Optional[List[str]] = None,
        album: str = "", uid: str = "0", dhash: str = "",
        verdict: str = "", skin: float = 0.0, ext: str = ".jpg") -> Optional[Dict[str, Any]]:
    """落盘 + 写索引。返回记录（失败 None）。"""
    if not data:
        return None
    rid = new_id(uid)
    name = rid + ext
    try:
        os.makedirs(root, exist_ok=True)
        with _lock:
            with open(os.path.join(root, name), "wb") as f:
                f.write(data)
    except OSError:
        return None
    rec = {"id": rid, "file": name, "at": time.strftime("%Y-%m-%d %H:%M"),
           "tags": [str(t).strip() for t in (tags or []) if str(t).strip()],
           "album": album or DEFAULT_ALBUM, "bytes": len(data),
           "dhash": dhash, "verdict": verdict, "skin": round(float(skin), 3), "note": ""}
    items = load(root)
    items.append(rec)
    save(root, items)
    return rec


def find(root: str, rid: str) -> Optional[Dict[str, Any]]:
    return next((it for it in load(root) if it.get("id") == rid), None)


def path_of(root: str, rec: Dict[str, Any]) -> str:
    return os.path.join(root, str(rec.get("file") or ""))


def delete(root: str, rid: str) -> bool:
    items = load(root)
    rec = next((it for it in items if it.get("id") == rid), None)
    if not rec:
        return False
    try:
        p = path_of(root, rec)
        if os.path.isfile(p):
            os.remove(p)
    except OSError:
        pass
    save(root, [it for it in items if it.get("id") != rid])
    return True


def set_meta(root: str, rid: str, **kw) -> bool:
    items = load(root)
    hit = False
    for it in items:
        if it.get("id") != rid:
            continue
        hit = True
        for k in ("tags", "album", "note", "verdict"):
            if k in kw:
                it[k] = kw[k]
    if not hit:
        return False
    return save(root, items)


def tags_of(items: List[Dict[str, Any]]) -> List[Tuple[str, int]]:
    """标签统计（按出现次数降序）——用于 `/图库 标签`。"""
    cnt: Dict[str, int] = {}
    for it in items:
        for t in it.get("tags") or []:
            cnt[str(t)] = cnt.get(str(t), 0) + 1
    return sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))


def albums_of(items: List[Dict[str, Any]]) -> List[Tuple[str, int]]:
    cnt: Dict[str, int] = {}
    for it in items:
        a = str(it.get("album") or DEFAULT_ALBUM)
        cnt[a] = cnt.get(a, 0) + 1
    return sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))


def search(items: List[Dict[str, Any]], *, tag: str = "", album: str = "",
           q: str = "", verdict: str = "", limit: int = 8,
           offset: int = 0) -> Dict[str, Any]:
    tag = str(tag or "").strip()
    album = str(album or "").strip()
    q = str(q or "").strip().lower()
    verdict = str(verdict or "").strip()

    def hit(it: Dict[str, Any]) -> bool:
        if tag and tag not in [str(x) for x in (it.get("tags") or [])]:
            return False
        if album and str(it.get("album") or DEFAULT_ALBUM) != album:
            return False
        if verdict and str(it.get("verdict") or "") != verdict:
            return False
        if q:
            blob = " ".join([str(it.get(k) or "") for k in ("note", "album")]
                            + [str(x) for x in (it.get("tags") or [])]).lower()
            if q not in blob:
                return False
        return True

    sel = [it for it in items if hit(it)]
    sel.sort(key=lambda x: str(x.get("at") or ""), reverse=True)
    try:
        limit = max(1, min(200, int(limit)))
        offset = max(0, int(offset))
    except (TypeError, ValueError):
        limit, offset = 8, 0
    return {"all": len(items), "total": len(sel), "items": sel[offset:offset + limit]}


def pick_random(items: List[Dict[str, Any]], *, tag: str = "", album: str = "",
                verdict: str = "", rng: Optional[random.Random] = None) -> Optional[Dict[str, Any]]:
    res = search(items, tag=tag, album=album, verdict=verdict, limit=200, offset=0)
    pool = res["items"]
    if not pool:
        return None
    rng = rng or random
    return pool[rng.randrange(len(pool))]
