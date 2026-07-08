from app.models import ResourceResult
from app.scoring import score_resource


def test_4k_beats_1080p():
    four_k = ResourceResult("Movie 2160p WEB-DL HDR 中字", "https://pan.quark.cn/s/a")
    full_hd = ResourceResult("Movie 1080p WEB-DL", "https://pan.quark.cn/s/b")
    assert score_resource(four_k) > score_resource(full_hd)
