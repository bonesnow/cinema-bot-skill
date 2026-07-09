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


def test_source_site_management_intents():
    add = parse_intent("配置资源站 https://media.example")
    assert add.action == "source_add"
    assert add.query == "https://media.example"

    remove = parse_intent("删除资源站 media.example")
    assert remove.action == "source_remove"
    assert remove.query == "media.example"

    assert parse_intent("资源站列表").action == "source_list"
    assert parse_intent("清空资源站").action == "source_clear"
