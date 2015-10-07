# -*- coding: utf-8 -*-
from __future__ import (absolute_import, unicode_literals, print_function)

import codecs
import unicodedata
from six.moves.urllib.parse import urlsplit
from six.moves.urllib.request import urlopen, Request
from publicsuffix import PublicSuffixList


PUBLIC_SUFFIX_LIST_URL = 'https://publicsuffix.org/list/public_suffix_list.dat'
PSL_CACHE_FILE = 'public_suffix_list.dat'

def download_psl(url=PUBLIC_SUFFIX_LIST_URL):
	"""Downloads the latest public suffix list from publicsuffix.org.

	Returns a file object containing the public suffix list.
	"""
	res = urlopen(Request(url))
	try:
		encoding = res.headers.get_content_charset()
	except AttributeError:
		encoding = res.headers.getparam('charset')
	f = codecs.getreader(encoding)(res)
	return f

def cache_psl(from_file='public_suffix_list.dat'):
    try:
        with open(from_file, 'rb') as f:
            psl = PublicSuffixList(f)
    except (IOError, OSError):
        with download_psl() as inf, open(from_file, 'wb') as outf:
            outf.write(inf.read().encode('utf-8'))
        with open(from_file, 'rb') as f:
            psl = PublicSuffixList(f)
    return psl

psl = cache_psl(PSL_CACHE_FILE)

def tld_from_suffix(suffix):
    return '.'.join(suffix.split('.')[1:])

def domain_suffix(link):
    parse = urlsplit(link)
    return psl.get_public_suffix(parse.netloc)


def remove_control_characters(string):
    return ''.join(c for c in string if unicodedata.category(c)[0] != 'C')
