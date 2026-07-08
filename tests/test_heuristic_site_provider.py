from app.providers.heuristic_site import (
    extract_quark_links,
    parse_candidates,
    HeuristicSiteProvider,
    jpmom_profile,
    houtupan_profile,
)


def test_extract_quark_links_handles_html_and_escaped_urls():
    text = '''
    <a href="https://pan.quark.cn/s/abc123">夸克</a>
    {"url":"https:\\/\\/pan.quark.cn\\/s\\/xyz789"}
    '''
    assert extract_quark_links(text) == [
        "https://pan.quark.cn/s/abc123",
        "https://pan.quark.cn/s/xyz789",
    ]


def test_jpmom_candidate_parser_prioritizes_matching_article():
    html = '''
    <nav><a href="/zxdy">最新电影</a></nav>
    <article class="post-item"><h2><a href="/6060.html">星际穿越 4K HDR</a></h2></article>
    <article><a href="/5999.html">其他电影</a></article>
    '''
    candidates = parse_candidates(
        html,
        "https://site-a.example/?s=%E6%98%9F%E9%99%85%E7%A9%BF%E8%B6%8A",
        "星际穿越",
        "site-a.example",
        (r"/\d+\.html(?:$|[?#])",),
        10,
    )
    assert candidates
    assert candidates[0].url == "https://site-a.example/6060.html"


def test_document_parser_extracts_quality_size_and_passcode():
    provider = HeuristicSiteProvider(jpmom_profile("https://site-a.example"))
    html = '''
    <html><head><meta property="og:title" content="星际穿越 2160p REMUX HDR Atmos"></head>
    <body><p>文件大小 70GB，提取码：A1b2</p>
    <a href="https://pan.quark.cn/s/fourk">夸克网盘</a></body></html>
    '''
    results = provider._results_from_document(html, "星际穿越", "https://site-a.example/6060.html")
    assert len(results) == 1
    assert results[0].share_url == "https://pan.quark.cn/s/fourk"
    assert "2160P" in results[0].quality
    assert "REMUX" in results[0].quality
    assert results[0].size == "70GB"
    assert results[0].extra["password"] == "A1b2"


def test_builtin_profiles_include_fallback_search_patterns():
    assert jpmom_profile("https://site-a.example").search_templates == ("?s={query}",)
    houtu = houtupan_profile("https://site-b.example")
    assert "?s={query}" in houtu.search_templates
    assert "search?keyword={query}" in houtu.search_templates


def test_irrelevant_homepage_result_is_filtered():
    from app.providers.heuristic_site import _relevant_results
    from app.models import ResourceResult

    rows = [
        ResourceResult(title="完全无关的最新电影", share_url="https://pan.quark.cn/s/other"),
        ResourceResult(title="星际穿越 4K", share_url="https://pan.quark.cn/s/right"),
    ]
    filtered = _relevant_results("星际穿越", rows)
    assert [item.share_url for item in filtered] == ["https://pan.quark.cn/s/right"]
