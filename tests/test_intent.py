from app.service import parse_intent


def test_natural_search():
    intent = parse_intent("我想看 星际穿越")
    assert intent.action == "search"
    assert intent.query == "星际穿越"


def test_direct_quark_link():
    intent = parse_intent("保存 https://pan.quark.cn/s/Abc123 提取码 8888")
    assert intent.action == "save"
    assert intent.passcode == "8888"


def test_quark_qr_login_intent():
    assert parse_intent("夸克登录").action == "quark_login"
    assert parse_intent("退出夸克").action == "quark_logout"
