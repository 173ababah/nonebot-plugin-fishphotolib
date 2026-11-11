"""nonebot-plugin-fishphotolib —— 图片库。

命令：

| 命令 | 说明 |
|------|------|
| `/图库` | 最新几张 |
| `/图库 猫` | 按标签搜 |
| `/图库 随机 [标签]` | 随机来一张 |
| `/图库 标签` | 看标签统计 |
| `/图库 相册` | 看相册统计 |
| `/图库 加 <标签…>` | （超管，回复一张图）入库；自动 dHash 去重 + 粗筛露点 |

设计：**先粗筛再人工标签**。`classify` 只提供可解释的两个指标（肤色占比、色块集中度），
不接视觉模型也能用；接了模型就多一道准确率。
"""

from __future__ import annotations

import os

from nonebot import get_plugin_config, on_command
from nonebot.adapters import Event, Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata

from . import classify, dhash, store
from .config import LibConfig

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-fishphotolib",
    description="图片库：相册/标签/搜索/随机 + dHash 去重 + 露点与二次元粗筛",
    usage="/图库 | /图库 猫 | /图库 随机 | /图库 标签 | /图库 相册 | /图库 加 猫（超管，回复图）",
    type="application",
    config=LibConfig,
    homepage="https://github.com/173ababah/nonebot-plugin-fishphotolib",
    supported_adapters={"~onebot.v11"},
)

cfg = get_plugin_config(LibConfig)
ROOT = cfg.fishlib_root or os.path.join(os.getcwd(), "data", "fishlib")

lib_cmd = on_command("图库", aliases={"相册", "来张图"}, priority=18, block=True)


def _reply_image(event: Event):
    """取被回复消息里的图片字节（None = 没有）。"""
    try:
        from nonebot.adapters.onebot.v11 import MessageSegment
        msg = getattr(event, "reply", None)
        segs = getattr(getattr(event, "original_message", None), "get", None)
        for seg in (list(getattr(event, "message", []) or []) + list((msg.message if msg else []) or [])):
            if seg.type == "image":
                return {"url": (seg.data or {}).get("url") or (seg.data or {}).get("file")}
        return None
    except Exception:
        return None


async def add_image(data: bytes, tags: list, *, uid: str = "0") -> tuple:
    """入库（自动去重 + 粗筛）。返回 `(ok, 说明)`。"""
    h = dhash.dhash(data)
    items = store.load(ROOT)
    if h and dhash.is_dup(h, [it.get("dhash") for it in items], dist=cfg.fishlib_dhash_dist):
        near = dhash.nearest(h, [it.get("dhash") for it in items])
        return False, "这张已经有了（相似度差 %d 位）" % near
    m = classify.measure(data)
    v = classify.verdict(m, skin_thresh=cfg.fishlib_skin_thresh)
    rec = store.add(ROOT, data, tags=tags, uid=uid, dhash=h or "",
                    verdict=v, skin=(m or {}).get("skin", 0.0))
    if not rec:
        return False, "存盘失败"
    tail = ""
    if m:
        tail = "（肤色 %.0f%%，%s）" % (m["skin"] * 100,
                                     "偏露" if v == "lewd" else "安全")
    return True, "收下了：%s%s" % (rec["id"], tail)


@lib_cmd.handle()
async def _(event: Event, arg: Message = CommandArg()):
    if not cfg.fishlib_enabled:
        await lib_cmd.finish("图库关着呢（FISHLIB_ENABLED=false）")
    text = arg.extract_plain_text().strip()
    items = store.load(ROOT)

    if text.startswith("加"):
        if not await SUPERUSER(event):
            await lib_cmd.finish("只有超管能加图")
        tags = [t for t in text[1:].split() if t]
        ref = _reply_image(event)
        if not ref:
            await lib_cmd.finish("回复一张图，再发 `/图库 加 标签`")
        import httpx
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.get(ref["url"])
                data = r.content
        except Exception as e:
            await lib_cmd.finish("图下载不下来：%s" % e)
        ok, msg = await add_image(data, tags, uid=str(getattr(event, "get_user_id", lambda: "")()))
        await lib_cmd.finish(msg)

    if text in ("标签", "tags"):
        rows = store.tags_of(items)
        if not rows:
            await lib_cmd.finish("还没有标签")
        await lib_cmd.finish("标签（%d 个）：\n" % len(rows) +
                             "  ".join("%s×%d" % (t, n) for t, n in rows[:40]))

    if text in ("相册", "albums"):
        rows = store.albums_of(items)
        if not rows:
            await lib_cmd.finish("还没有相册")
        await lib_cmd.finish("相册：\n" + "\n".join("· %s（%d）" % (a, n) for a, n in rows))

    if text.startswith("随机"):
        tag = text[2:].strip()
        rec = store.pick_random(items, tag=tag)
        if not rec:
            await lib_cmd.finish("图库里没有可发的图")
        from nonebot.adapters.onebot.v11 import MessageSegment
        with open(store.path_of(ROOT, rec), "rb") as f:
            await lib_cmd.finish(MessageSegment.image(f.read()))

    res = store.search(items, tag=text, q=text if not text else "", limit=cfg.fishlib_page)
    if not res["items"]:
        await lib_cmd.finish("没找到（共 %d 张）" % res["all"])
    lines = ["图库 %d / 共 %d 张：" % (res["total"], res["all"])]
    for it in res["items"]:
        lines.append("· %s %s%s" % (it["id"],
                                    "/".join(it.get("tags") or []) or "无标签",
                                    "" if it.get("verdict") != "lewd" else " ⚠️"))
    await lib_cmd.finish("\n".join(lines))
