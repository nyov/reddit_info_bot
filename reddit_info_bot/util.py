# -*- coding: utf-8 -*-
from __future__ import (absolute_import, unicode_literals, print_function)
import os
import codecs
import unicodedata
import six
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

def string_translate(text, intab, outtab):
    """Helper function for string translation

    Replaces characters in `intab` with replacements from `outtab`
    inside `text`.
    """
    if six.PY2:
        from string import maketrans
        transtab = maketrans(intab, outtab)
        text = bytes(text)
    else:
        transtab = text.maketrans(intab, outtab)
    return text.translate(transtab)


def chwd(dir):
    """Change working directory."""
    if not os.path.exists(dir):
        errmsg = "Requested workdir '{0}' does not exist, aborting.".format(dir)
        return False, errmsg
    os.chdir(dir)
    if os.getcwd() != dir:
        errmsg = "Changing to workdir '{0}' failed!".format(dir)
        return False, errmsg
    return True, 'success'


# mock objects to emulate praw interface
class submission:
    def __init__(self,link):
        self.url = link

class comment:
    def __init__(self,link):
        self.submission = submission(link)
        self.id = "dummy comment"
    def reply(self,text):
        print(text)
