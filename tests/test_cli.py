from app.cli import build_parser, is_exit_command


def test_cli_without_message_defaults_to_interactive_mode():
    args = build_parser().parse_args([])
    assert args.message == []


def test_cli_message_mode_still_accepts_one_shot_text():
    args = build_parser().parse_args(["我要看", "星际穿越"])
    assert args.message == ["我要看", "星际穿越"]


def test_cli_exit_commands_support_chinese_and_english():
    assert is_exit_command("退出")
    assert is_exit_command("quit")
    assert not is_exit_command("我要看 星际穿越")
