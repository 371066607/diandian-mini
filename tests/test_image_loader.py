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
