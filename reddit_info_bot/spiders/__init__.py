# -*- coding: utf-8 -*-
from __future__ import print_function

import sys
import time
import json
import logging
from pprint import pprint
from functools import partial

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
from twisted.internet.error import TimeoutError

from scrapy.spiders import Spider
from scrapy.exceptions import CloseSpider
from scrapy.settings import Settings

import signal
from scrapy.crawler import CrawlerProcess as ScrapyCrawlerProcess
from scrapy.utils.ossignal import install_shutdown_handlers, signal_names

from scrapy.http import Request
from ..spamfilter import isspam_link, isspam_text
from ..util import http_code_ranges

logger = logging.getLogger(__name__)


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

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        o = super(InfoBotSpider, cls).from_crawler(crawler, *args, **kwargs)

        codes = http_code_ranges()
        o.GOOD_HTTP_CODES  = set(o.crawler.settings.getlist('GOOD_HTTP_CODES' )) or codes['100'] | codes['200']
        o.REDIR_HTTP_CODES = set(o.crawler.settings.getlist('REDIR_HTTP_CODES')) or codes['300']
        o.RETRY_HTTP_CODES = set(o.crawler.settings.getlist('RETRY_HTTP_CODES', [408, 500, 502, 503, 504]))
        o.ERROR_HTTP_CODES = set(o.crawler.settings.getlist('ERROR_HTTP_CODES')) or (codes['400'] | codes['500'] | codes['EXT']) - o.RETRY_HTTP_CODES

        o.LINKCHECK_TIMEOUT = o.crawler.settings.get('DOWNLOAD_TIMEOUT_LINKCHECK', o.crawler.settings.get('DOWNLOAD_TIMEOUT'))
        return o

    def write(self, data):
        if self.debug_results:
            pprint(data)
        if not isinstance(data, dict):
            data = dict(data)
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

    ####

    @staticmethod
    def isredditspam_link(link):
        if not link:
            return False
        return isspam_link(link.lower())

    @staticmethod
    def isredditspam_text(text):
        if not text:
            return False
        return isspam_text(text.lower())

    # result item returned by search
    def parse_result(self, result):
        if not 'url' in result or not result['url']:
            # investigate unusable results, that shouldn't happen.
            self.logger.warning("bad result (no URL): %r" % result)
            return

        #
        # link-check, ignore broken/dead link results
        #

        def _onerror(result, failure):
            """ handle TimeoutError tracebacks getting dumped to stderr """
            exc = failure.trap(TimeoutError) # any other exception gets re-raised right here
            errmsg = failure.getErrorMessage()
            self.logger.info(
                "Ignoring %s result with %s: %s (%s)" % (
                    result['provider'], str(exc.__name__), result['url'], errmsg))
            result['broken'] = True
            return result

        url = result['url']
        reqmethod = 'GET'
        if result['image_url']:
            # If we have an image_url, check the direct link.
            # It's more important to us than the page it was found on.
            url = result['image_url']
            reqmethod = 'HEAD' # save on download size
        return Request(url, method=reqmethod, callback=self.analyze_result, meta={
                'result': result,
                #'handle_httpstatus_all': True,
                'handle_httpstatus_list': list(self.GOOD_HTTP_CODES | self.ERROR_HTTP_CODES),
                'download_timeout': self.LINKCHECK_TIMEOUT,
            }, errback=partial(_onerror, result))

    def analyze_result(self, response):
        result = response.meta['result']

        if response.status == 405 and response.request.method == 'HEAD':
            # "Method not allowed" - retry as GET
            url = result['url']
            if result['image_url']:
                url = result['image_url']
            # consider valid for now
            # FIXME: retry as GET request
            return self.write(result)

        if response.status != 200:
            self.logger.info(
                "Ignoring %s result with bad response status (%s): %s" % (
                    result['provider'], response.status, response.url))
            result['broken'] = True
            #return

        return self.write(result)


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
