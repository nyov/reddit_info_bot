# -*- coding: utf-8 -*-
from __future__ import print_function

import sys
import time
import json
import logging
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

# apply monkey patches for scrapy
from . import _monkeypatches
del _monkeypatches

from scrapy.spiders import Spider
from scrapy.exceptions import CloseSpider
from scrapy.settings import Settings

from scrapy.http import Request
from ..spamfilter import isspam_link, isspam_text
from ..util import http_code_ranges

logger = logging.getLogger(__name__)


# CrawlerProcess
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


# RewriteRedirectMiddleware
from scrapy.downloadermiddlewares.redirect import RedirectMiddleware
from six.moves.urllib.parse import urljoin, urlsplit, urlunsplit
from scrapy.utils.python import to_native_str
from ..util import domain_suffix, tld_from_suffix

class RewriteRedirectMiddleware(RedirectMiddleware):
    """ Handle redirection of requests based on response status and meta-refresh html tag

    Extended with custom location rewrites.
    """

    def process_response(self, request, response, spider):
        if (request.meta.get('dont_redirect', False) or
                response.status in getattr(spider, 'handle_httpstatus_list', []) or
                response.status in request.meta.get('handle_httpstatus_list', []) or
                request.meta.get('handle_httpstatus_all', False)):
            return response

        allowed_status = (301, 302, 303, 307)
        if 'Location' not in response.headers or response.status not in allowed_status:
            return response

        return self.handle_redirect(request, response, spider)

    def handle_redirect(self, request, response, spider):
        # HTTP header is ascii or latin1, redirected url will be percent-encoded utf-8
        location = to_native_str(response.headers['location'].decode('latin1'))

        redirected_url = urljoin(request.url, location)

        redirected_url = self.rewrite_redirect(redirected_url, response.url)

        if response.status in (301, 307) or request.method == 'HEAD':
            redirected = request.replace(url=redirected_url)
        else:
            redirected = self._redirect_request_using_get(request, redirected_url)
        return self._redirect(redirected, request, spider, response.status)

    def rewrite_redirect(self, url, oldurl):

        def replace_tld(netloc, oldtld, newtld):
            sep = netloc.find(oldtld)
            if sep > 0:
                newloc = netloc[:sep] + newtld
                return newloc

        domain, fulldomain = domain_suffix(url)
        tld = tld_from_suffix(domain)

        # Google: force lookup of .com results
        if domain.split('.')[:1][0] == 'google':
            domainparts = urlsplit(url)
            (scheme, _netloc, path, query, fragment) = domainparts
            newloc = replace_tld(fulldomain, tld, 'com')
            if not newloc:
                return url
            url = urlunsplit((scheme, newloc, path, query, fragment))

            msg = "Rewriting %s redirect to %s" % (fulldomain, newloc)
            logger.debug(msg)

        return url


# ItemPipeline
from scrapy.exceptions import DropItem

writer = None
def collector_pipeline_writer(writefd=None):
    global writer
    if not writer:
        if not writefd:
            return
        writer = writefd
    return writer

class ResultCollectorPipeline(object):

    def __init__(self, writer):
        if not writer:
            raise NotConfigured
        self.writer = writer

    @classmethod
    def from_settings(cls, settings):
        o = cls(collector_pipeline_writer())
        o.debug = settings.getbool('RESULTCOLLECTOR_DEBUG')
        return o

    def process_item(self, item, spider):
        """ basic 'line writer' protocol, end line with LF """
        data = json.dumps(dict(item))
        self.writer.write(data)
        self.writer.write('\n')
        self.writer.flush()

        if self.debug:
            return item

        # drop; don't propagate item to other pipelines
        raise DropItem()


class InfoBotSpider(Spider):

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
            return result

        if response.status != 200:
            self.logger.info(
                "Ignoring %s result with bad response status (%s): %s" % (
                    result['provider'], response.status, response.url))
            result['broken'] = True
            #return

        return result


def crawler_setup(settings, *args, **kwargs):

    # telnet extension workaround
    # (simply including both in EXTENSIONS fails on scrapy 1.1+:
    #  "Some paths in settings convert to the same object")
    from scrapy import __version__ as scrapy_version
    if scrapy_version[:3] == '1.0':
        telnet_ext = 'scrapy.telnet.TelnetConsole'
    else:
        telnet_ext = 'scrapy.extensions.telnet.TelnetConsole'

    # ResultCollectorPipeline file descriptor
    # ...hacky, hacky, hacky :|
    collector_pipeline_writer(kwargs.pop('writer'))

    default_settings = {
        'EXTENSIONS': {
            telnet_ext: None,
            'scrapy.extensions.spiderstate.SpiderState': None,
            'scrapy.extensions.corestats.CoreStats': None,
            'scrapy.extensions.logstats.LogStats': None,
        },
        'DOWNLOAD_HANDLERS': { 's3': None },
        'STATS_DUMP': False,
        'DOWNLOADER_STATS': False,
        'SPIDER_MODULES': [],
        #
        'DOWNLOADER_MIDDLEWARES': {
            'scrapy.downloadermiddlewares.redirect.RedirectMiddleware': None,
            RewriteRedirectMiddleware: 600,
        },
        'ITEM_PIPELINES': {
            ResultCollectorPipeline: 800,
        },
        'RESULTCOLLECTOR_DEBUG': kwargs.pop('debug_results'),
    }
    default_settings.update(settings.attributes)
    settings = Settings(default_settings)

    # shut up some verbose scrapy loggers
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
