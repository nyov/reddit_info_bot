# -*- coding: utf-8 -*-
from __future__ import (absolute_import, unicode_literals, print_function)
import sys
import os
import logging
import time
import pickle
import urllib2
import re
import json
from .util import domain_suffix, tld_from_suffix

logger = logging.getLogger(__name__)


def get_filter(filter_type):
    def cache_filters(filter_type):
        try:
            response = urllib2.urlopen('http://spambot.rarchives.com/api.cgi?method=get_filters&start=0&count=3000&type={0}'.format(filter_type)).read()
            # test if the response is valid for us
            json.loads(response)['filters']
        except (urllib2.HTTPError, KeyError, Exception) as e:
            msg = 'Spamfilter update failed with error "{0}", using cached files (if available)'.format(str(e))
            print(msg)
        else:
            with open(filename, 'wb') as outf:
                outf.write(response)

    filename = 'spamfilter_{0}.json'.format(filter_type)
    if not os.path.isfile(filename) or \
            (int(time.time() - os.path.getmtime(filename)) > 43200): # cache 24 hours
        cache_filters(filter_type)
        if not os.path.isfile(filename):
            errmsg = "Could not load spam filters. Cached files invalid or Network failure."
            sys.exit(errmsg) # quick&ugly, sorry

    filters = None
    try:
        with open(filename, 'rb') as inf:
            filters = json.load(inf)['filters']
    except (ValueError, KeyError): # cached file contents invalid
        os.unlink(filename)
        # retry? potential loop
        #get_filter(filter_type)
        errmsg = "Could not load spam filters. Cached files invalid or Network failure."
        sys.exit(errmsg)

    return [i['spamtext'] for i in filters]


def spamfilter_lists():
    blacklist = []
    if os.path.isfile("blacklist.p"):
        with open("blacklist.p", "rb") as f:
            blacklist = pickle.load(f)
    print('Adding Rarchives links to blacklist.')
    link_filter = get_filter('link') + get_filter('thumb')
    text_filter = get_filter('text') + get_filter('user')
    """for domain in link_filter:
        if 'http' not in domain and domain[0] != '.':
            domain = "http://"+domain
        if not re.search('\.[^\.]+/.+$',domain): #if the link isn't to a specific page (has stuff after the final /) instead of an actual domain
            if domain[0] != '.':
                if domain not in blacklist:
                    blacklist.append(domain)
    """
    word_filter = get_filter('text')
    tld_blacklist = [''.join(letter for letter in tld if letter!=".") for tld in get_filter('tld')]

    hard_blacklist = []
    whitelist = ['reddit.com']

    return (
        link_filter,
        text_filter,
        word_filter,
        hard_blacklist,
        whitelist,
        tld_blacklist,
        blacklist,
    )


# load spam lists
(
    link_filter,
    text_filter,
    word_filter,
    hard_blacklist,
    whitelist,
    tld_blacklist,
    blacklist,
) = spamfilter_lists()


def isspam(result):
    """check search result for spammy content
    """
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