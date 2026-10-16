"""Compatibility command; always start the integrated main host."""
import asyncio
import multiprocessing
from .xueya.server import serve


def main():
    multiprocessing.freeze_support()
    asyncio.run(serve())


if __name__ == '__main__':
    main()
