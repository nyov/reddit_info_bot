# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import os
import logging
import string
import json
from collections import OrderedDict
from six.moves.urllib.parse import urlsplit, urlunsplit

from .util import domain_suffix, remove_control_characters

logger = logging.getLogger(__name__)


# Define special domains which only host image or video media,
# and where that media can be found.
media_only_domains = {
    'imgur.com': 'i.imgur.com',
    'gfycat.com': 'giant.gfycat.com',
    'pbs.twimg.com': 'pbs.twimg.com',
    'upload.wikimedia.org': 'upload.wikimedia.org',
}

def is_media_domain(url):
    ps, domain = domain_suffix(url)
    if ps in media_only_domains.keys():
        return media_only_domains[ps]
    if domain in media_only_domains.keys():
        return media_only_domains[domain]
    return False

def find_media_url(url, settings):
    """ Find a direct media link from an url """
    domain = is_media_domain(url)
    if not domain:
        return url

    # correct domain name
    domainparts = urlsplit(url)
    (scheme, netloc, path, query, fragment) = domainparts
    #if netloc == 'gfycat.com':
    #   maybe_handy_json_url = urlunsplit((scheme, netloc, '/cajax/get' + path, query, fragment))
    url = urlunsplit((scheme, domain, path, query, fragment))

    # add a file extension to shortcut links
    if domain in ('i.imgur.com', 'giant.gfycat.com'):
        video_extensions = ['.%s' % e.strip('.') for e in settings.getlist('VIDEO_EXTENSIONS')] + \
                           ['.%s' % e.strip('.') for e in settings.getlist('OTHER_EXTENSIONS')]
        # substitute videos with gif versions where possible
        # (because search engines index those as images)
        if url.endswith(video_extensions):
            for ext in video_extensions:
                url = url.replace(ext, '.gif')
            logger.debug('Found %s video - substituting with gif url: %s' % (domain, url))

        # no file extension? if it doesn't contain any path delimiters, consider it a shortlink
        elif domainparts.path.rstrip(string.ascii_letters+string.digits) == '/':
            # on imgur, this could be a regular image, but luckily imgur provides a .gif url anyway :)
            # gfycat.com always has gif
            url += '.gif'
            logger.debug('Found potential %s video - using gif url: %s' % (domain, url))

    return url

def image_search(settings, **spiderargs):
    from .spiders import crawler_setup

    image_url = spiderargs.get('image_url')
    image_data = spiderargs.get('image_data')
    if image_url:
        logger.info('Image-searching for %s' % image_url)
    elif image_data:
        logger.info('Image-searching for (image data)')
    else:
        return

    pipein, pipeout = os.pipe()
    pid = os.fork()
    if pid < 0:
        raise OSError('Forking child process failed.')

    if pid == 0: # child process
        os.close(pipein)
        writer = os.fdopen(pipeout, 'wb')
        statuscode = crawler_setup(settings, writer=writer, **spiderargs)
        writer.flush()
        writer.close()
        if not statuscode:
            statuscode = 0
        os._exit(int(statuscode))
        return # finis

    # parent process
    os.close(pipeout)
    reader = os.fdopen(pipein, 'rb')

    results = {}
    while True:
        # simple line-based protocol
        data = reader.readline()[:-1]
        if not data or len(data) == 0:
            break

        response = None
        try:
            response = json.loads(data)
        except ValueError:
            logger.error('Error decoding Spider data: %s' % (data,))
        if response:
            provider = None
            link = title = ''
            if 'provider' in response:
                provider = response['provider']
            if 'link' in response:
                link = response['link']
            if 'title' in response:
                title = response['title']

            if not provider in results:
                results[provider] = []
            results[provider].append([link, title])

    pid, status = os.waitpid(pid, 0)
    reader.close()

    # do not forget about empty results
    providers = ['KarmaDecay', 'Yandex', 'Bing', 'Tineye', 'Google']
    for provider in providers:
        if not provider in results:
            results[provider] = []

    # sort for constant key order
    results = OrderedDict(sorted(results.items()))
    return results

def filter_image_search(settings, search_results, account1=None, account2=None):

    from .reddit import reddit_messagefilter
    from .spamfilter import spamfilter_results

    def sanitize_string(string):
        if string is None:
            return ''

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
