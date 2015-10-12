#!/usr/bin/python -u
import sys

if __name__ == '__main__':
    from reddit_info_bot.cli import execute
    sys.exit(
        execute()
    )
