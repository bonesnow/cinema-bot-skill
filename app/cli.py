from __future__ import annotations

import argparse
import asyncio

from .config import Settings
from .service import MediaService


async def _run(message: str):
    service = MediaService(Settings.from_env())
    print(await service.handle(message))


def main():
    parser = argparse.ArgumentParser(description="Test Cinema Bot locally")
    parser.add_argument("message", nargs="+", help="message to process")
    args = parser.parse_args()
    asyncio.run(_run(" ".join(args.message)))


if __name__ == "__main__":
    main()
