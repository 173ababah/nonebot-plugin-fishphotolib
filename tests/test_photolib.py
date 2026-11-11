"""dHash / 粗筛 / 存储 的单元测试（合成图，不联网）。"""

import io
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "nonebot_plugin_fishphotolib"))

import classify  # noqa: E402
import dhash  # noqa: E402
import store  # noqa: E402

try:
    from PIL import Image
    HAS_PIL = True
except Exception:
    HAS_PIL = False

import pytest


def _png(size=(160, 160), color=(30, 30, 30), box=None, box_color=(240, 200, 190)):
    im = Image.new("RGB", size, color)
    if box:
        for x in range(box[0], box[2]):
            for y in range(box[1], box[3]):
                im.putpixel((x, y), box_color)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


@pytest.mark.skipif(not HAS_PIL, reason="需要 pillow")
def test_dhash_stable_for_same_image():
    a = dhash.dhash(_png())
    b = dhash.dhash(_png())
    assert a and a == b and len(a) == 16


@pytest.mark.skipif(not HAS_PIL, reason="需要 pillow")
def test_dhash_differs_for_different_images():
    a = dhash.dhash(_png(color=(10, 10, 10), box=(0, 0, 80, 160)))
    b = dhash.dhash(_png(color=(10, 10, 10), box=(80, 0, 160, 160)))
    assert dhash.hamming(a, b) >= 0


def test_hamming_and_is_dup():
    assert dhash.hamming("0000000000000000", "0000000000000000") == 0
    assert dhash.hamming("f000000000000000", "0000000000000000") == 4
    assert dhash.hamming("zzz", "000") == 64                     # 非法输入
    assert dhash.is_dup("0000000000000000", ["000000000000000f"], dist=6) is True
    assert dhash.is_dup("0000000000000000", ["ffffffffffffffff"], dist=6) is False
    assert dhash.nearest("0000000000000000", []) == 64


def test_dhash_bad_input():
    assert dhash.dhash(b"") is None
    assert dhash.dhash(b"not an image") is None


@pytest.mark.skipif(not HAS_PIL, reason="需要 pillow")
def test_classify_skin_ratio():
    # 大半是肤色 → lewd；纯绿背景 + 小块皮肤 → safe
    hot = classify.measure(_png(color=(235, 190, 175)))
    safe = classify.measure(_png(color=(20, 190, 90), box=(60, 120, 100, 160)))
    assert hot and hot["skin"] > 0.5
    assert classify.verdict(hot, skin_thresh=0.28) == "lewd"
    assert classify.verdict(safe, skin_thresh=0.28) == "safe"
    assert classify.verdict(None) == "unknown"


@pytest.mark.skipif(not HAS_PIL, reason="需要 pillow")
def test_classify_anime_heuristic_and_verify_hook():
    flat = classify.measure(_png(color=(240, 60, 120)))
    assert classify.is_anime_like(flat, flat_thresh=0.06)
    assert classify.verify_with(b"x", lambda b: {"nsfw": True})["nsfw"] is True
    assert classify.verify_with(b"x", lambda b: 1 / 0) is None     # 抛异常不炸


def test_store_add_search_tags_albums():
    with tempfile.TemporaryDirectory() as d:
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
        rec = store.add(d, png, tags=["猫", "二次元"], album="萌宠", uid="1000", dhash="00ff")
        assert rec and os.path.isfile(store.path_of(d, rec))
        items = store.load(d)
        assert store.search(items, tag="猫")["total"] == 1
        assert store.search(items, tag="狗")["total"] == 0
        assert store.search(items, album="萌宠")["total"] == 1
        assert dict(store.tags_of(items))["猫"] == 1
        assert dict(store.albums_of(items))["萌宠"] == 1
        assert store.set_meta(d, rec["id"], tags=["狗"], note="改了")
        assert store.search(store.load(d), tag="狗")["total"] == 1
        assert store.delete(d, rec["id"]) is True
        assert store.load(d) == []


def test_store_random_and_pagination():
    with tempfile.TemporaryDirectory() as d:
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 16
        for i in range(5):
            store.add(d, png, tags=["t"], uid=str(i))
        items = store.load(d)
        assert store.search(items, limit=2, offset=2)["total"] == 5
        rng = random.Random(1)
        assert store.pick_random(items, rng=rng) is not None
        assert store.pick_random(items, tag="没有", rng=rng) is None
