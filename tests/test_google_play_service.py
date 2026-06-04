import json

from app.services.google_play_service import GooglePlayService


def test_parse_chart_response_maps_rank_and_installs():
    service = object.__new__(GooglePlayService)
    app_data = [None] * 16
    app_data[0] = ["com.example.demo"]
    app_data[1] = [None, None, None, [None, None, "https://cdn.example/icon.png"]]
    app_data[3] = "Demo App"
    app_data[4] = ["4.8", 4.8]
    app_data[8] = [None, [[0, "USD"]]]
    app_data[10] = [None, None, None, None, [None, None, "/store/apps/details?id=com.example.demo"]]
    app_data[14] = "Demo Studio"
    app_data[15] = "10,000,000+"
    raw_item = [app_data]

    collection_block = [None] * 29
    collection_block[28] = [[raw_item]]
    payload = [[None, [collection_block]]]
    response = ")]}'\n\n101\n" + json.dumps([["wrb.fr", "vyAe2", json.dumps(payload)]])

    items = service._parse_chart_response(
        response,
        chart_type="top_free",
        category="APPLICATION",
        country="us",
        lang="en",
    )

    assert len(items) == 1
    assert items[0].rank == 1
    assert items[0].app_id == "com.example.demo"
    assert items[0].title == "Demo App"
    assert items[0].developer == "Demo Studio"
    assert items[0].installs == "10,000,000+"
    assert items[0].free is True


def test_parse_similar_cards_extracts_rating_and_titles():
    service = object.__new__(GooglePlayService)
    html = """
    <section>
      <h2><span>Similar apps</span></h2>
      <a class="Si6A0c nT2RTe" href="/store/apps/details?id=com.example.alpha">
        <img src="https://cdn.example/alpha.png" />
        <span class="DdYX5">Alpha</span>
        <span class="wMUdtb">Alpha Studio</span>
        <span class="w2kbF">4.7</span>
      </a>
      <a class="Si6A0c nT2RTe" href="/store/apps/details?id=com.example.beta">
        <img src="https://cdn.example/beta.png" />
        <span class="DdYX5">Beta &amp; Friends</span>
        <span class="wMUdtb">Beta Labs</span>
        <span class="w2kbF">4.1</span>
      </a>
    </section>
    """

    items = service._parse_similar_cards(html, country="us", lang="en", limit=10)

    assert [item.app_id for item in items] == ["com.example.alpha", "com.example.beta"]
    assert items[0].title == "Alpha"
    assert items[0].developer == "Alpha Studio"
    assert items[0].rating == 4.7
    assert items[1].title == "Beta & Friends"
    assert items[1].rating == 4.1
