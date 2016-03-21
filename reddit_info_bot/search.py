# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import os
import logging
import string
from collections import OrderedDict
from six.moves.urllib.parse import urlsplit, urlunsplit

from .util import domain_suffix, remove_control_characters

logger = logging.getLogger(__name__)


def optimize_image_url(image_url):
    # substitute videos with gif versions where possible
    # (because search engines index those)
    domain = domain_suffix(image_url)
    fileformats = ('.gifv', '.mp4', '.webm', '.ogg')
    if domain in ('imgur.com', 'gfycat.com'):
        domainparts = urlsplit(image_url)
        if image_url.endswith(fileformats):
            for ff in fileformats:
                image_url = image_url.replace(ff, '.gif')
            logger.debug('Found %s video - substituting with gif url: %s' % (domain, image_url))
        # no file extension?
        elif domainparts.path.rstrip(string.ascii_lowercase+string.ascii_uppercase) == '/':
            # on imgur, this could be a regular image, but luckily imgur provides a .gif url anyway :)
            # on gfycat we must also change domain to 'giant.gfycat.com'
            if str(domain) == 'gfycat.com':
                (scheme, netloc, path, query, fragment) = domainparts
                #maybe_handy_json_url = urlunsplit((scheme, netloc, '/cajax/get' + path, query, fragment))
                image_url = urlunsplit((scheme, 'giant.gfycat.com', path, query, fragment))
            image_url += '.gif'
            logger.debug('Found potential %s video - using gif url: %s' % (domain, image_url))
    return image_url

def image_search(settings, image_url):

    logger.info('Image-searching for %s' % image_url)

    image_url = optimize_image_url(image_url)

    search_engines = OrderedDict([
        ('Google', None),
        ('Bing',   None),
        ('Yandex', None),
        ('Tineye', None),
        ('Karma Decay', None),
    ])

    results = OrderedDict()

    for provider, search_engine in search_engines.items():
        try:
            result = search_engine(image_url, settings)
        except IndexError as e:
            logger.error('Failed fetching %s results: %s' % (provider, e))

        results[provider] = result

    return results

def filter_image_search(settings, search_results, account1=None, account2=None):

    from .reddit import reddit_messagefilter
    from .spamfilter import spamfilter_results

    def sanitize_string(string):
        # strip possible control characters
        string = remove_control_characters(string)

        # also strip non-ascii characters
        #string = ''.join(c for c in string if ord(c) in range(32, 127))

        string = string.strip()
        return string

    stats = OrderedDict()
    filtered_results = OrderedDict()
    for provider, result in search_results.items():
        filtered_results[provider] = []

        stats[provider] = {'all': len(result), 'succeeded': 0}
        if not result:
            continue

        result = [[sanitize_string(v) for v in r] for r in result]

        # spam-filter results
        logger.debug('...filtering results for %s' % provider)
        filtered = spamfilter_results(result)
        if not filtered:
            continue

        filtered_results[provider] = filtered
        stats[provider].update({'succeeded': len(filtered)})

    # reddit-spamfilter results
    verified_results = OrderedDict()
    submission_id = settings.get('REDDIT_SPAMFILTER_SUBMISSION_ID', None)
    if not (account1 and account2 and submission_id):
        verified_results = filtered_results
        logger.info('reddit_spamfilter skipped (missing settings)')
    else:
        urls = set()
        for _, results in filtered_results.items():
            urls |= set([url for url, text in results])

        verified_urls = reddit_messagefilter(urls, account2, account1, submission_id)

        for provider, results in filtered_results.items():
            verified_results[provider] = []
            stats[provider].update({'succeeded': 0})

            res = []
            for result in results:
                url = result[0]
                if url in verified_urls:
                    res.append(result)

            if not res:
                continue

            verified_results[provider] = res
            stats[provider].update({'succeeded': len(res)})

    # stats
    for provider, stats in stats.items():
        logger.info('%11s: all: %3d / failed: %3d / good: %3d' % (provider,
            stats.get('all'), stats.get('all')-stats.get('succeeded'), stats.get('succeeded')))

    return verified_results

def format_image_search(settings, search_results, display_limit=None, escape_chars=True):

    from .reddit import reddit_format_results

    results_message_format = settings.get('BOTCMD_IMAGESEARCH_MESSAGE_TEMPLATE').decode('utf-8')
    no_engine_results_message = settings.get('BOTCMD_IMAGESEARCH_NO_SEARCHENGINE_RESULTS_MESSAGE').decode('utf-8')
    reply = ''

    check_results = {}
    for provider, result in search_results.items():

        if not result:
            reply += results_message_format.format(
                    search_engine=provider,
                    search_results=no_engine_results_message,
                )
            continue

        # limit output to `display_limit` results
        if display_limit:
            result = result[:display_limit]

        # format results
        formatted = reddit_format_results(result, escape_chars)
        reply += results_message_format.format(
                search_engine=provider,
                search_results=formatted,
            )

        check_results[provider] = result

    if not check_results:
        reply = ''

    if not reply:
        reply = settings.get('BOTCMD_IMAGESEARCH_NO_RESULTS_MESSAGE').decode('utf-8')

    reply += settings.get('FOOTER_INFO_MESSAGE').decode('utf-8')
    return reply
