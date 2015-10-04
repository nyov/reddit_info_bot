# -*- coding: utf-8 -*-
from __future__ import (absolute_import, unicode_literals, print_function)

from six.moves.urllib.parse import urlsplit
from publicsuffix import PublicSuffixList, fetch

psl_dat = 'public_suffix_list.dat'

def download_psl(to_file='public_suffix_list.dat'):
    with fetch() as inf, open(to_file, 'wb') as outf:
        outf.write(inf.read().encode('utf-8'))

#download_psl(psl_dat)

def tld_from_suffix(suffix):
    return '.'.join(suffix.split('.')[1:])

#import codecs
#psl_file = codecs.open(psl_dat, encoding='utf8')
#psl = PublicSuffixList(psl_file)
with open(psl_dat, 'rb') as f:
    psl = PublicSuffixList(f)


def domain_suffix(link):
    parse = urlsplit(link)
    return psl.get_public_suffix(parse.netloc)
