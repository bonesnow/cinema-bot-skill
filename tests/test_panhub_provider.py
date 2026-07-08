from app.providers.panhub import _extract_merged, _extract_size


def test_extract_standard_merged_by_type():
    payload = {
        "code": 0,
        "data": {
            "merged_by_type": {
                "quark": [
                    {
                        "url": "https://pan.quark.cn/s/abc",
                        "password": "1234",
                        "note": "星际穿越 2160p REMUX 70GB",
                    }
                ]
            }
        },
    }
    merged = _extract_merged(payload)
    assert merged["quark"][0]["password"] == "1234"


def test_extract_results_with_links():
    payload = {
        "data": {
            "results": [
                {
                    "title": "测试片 1080p",
                    "links": [
                        {"type": "quark", "url": "https://pan.quark.cn/s/xyz", "password": ""}
                    ],
                }
            ]
        }
    }
    merged = _extract_merged(payload)
    assert merged["quark"][0]["note"] == "测试片 1080p"


def test_extract_size_from_note():
    assert _extract_size("电影 2160p REMUX 68.5 GB") == "68.5GB"
    assert _extract_size("没有大小") == ""
