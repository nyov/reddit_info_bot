# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import sys
import os
import logging
import time
import pickle
import json
import requests
from requests.exceptions import HTTPError, ConnectionError, Timeout
try:
    from urllib.parse import urlparse, urlunparse
except ImportError:
    from urlparse import urlparse, urlunparse
from .util import domain_suffix, tld_from_suffix, remove_control_characters

logger = logging.getLogger(__name__)


LISTS = {
    'link': set(),
    'thumb': set(),
    'text': set(),
    'user': set(),
    'tld': set(),
    'blacklist': set(),
    'whitelist': set(),
}


def _strip_scheme(url):
    (scheme, netloc, path, params, query, fragment) = urlparse(url)
    return urlunparse(('', netloc, path, params, query, fragment))

def _check(string, list):
    """ check for string in items in list """
    return '|'.join([thing for thing in list if thing in string])


def sync_rarchives_spamdb(filter_type, last_update=None):
    """Pull data from the spambot.rarchives.com database

    in a (hopefully) least-bothersome way (since it's just
    a small, and apparently memory-limited, sqlite app).
    """
    # This means we pull smallish chunks, iteratively, so the
    # remote db doesn't need to pull a big dataset into memory
    # and lock up or die.
    self = sync_rarchives_spamdb
    api_url = 'http://spambot.rarchives.com/api.cgi'
    filters_url = '%s?method=get_filters&start={start}&count={count}&type={type}' % api_url
    filter_changes_url = '%s?method=get_filter_changes&start={start}&count={count}&type={type}' % api_url
    last_update_url = '%s?method=get_last_update' % api_url

    def fetch_data(url):
        try:
            logger.debug('%s: downloading %s' % (self.__name__, url))
            response = requests.get(url).text
            data = json.loads(response)
            if 'error' in data:
                return (False, data['error'])
            return (True, data)
        except (HTTPError, ConnectionError, Timeout, ValueError) as e:
            return (False, str(e))

    if not last_update: # no deltas, fetch everything
        count = 500 # number of db-results per request, pick a balanced value
                    # (not too many request, not too much data per request)
        start = failcount = 0
        total = count
        filters = []
        while True:
            ok, data = fetch_data(filters_url.format(start=start, count=count, type=filter_type))
            if not ok: # or ('filters' not in data):
                logger.debug('%s: errored: %s' % (self.__name__, data))
                failcount += 1
                if failcount > 3:
                    break
                if 'database is locked' in data:
                    # back off and hope the remote will recover
                    time.sleep(failcount*3)
                # try again
                logger.debug('%s: retrying (%s)' % (self.__name__, failcount))
                continue
            if 'filters' not in data or 'total' not in data:
                # unknown content
                break

            filters += list(data['filters'])

            start += count
            #start = data['start']
            total = int(data['total'])
            if start > total: # all done
                logger.debug('%s: fetched %d %s filters.' % (self.__name__, total, filter_type))
                filters = json.dumps({
                    'total': total,
                    'type': filter_type,
                    'filters': filters,
                })
                return filters
            failcount = 0
        return None
    else: # compile deltas to patch our local dataset
        # TODO
        return None

def get_filter(filter_type, cachedir):
    filename = '{1}spamfilter_{0}.json'.format(filter_type, cachedir)

    def cache_filters(filter_type):
        response = sync_rarchives_spamdb(filter_type)
        if not response:
            msg = 'Spamfilter update failed, using cached files (if available)'
            logger.warning(msg)
        else:
            with open(filename, 'wb') as outf:
                outf.write(response.encode('utf-8'))

    if not os.path.isfile(filename) or \
            (int(time.time() - os.path.getmtime(filename)) > 43200): # cache 24 hours
        logger.info('Downloading spambot.rarchives.com list: %s filters' % filter_type)
        cache_filters(filter_type)
        if not os.path.isfile(filename):
            errmsg = "Could not load spam filters. Cached files invalid or Network failure."
            sys.exit(errmsg) # quick&ugly, sorry

    filters = None
    try:
        with open(filename, 'r') as inf:
            filters = json.load(inf)['filters']
    except (ValueError, KeyError): # cached file contents invalid
        os.unlink(filename)
        errmsg = "Could not load spam filters. Cached files invalid or Network failure."
        sys.exit(errmsg)

    filters = set(val['spamtext'] for val in filters)
    return filters

cachedir = None

def populate_spamfilter_lists(cache_dir=None):
    # s.r.c filters
    global cachedir
    if not cachedir:
        if not cache_dir:
            return
        cachedir = cache_dir

    link_filter = get_filter('link', cachedir)
    link_filter = set(_strip_scheme(link) for link in link_filter)
    thumb_filter = get_filter('thumb', cachedir)
    tld_filter = get_filter('tld', cachedir)
    tld_filter = set(tld.strip('.') for tld in tld_filter)
    text_filter = get_filter('text', cachedir)
    user_filter = get_filter('user', cachedir)

    blacklist = set()
    whitelist = set('reddit.com')

    global LISTS
    LISTS = {
        'link': link_filter,
        'thumb': thumb_filter,
        'tld': tld_filter,
        'text': text_filter,
        'user': user_filter,
        'blacklist': blacklist, # domains
        'whitelist': whitelist, # domains
    }

def spamfilter_lists(cache_dir=None):
    global LISTS
    return LISTS

def isspam_link(url):
    global LISTS

    if len(url) < 6: # shorter than '//a.bc' can't be a useable absolute HTTP URL
        logger.debug('Skipping invalid URL: "{0}"'.format(url))
        return True

    url = _strip_scheme(url)

    # domain from URL using publicsuffix (not a validator)
    domain, fulldomain = domain_suffix(url)
    if not domain:
        logger.debug('Failed to lookup PSL/Domain for: "{0}"'.format(url))
        return True

    tld = tld_from_suffix(domain)
    if not tld or tld == '':
        logger.debug('Failed to lookup TLD from publicsuffix for: "{0}"'.format(url))
        return True

    if domain in LISTS['whitelist']:
        # higher prio than the blacklist
        return False

    if domain in LISTS['blacklist']:
        logger.debug('Skipping blacklisted Domain "{0}": {1}'.format(domain, url))
        return True

    if tld in LISTS['tld']:
        logger.debug('Skipping blacklisted TLD "{0}": {1}'.format(tld, url))
        return True

    inlist = _check(url, LISTS['link']) # perfect match (100% certainty)
    if inlist:
        logger.debug('Skipping spammy link match "{0}": {1}'.format(inlist, url))
        return True
    inlist = _check(fulldomain, LISTS['link']) # full match (~80% certainty)
    if inlist:
        logger.debug('Skipping spammy link match "{0}": {1}'.format(inlist, fulldomain))
        return True
    inlist = _check(domain, LISTS['link']) # partial match (~50% certainty)
    if inlist:
        logger.debug('Skipping spammy link match "{0}": {1}'.format(inlist, domain))
        return True

    inlist = _check(url, LISTS['thumb'])
    if inlist:
        logger.debug('Skipping spammy thumb match "{0}": {1}'.format(inlist, url))
        return True

    # no spam, result is good
    return False

def isspam_text(text):
    """check search result for spammy content
    """
    global LISTS

    inlist = _check(text, LISTS['text'])
    if inlist:
        logger.debug('Skipping spammy text match "{0}": "{1}"'.format(inlist, text))
        return True

    inlist = _check(text, LISTS['user'])
    if inlist:
        logger.debug('Skipping spammy user match "{0}": "{1}"'.format(inlist, text))
        return True

    # no spam, result is good
    return False
