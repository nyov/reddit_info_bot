# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import os
import logging
import string
import json
import six
from collections import OrderedDict
from six.moves.urllib.parse import urlsplit, urlunsplit
from scrapy.item import Item, Field

from .util import domain_suffix, sanitize_string

logger = logging.getLogger(__name__)

if six.PY3:
    unicode = str


class SearchResultItem(Item):
    """ Search Result set

    Fields for use in Result template formatting.
    """
    provider = Field()
    url = Field()
    title = Field()
    description = Field()
    serp = Field()
    spam = Field()
    image_url = Field()
    image_size = Field()
    image_format = Field()

    image_filesize = Field() # not on Google, KarmaDecay, Yandex
    display_url = Field() # not on KarmaDecay, Tineye
    # results tagged by spamfilter
    spam = Field()
    # results marked broken by link-check
    broken = Field()

    # unused
    image_thumb_url = Field()
    image_thumb_size = Field()


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
        video_extensions = tuple(['.%s' % e.strip('.') for e in settings.getlist('VIDEO_EXTENSIONS')] +
                ['.%s' % e.strip('.') for e in settings.getlist('OTHER_EXTENSIONS')])
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

        result = None
        try:
            result = json.loads(data)
        except ValueError:
            logger.error('Error decoding Spider data: %s' % (data,))
        if not result:
            continue
        # result must have a search provider
        if not 'provider' in result:
            continue # should not happen

        result = SearchResultItem(result)

        provider = result['provider']
        if not provider in results:
            results[provider] = []

        results[provider].append(result)

    pid, status = os.waitpid(pid, 0)
    reader.close()

    # do not forget about empty results
    providers = ['KarmaDecay', 'Yandex', 'Bing', 'Tineye', 'Google']
    for provider in providers:
        if not provider in results:
            results[provider] = []

    # sort (by provider) for constant key order
    results = OrderedDict(sorted(results.items()))
    return results

def filter_image_search(settings, search_results, account1=None, account2=None, display_limit=None):

    from .reddit import reddit_messagefilter

    stats = OrderedDict()
    filtered_results = OrderedDict()
    for provider, results in search_results.items():
        filtered_results[provider] = []

        stats[provider] = {'all': len(results), 'succeeded': 0}
        if not results:
            continue

        for result in results:
            for key, value in result.items():
                if isinstance(value, (str, unicode)):
                    result[key] = sanitize_string(value)

        # spam-filter results
        logger.debug('...filtering results for %s' % provider)
        for result in results:
            # remove items marked spammy
            if 'spam' in result and result['spam']:
                continue
            # remove items marked broken
            if 'broken' in result and result['broken']:
                continue
            filtered_results[provider].append(result)

        if not filtered_results[provider]:
            continue
        stats[provider].update({'succeeded': len(filtered_results[provider])})

    # reddit-spamfilter results
    verified_results = OrderedDict()
    submission_id = settings.get('REDDIT_SPAMFILTER_SUBMISSION_ID', None)
    if not (account1 and account2 and submission_id):
        verified_results = filtered_results
        logger.info('reddit_spamfilter skipped (missing settings)')
    else:
        urls = set()
        for _, results in filtered_results.items():
            urls |= set([result['url'] for result in results])

        if display_limit:
            # limit url checks on reddit to sane number of results
            # TODO: better implementation in reddit_messagefilter
            cutoff_limit = display_limit+5 # (expect about 5 spam links)
            urls = list(urls)[:cutoff_limit]

        verified_urls = reddit_messagefilter(urls, account2, account1, submission_id)

        for provider, results in filtered_results.items():
            verified_results[provider] = []
            stats[provider].update({'succeeded': 0})

            res = []
            for result in results:
                if 'url' in result and result['url'] in verified_urls:
                    res.append(result)

            if not res:
                continue

            verified_results[provider] = res
            stats[provider].update({'succeeded': len(res)})

    # stats
    for provider, stats in stats.items():
        logger.info('%11s: all: %3d / failed: %3d / good: %3d' % (provider,
            stats.get('all'), stats.get('all')-stats.get('succeeded'), stats.get('succeeded')))

    if not display_limit:
        return verified_results

    # limit output to `display_limit` results
    for provider, results in verified_results.items():
        if not results:
            continue
        results = results[:display_limit]
        verified_results[provider] = results
    return verified_results

def format_image_search(settings, search_results, metainfo={}, escape_chars=True):

    from .reddit import reddit_markdown_escape

    results_item_format = settings.get('BOTCMD_IMAGESEARCH_RESULT_TEMPLATE').decode('utf-8')
    results_message_format = settings.get('BOTCMD_IMAGESEARCH_MESSAGE_TEMPLATE').decode('utf-8')
    no_engine_results_message = settings.get('BOTCMD_IMAGESEARCH_NO_SEARCHENGINE_RESULTS_MESSAGE').decode('utf-8')
    reply = ''

    def reddit_format_results(results, escape_chars=True):
        """Format search results for reddit.

        All result dict keys can be used in "BOTCMD_IMAGESEARCH_RESULT_TEMPLATE"
        template string. Returns a template-formatted list of items.
        """
        items = []
        for result in results:
            result = dict(result)
            if escape_chars:
                for key, value in result.items():
                    result[key] = reddit_markdown_escape(value)

            # quote url whitespace, really shouldn't happen :(
            result['url'] = result['url'].replace(' ', '%20')

            # add result['text'] key with best possible textual value
            text = result['title']
            if not text:
                text = result['description']
            if not text:
                text = result['display_url']
            if not text:
                text = result['url']
            result['text'] = text

            entry = results_item_format.format(**result)
            items.append(entry)

        formatted = '\n'.join(items)
        return formatted

    check_results = {}
    for provider, results in search_results.items():

        if not results:
            reply += results_message_format.format(
                    search_engine=provider,
                    search_results=no_engine_results_message,
                )
            continue

        # format results
        formatted = reddit_format_results(results, escape_chars)
        reply += results_message_format.format(
                search_engine=provider,
                search_results=formatted,
            )

        check_results[provider] = results

    if not check_results:
        reply = ''

    wordcloud_link = metainfo.get('wordcloud')
    if wordcloud_link:
        wcmessage = settings.get('BOTCMD_IMAGESEARCH_WORDCLOUD_TEMPLATE').decode('utf-8')
        reply += wcmessage.format(wordcloud_link=wordcloud_link)

    if not reply:
        reply = settings.get('BOTCMD_IMAGESEARCH_NO_RESULTS_MESSAGE').decode('utf-8')

    reply += settings.get('FOOTER_INFO_MESSAGE').decode('utf-8')
    return reply

def filter_wordcloud_text(settings, search_results):
    """ Prepare text for wordcloud

    (Generated from all search result data, not excluding entries marked spam
     or no longer available.)
    """

    text = []

    for provider, results in search_results.items():
        if not results:
            continue

        for result in results:
            for key, value in result.items():
                if isinstance(value, (str, unicode)):
                    result[key] = sanitize_string(value)

            # wordcloud
            # from title and description text
            if result['title']:
                text += result['title'].split()
            if result['description']:
                text += result['description'].split()
            # /wordcloud

    text = ' '.join(text)

    # hardcoded removal of nonrelevant text
    # (prefer using stopwords in wordcloud)
    #eradicate = []
    #for strng in eradicate:
    #    text = text.replace(strng, '')

    return text
