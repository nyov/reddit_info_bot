# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import os
import logging
import six.moves.http_cookiejar as cookielib
try:
    import BeautifulSoup as bs
except ImportError:
    import bs4 as bs
import requests
import re
from parsel import Selector
from six.moves.urllib.request import build_opener, HTTPCookieProcessor, urlopen
from six.moves.urllib.error import HTTPError

import string
from base64 import b64decode
from collections import OrderedDict
from six.moves.urllib.parse import urlsplit, urlunsplit

from .util import domain_suffix, remove_control_characters

logger = logging.getLogger(__name__)


def get_google_results(image_url, settings, limit=15): #limit is the max number of results to grab (not the max to display)
    headers = {}
    headers['User-Agent'] = settings['SEARCH_USER_AGENT']
    response_text = requests.get('https://www.google.com/searchbyimage?image_url={0}'.format(image_url), headers=headers).content
    response_text += requests.get('https://www.google.com/searchbyimage?image_url={0}&start=10'.format(image_url), headers=headers).content
    #response_text = response_text[response_text.find('Pages that include'):]
    tree = bs.BeautifulSoup(response_text)
    list_class_results = tree.findAll(attrs={'class':'r'})
    if len(list_class_results) == 0:
        raise IndexError('No results')
    if limit >= len(list_class_results):
        limit = len(list_class_results)
    results = [(list_class_results[i].find('a')['href'],re.sub('<.*?>', '', re.sub('&#\d\d;', "'", ''.join([str(j) for j in list_class_results[i].find('a').contents])))) for i in xrange(limit)]
    return results

def get_bing_results(image_url, settings, limit=15):
    cj = cookielib.MozillaCookieJar('cookies.txt')
    cj.load()
    opener = build_opener(HTTPCookieProcessor(cj))
    opener.addheaders = [('User-Agent', settings['SEARCH_USER_AGENT'])]
    response_text = opener.open("https://www.bing.com/images/searchbyimage?FORM=IRSBIQ&cbir=sbi&imgurl="+image_url).read()
    tree = bs.BeautifulSoup(response_text)
    list_class_results = tree.findAll(attrs={'class':'sbi_sp'})
    if len(list_class_results) == 0:
        raise IndexError('No results')
    if limit >= len(list_class_results):
        limit = len(list_class_results)
    results = [(list_class_results[i].findAll(attrs={'class':'info'})[0].find('a')['href'],list_class_results[i].findAll(attrs={'class':'info'})[0].find('a').contents[0]) for i in xrange(limit)]
    return results

def get_yandex_results(image_url, settings, limit=15):
    headers = {}
    headers['User-Agent'] = settings['SEARCH_USER_AGENT']
    response_text = requests.get("https://www.yandex.com/images/search?img_url={0}&rpt=imageview&uinfo=sw-1440-sh-900-ww-1440-wh-775-pd-1-wp-16x10_1440x900".format(image_url), headers=headers).content
    response_text = response_text[response_text.find("Sites where the image is displayed"):]
    tree = bs.BeautifulSoup(response_text)
    list_class_results = tree.findAll(attrs={'class':'link other-sites__title-link i-bem'})
    if len(list_class_results) == 0:
        raise IndexError('No results')
    results = []
    for a in list_class_results:
        a = str(a)
        b = "https:"+a[a.find('href="')+6:a.find('" target="')]
        filtered_link = re.compile(r'\b(amp;)\b', flags=re.IGNORECASE).sub("",b)
        try:
            redirect_url = urlopen(filtered_link).geturl()
            text = a[a.find('"_blank">')+9:a.find('</a>')]
            results.append((redirect_url,text))
        except: pass #this site bands bots and cannot be accessed
    if limit >= len(results):
        limit = len(results)
    return results[:limit]

def get_karmadecay_results(image_url, settings, limit=15):
    headers = {}
    headers['User-Agent'] = settings['SEARCH_USER_AGENT']
    response_text = requests.get("http://karmadecay.com/search?kdtoolver=b1&q="+image_url, headers=headers).content
    if "No very similar images were found." in response_text:
        return []
    raw_results_text = response_text[response_text.find(":--|:--|:--|:--|:--")+20:response_text.find("*[Source: karmadecay]")-2]
    raw_results = raw_results_text.split("\n")
    results = [(i[i.find("(",i.find(']'))+1:i.find(")",i.find(']'))],i[i.find("[")+1:i.find("]")]) for i in raw_results]
    return results #[(link,text)]

