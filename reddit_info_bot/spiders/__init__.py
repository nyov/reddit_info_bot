# -*- coding: utf-8 -*-
from __future__ import print_function

import sys
import time
import json
import logging
from pprint import pprint

try:
    # remove any already installed reactor
    del sys.modules['twisted.internet.reactor']
except KeyError: pass
# reinstall reactor
from twisted.internet.default import install
#from twisted.internet.pollreactor import install
#from twisted.internet.epollreactor import install
install()
del install

from twisted.internet import reactor

from scrapy.spiders import Spider
from scrapy.exceptions import CloseSpider
from scrapy.settings import Settings

logger = logging.getLogger(__name__)

import signal
from scrapy.crawler import CrawlerProcess as ScrapyCrawlerProcess
from scrapy.utils.ossignal import install_shutdown_handlers, signal_names

class CrawlerProcess(ScrapyCrawlerProcess):

    def __init__(self, settings=None):
        super(ScrapyCrawlerProcess, self).__init__(settings)
        install_shutdown_handlers(self._signal_shutdown)

    def _signal_shutdown(self, signum, _):
        install_shutdown_handlers(self._signal_kill)
        signame = signal_names[signum]
        reactor.callFromThread(self._graceful_stop_reactor)

    def _signal_kill(self, signum, _):
        install_shutdown_handlers(signal.SIG_IGN)
        signame = signal_names[signum]
        reactor.callFromThread(self._stop_reactor)


class InfoBotSpider(Spider):

    def __init__(self, *args, **kwargs):
        writer = kwargs.get('writer')
        self.debug_results = kwargs.get('debug_results')
        super(InfoBotSpider, self).__init__(*args, **kwargs)
        if writer:
            self.writer = writer

    def write(self, data):
        if self.debug_results:
            pprint(data)
        data = json.dumps(data)
        self.writer.write(data)
        # basic 'line writer' protocol, end with LF
        self.writer.write('\n')
        self.writer.flush()

    def finished(self):
        if self.writer:
            self.writer.flush()

    @staticmethod
    def close(spider, reason):
        finished = getattr(spider, 'finished', None)
        if callable(finished):
            finished()
        closed = getattr(spider, 'closed', None)
        if callable(closed):
            return closed(reason)

    def debug(self, response):
        from scrapy.shell import inspect_response
        inspect_response(response, self)
        raise CloseSpider('debug stop')


def crawler_setup(settings, *args, **kwargs):

    default_settings = {
        'EXTENSIONS': {
            'scrapy.telnet.TelnetConsole': None,
            'scrapy.extensions.telnet.TelnetConsole': None,
            'scrapy.extensions.spiderstate.SpiderState': None,
            'scrapy.extensions.corestats.CoreStats': None,
            'scrapy.extensions.logstats.LogStats': None,
        },
        'DOWNLOAD_HANDLERS': { 's3': None },
        'STATS_DUMP': False,
        'DOWNLOADER_STATS': False,
        'SPIDER_MODULES': [],
    }
    default_settings.update(settings.attributes)
    settings = Settings(default_settings)

    # "downgrade" some verbose scrapy loggers
    logging.getLogger('scrapy.middleware').setLevel(logging.WARNING)
    logging.getLogger('scrapy.core.engine').setLevel(logging.WARNING)

    from .search import (
        KarmaDecay,
        Yandex,
        Bing,
        Tineye,
        Google,
    )
    spiders = [
        (KarmaDecay, kwargs),
        (Yandex, kwargs),
        (Bing, kwargs),
        (Tineye, kwargs),
        (Google, kwargs),
    ]

    crawlerproc = CrawlerProcess(settings)
    for spider in spiders:
        (scls, sargs) = spider
        crawlerproc.crawl(scls, **sargs)
    crawlerproc.start() # blocking call
