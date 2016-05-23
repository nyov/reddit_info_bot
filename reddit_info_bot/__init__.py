"""
reddit_info_bot
"""
from __future__ import absolute_import, unicode_literals

# apply monkey patches for scrapy
from . import _monkeypatches
del _monkeypatches

from .version import __version__, version_info
from .cli import execute
