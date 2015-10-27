# -*- coding: utf-8 -*-
from __future__ import (absolute_import, unicode_literals, print_function)
import sys, os
import codecs
import unicodedata
import six
import imp
from importlib import import_module
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

psl_cached = None

def cached_psl(from_file='public_suffix_list.dat'):
    global psl_cached
    if not psl_cached:
        try:
            with open(from_file, 'rb') as f:
                psl_cached = PublicSuffixList(f)
        except (IOError, OSError):
            with download_psl() as inf, open(from_file, 'wb') as outf:
                outf.write(inf.read().encode('utf-8'))
            with open(from_file, 'rb') as f:
                psl_cached = PublicSuffixList(f)
    return psl_cached

def tld_from_suffix(suffix):
    return '.'.join(suffix.split('.')[1:])

def domain_suffix(link):
    parse = urlsplit(link)
    psl = cached_psl(PSL_CACHE_FILE)
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
        return (False, errmsg)
    os.chdir(dir)
    if os.getcwd() != dir:
        errmsg = "Changing to workdir '{0}' failed!".format(dir)
        return (False, errmsg)
    return (True, 'success')

def import_file(filepath):
    abspath = os.path.abspath(filepath)
    dirname, file = os.path.split(abspath)
    fname, fext = os.path.splitext(file)
    if fext != '.py':
        raise ValueError("Not a Python source file: %s" % abspath)
    if dirname:
        sys.path = [dirname] + sys.path
    try:
        module = import_module(fname)
    finally:
        if dirname:
            sys.path.pop(0)
    return module

def import_string_from_file(filepath, module_name='configfile'):
    """Import anything as a python source file.

    (And do not generate cache files where none belong.)
    """
    abspath = os.path.abspath(filepath)
    try:
        with open(abspath, 'r') as cf:
            code = cf.read()
    except (IOError, OSError) as e:
        sys.exit(e)
    module = imp.new_module(module_name)
    six.exec_(code, module.__dict__)
    return module


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