def get_tineye_results(image_url, settings, limit=15):
    def extract(r, count):
        sel = Selector(text=r.content.decode(r.encoding))
        page = sel.xpath('//div[@class="results"]//div[@class="row matches"]//div[contains(@class, "match-row")]')
        if not page:
            raise IndexError('No search results')
        if 'Your IP has been blocked' in page:
            logger.error('Tineye IP ban detected')
            raise IndexError('No search results')
        if '403 Forbidden' in page: # hmm, something else?
            raise IndexError('No search results')

        results = []
        for found in page:
            count -= 1
            if count < 0:
                break # stop after our search limit
            source_image = found.xpath('.//div[@class="match"]/p[contains(@class, "short-image-link")]/a/@href').extract_first()
            source_image_size = found.xpath('.//div[contains(@class, "match-thumb")]/p/span[2]/text()').extract_first()
            source_link = found.xpath('.//div[@class="match"]/p[not(@class)]/a/@href').extract_first()
            source_title = found.xpath('.//div[@class="match"]/h4[@title]/text()').extract_first()
            #source_text = found.xpath('.//div[@class="match"]/p[@class="crawl-date"]/text()').extract_first()

            if source_image:
                source_image = os.path.basename(source_image)
                text = '{0} {1} on {2}'.format(source_image, source_image_size, source_title)
                results += [(source_link, text)]
        return results # [(link,text)]

    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'DNT': '1',
        'Host': 'www.tineye.com',
        'Referer': 'https://www.tineye.com/',
    }
    headers['User-Agent'] = settings['SEARCH_USER_AGENT']
    response = requests.post("https://www.tineye.com/search", data={'url': image_url})

    results = extract(response, limit)
    limit = limit - len(results)
    if limit > 0: # try another page
        sel = Selector(text=response.content.decode(response.encoding))
        next_link = sel.xpath('//div[@class="pagination"]/span[@class="current"]/following-sibling::a/@href').extract_first()
        if next_link:
            response = requests.get(response.url + '?page=2')
            results += extract(response, limit)

    return results


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

    def app_proxy_search():
        link = re.sub("/","*", image_url)
        results = ''
        i = 0
        app = unicode(b64decode('aHR0cHM6Ly9zbGVlcHktdHVuZHJhLTU2NTkuaGVyb2t1YXBwLmNvbS9zZWFyY2gv'))
        while not results:
            i += 1
            try:
                if settings.getbool('DEBUG', False):
                    ### for debugging, cache response
                    _dumpfile = 'proxydebug'
                    if not os.path.exists(_dumpfile):
                        response = urlopen(app+link).read()
                        with open(_dumpfile, 'wb') as f:
                            f.write(response)
                    with open(_dumpfile, 'rb') as f:
                        response = f.read()
                else:
                    response = urlopen(app+link).read()
                results = eval(response)
            except HTTPError as e:
                logger.error(e)
                logger.info("Retrying %d" % i)
        return results

    def app_proxy_filter(result):
        # sanitizing strange remote conversions,
        # unescape previously escaped backslash
        result = [
            [x.replace('\\', '').replace(r'[', '') for x in r] for r in result
        ]

        # sanity check on app's response:
        _dropped = _ok = _all = 0
        _good = []
        for idx, item in enumerate(result):
            _all += 1
            # result should always be '(url, text)', nothing else
            if len(item) != 2:
                _dropped += 1
                continue
            (url, text) = item
            # quick check for *impossible* urls
            if not url.strip().startswith(('http', 'ftp', '//')): # http | ftp | //:
                _dropped += 1
                logger.debug('Dropping invalid proxy result "%s" (%s)' % (url, text))
                continue
            _ok += 1
            _good += [item]
        result = _good

        if _dropped > 0:
            logger.info('Dropped %d invalid result(s) from proxy for %s, %d result(s) remaining' % \
                    (_dropped, provider, _ok))
        del _dropped, _ok, _all, _good

        return result

    logger.info('Image-searching for %s' % image_url)

    image_url = optimize_image_url(image_url)

    search_engines = OrderedDict([
        ('Google', get_google_results),
        ('Bing',   get_bing_results),
        ('Yandex', get_yandex_results),
        ('Tineye', get_tineye_results),
        ('Karma Decay', get_karmadecay_results),
    ])

    proxy_results = app_proxy_search()

    results = OrderedDict()

    for provider, search_engine in search_engines.items():
        #result = search_engine(image_url, settings)
        try:
            # hardcoded results
            if provider == 'Google':
                result = proxy_results[0]
                #result = search_engine(image_url, settings)
            if provider == 'Bing':
                result = proxy_results[1]
                #result = search_engine(image_url, settings)
            if provider == 'Yandex':
                result = proxy_results[2]
                #result = search_engine(image_url, settings)
            if provider == 'Karma Decay':
                result = proxy_results[3]
                ## sometimes we get nonempty empty results...
                if result == [(u'', u'')]:
                    result = []
                #result = search_engine(image_url, settings)
            if provider == 'Tineye':
                if settings.getbool('DEBUG', False):
                    continue
                result = search_engine(image_url, settings)
        except IndexError as e:
            logger.error('Failed fetching %s results: %s' % (provider, e))

        result = app_proxy_filter(result)

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
