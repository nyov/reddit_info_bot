# -*- coding: utf-8 -*-
from __future__ import (absolute_import, unicode_literals, print_function)
import sys
import os
import logging
import time
import pickle
import re
import json
from six.moves.urllib.request import urlopen
from six.moves.urllib.error import HTTPError
from .util import domain_suffix, tld_from_suffix

logger = logging.getLogger(__name__)


def sync_rarchives_spamdb(filter_type, full_data=False):
    """Pull data from the spambot.rarchives.com database

    in a (hopefully) least-bothersome way (since it's just
    a small, and apparently memory-limited, sqlite app).
    """
    # This means we pull smallish chunks, iteratively, so the
    # remote db doesn't need to pull a big dataset into memory
    # and lock up or die.

    def fetch_data(url):
        try:
            # debug
            #print('s>', url)
            response = urlopen(url).read()
            data = json.loads(response)
            if 'error' in data:
                return (False, data['error'])
            return (True, data)
        except (HTTPError, ValueError) as e:
            return (False, str(e))

    if full_data: # no deltas, fetch everything
        url = 'http://spambot.rarchives.com/api.cgi?method=get_filters&start={start}&count={count}&type={type}'
        count = 500 # number of db-results per request, pick a balanced value
                    # (not too many request, not too much data per request)
        start = failcount = 0
        total = count
        filters = []
        while True:
            ok, data = fetch_data(url.format(start=start, count=count, type=filter_type))
            if not ok: # or ('filters' not in data):
                # debug
                #print('error:', data)
                failcount += 1
                if failcount > 3:
                    break
                if 'database is locked' in data:
                    # back off and hope the remote will recover
                    time.sleep(failcount*3)
                # try again
                print('retrying')
                continue
            if 'filters' not in data or 'total' not in data:
                # unknown content
                break

            filters += list(data['filters'])

            start += count
            #start = data['start']
            total = data['total']
            if start > total: # all done
                filters = json.dumps({
                    'total': total,
                    'type': filter_type,
                    'filters': filters,
                })
                return filters
                break
            failcount = 0

        if not filters:
            return None
        #return filters # partial content is okay?
        return None

    else: # compile deltas to patch our local dataset
        # TODO
        return None

def get_filter(filter_type):
    def cache_filters(filter_type):
        response = sync_rarchives_spamdb(filter_type, full_data=True)
        if not response:
            msg = 'Spamfilter update failed, using cached files (if available)'
            print(msg)
        else:
            with open(filename, 'wb') as outf:
                outf.write(response)

    filename = 'spamfilter_{0}.json'.format(filter_type)
    if not os.path.isfile(filename) or \
            (int(time.time() - os.path.getmtime(filename)) > 43200): # cache 24 hours
        print('Downloading spambot.rarchives.com list: %s filters' % filter_type)
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

    return [i['spamtext'] for i in filters]


def spamfilter_lists():
    blacklist = []
    if os.path.isfile("blacklist.p"):
        with open("blacklist.p", "rb") as f:
            blacklist = pickle.load(f)
    # s.r.c filters
    link_filter = get_filter('link')
    thumb_filter = get_filter('thumb')
    text_filter = get_filter('text')
    user_filter = get_filter('user')
    tld_filter = get_filter('tld')
    #
    link_filter = link_filter + thumb_filter
    text_filter = text_filter + user_filter
    tld_blacklist = [''.join(letter for letter in tld if letter!=".") for tld in tld_filter]

    hard_blacklist = []
    whitelist = ['reddit.com']

    return (
        link_filter,
        text_filter,
        hard_blacklist,
        whitelist,
        tld_blacklist,
        blacklist,
    )


def isspam(result, lists):
    """check search result for spammy content
    """
    (link_filter, text_filter, hard_blacklist,
     whitelist, tld_blacklist, blacklist) = lists

    url, text = result[0].lower(), result[1].lower()

    if len(url) < 6: # shorter than '//a.bc' can't be a useable absolute HTTP URL
        print('Skipping invalid URL: "{0}"'.format(url))
        return True
    # domain from URL using publicsuffix (not a validator)
    domain = domain_suffix(url)
    if not domain:
        print('Failed to lookup PSL/Domain for: "{0}"'.format(url))
        return True
    tld = tld_from_suffix(domain)
    if not tld or tld == '':
        print('Failed to lookup TLD from publicsuffix for: "{0}"'.format(url))
        return True
    if domain in whitelist:
        # higher prio than the blacklist
        return False
    if domain in hard_blacklist:
        print('Skipping blacklisted Domain "{0}": {1}'.format(domain, url))
        return True
    if tld in tld_blacklist:
        print('Skipping blacklisted TLD "{0}": {1}'.format(tld, url))
        return True
    if url in link_filter:
        print('Skipping spammy link match "{0}": {1}'.format(link_filter[url], url))
        return True
    if text in text_filter:
        print('Skipping spammy text match "{0}": "{1}"'.format(text_filter[text], text))
        return True
    # no spam, result is good
    return False
