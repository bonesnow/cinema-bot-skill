from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence

from .config import Settings
from .service import MediaService


EXIT_COMMANDS = {"exit", "quit", "q", "bye", "退出", "再见", "结束"}


def is_exit_command(text: str) -> bool:
    return text.strip().lower() in EXIT_COMMANDS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Cinema Bot locally")
    parser.add_argument(
        "message",
        nargs="*",
        help="message to process once; omit it to enter local Q&A mode",
    )
    return parser


async def _run_message(message: str) -> str:
    service = MediaService(Settings.from_env())
    return await service.handle(message)


async def _run_once(message: str) -> None:
    print(await _run_message(message))


async def _run_interactive() -> None:
    service = MediaService(Settings.from_env())
    print("Cinema Bot 本地问答模式")
    print("输入“我要看 星际穿越”、“状态”或“帮助”。输入“退出”结束。")
    while True:
        try:
            message = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            return
        if not message:
            continue
        if is_exit_command(message):
            print("再见。")
            return
        reply = await service.handle(message)
        print(f"\nBot> {reply}")


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.message:
        asyncio.run(_run_once(" ".join(args.message)))
        return
    asyncio.run(_run_interactive())


if __name__ == "__main__":
    main()
