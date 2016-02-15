# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import sys
import os
import logging
import time
import pickle
import json
import requests
try:
    from sys import intern
except ImportError:
    intern = lambda x: x # dont use on py2 unicode strings # FIXME (do we need unicode here?)
from requests.exceptions import HTTPError, ConnectionError, Timeout
from .util import domain_suffix, tld_from_suffix

logger = logging.getLogger(__name__)


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
            response = requests.get(url).content
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
                outf.write(response)

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

    filters = set(intern(i['spamtext']) for i in filters)
    return filters


def spamfilter_lists(cachedir):
    # s.r.c filters
    link_filter = get_filter('link', cachedir)
    thumb_filter = get_filter('thumb', cachedir)
    text_filter = get_filter('text', cachedir)
    user_filter = get_filter('user', cachedir)
    tld_filter = get_filter('tld', cachedir)
    #
    link_filter = link_filter | thumb_filter
    text_filter = text_filter | user_filter
    tld_blacklist = set(''.join(letter for letter in tld if letter != '.')
                        for tld in tld_filter)

    hard_blacklist = set()
    whitelist = set('reddit.com')

    return (
        link_filter,
        text_filter,
        hard_blacklist,
        whitelist,
        tld_blacklist,
    )


def isspam(result, lists):
    """check search result for spammy content
    """
    (link_filter, text_filter, hard_blacklist,
     whitelist, tld_blacklist) = lists

    url, text = result[0].lower(), result[1].lower()

    if len(url) < 6: # shorter than '//a.bc' can't be a useable absolute HTTP URL
        logger.info('Skipping invalid URL: "{0}"'.format(url))
        return True
    # domain from URL using publicsuffix (not a validator)
    domain = domain_suffix(url)
    if not domain:
        logger.info('Failed to lookup PSL/Domain for: "{0}"'.format(url))
        return True
    tld = tld_from_suffix(domain)
    if not tld or tld == '':
        logger.info('Failed to lookup TLD from publicsuffix for: "{0}"'.format(url))
        return True
    if domain in whitelist:
        # higher prio than the blacklist
        return False
    if domain in hard_blacklist:
        logger.info('Skipping blacklisted Domain "{0}": {1}'.format(domain, url))
        return True
    if tld in tld_blacklist:
        logger.info('Skipping blacklisted TLD "{0}": {1}'.format(tld, url))
        return True
    if intern(url) in link_filter:
        logger.info('Skipping spammy link match "{0}": {1}'.format(link_filter[url], url))
        return True
    if intern(text) in text_filter:
        logger.info('Skipping spammy text match "{0}": "{1}"'.format(text_filter[text], text))
        return True
    # no spam, result is good
    return False
