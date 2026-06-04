import app.utils.image_loader as image_loader


def test_fetch_images_preserves_order(monkeypatch):
    monkeypatch.setattr(
        image_loader,
        "fetch_image_bytes",
        lambda url, timeout=6.0: None if url is None else url.encode(),
    )
    out = image_loader.fetch_images(["a", "b", None, "c"])
    assert out == [b"a", b"b", None, b"c"]


def test_fetch_images_empty():
    assert image_loader.fetch_images([]) == []


def test_image_cache_evicts_by_entry_count():
    cache = image_loader._ImageCache(max_bytes=10**9, max_entries=2)
    cache.put("a", b"1")
    cache.put("b", b"2")
    cache.put("c", b"3")  # exceeds 2 entries -> evict least-recently-used "a"
    assert cache.get("a") is None
    assert cache.get("b") == b"2"
    assert cache.get("c") == b"3"


def test_image_cache_evicts_by_bytes():
    cache = image_loader._ImageCache(max_bytes=5, max_entries=1000)
    cache.put("a", b"xxx")  # 3 bytes
    cache.put("b", b"yyy")  # +3 = 6 > 5 -> evict "a"
    assert cache.get("a") is None
    assert cache.get("b") == b"yyy"


def test_image_cache_lru_touch_protects_entry():
    cache = image_loader._ImageCache(max_bytes=10**9, max_entries=2)
    cache.put("a", b"1")
    cache.put("b", b"2")
    cache.get("a")  # touch "a" -> "b" becomes the LRU
    cache.put("c", b"3")  # evict LRU = "b"
    assert cache.get("b") is None
    assert cache.get("a") == b"1"
    assert cache.get("c") == b"3"


def test_image_cache_rejects_oversized_item():
    cache = image_loader._ImageCache(max_bytes=4, max_entries=10)
    cache.put("big", b"xxxxx")  # 5 bytes > cap -> not stored
    assert cache.get("big") is None


def test_fetch_image_bytes_uses_cache(monkeypatch):
    image_loader._image_cache.clear()
    calls = []
    monkeypatch.setattr(
        image_loader, "_download_image_bytes", lambda url, timeout: calls.append(url) or b"data"
    )
    first = image_loader.fetch_image_bytes("http://x/icon")
    second = image_loader.fetch_image_bytes("http://x/icon")
    assert first == second == b"data"
    assert calls == ["http://x/icon"]  # downloaded once; second hit served from cache
    image_loader._image_cache.clear()
