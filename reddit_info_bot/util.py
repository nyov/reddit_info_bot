# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import sys, os
import logging
import codecs
import unicodedata
import six
import imp
import daemon  # python-daemon on pypi + debian
from lockfile.pidlockfile import PIDLockFile # lockfile on pypi, python-lockfile in debian
from importlib import import_module
from six.moves.urllib.parse import urlsplit, urlunsplit

from .publicsuffix import PublicSuffixList, fetch as download_psl

logger = logging.getLogger(__name__)


psl_cached = None

def cached_psl(fh):
    global psl_cached
    if not psl_cached:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        fh.seek(0)
        if size <= 0:
            logger.debug('No cached PublicSuffixList data, downloading')
            with download_psl() as inf:
                psl_cached = inf.read().encode('utf-8')
                fh.write(psl_cached)
        else:
            psl_cached = PublicSuffixList(fh)
        logger.debug('PublicSuffixList loaded')
    return psl_cached

def tld_from_suffix(suffix):
    return '.'.join(suffix.split('.')[1:])

def domain_suffix(url):
    """ Return the authoritative part of a domain

    (usually the second-level domain), by using public-suffix list data.
    For convenience, also return the full domain that was recognized.
    """
    domain = urlsplit(url).netloc
    if psl_cached:
        # return public suffix
        ps = psl_cached.get_public_suffix(domain)
        return (ps, domain)
    # fallback to recognize second-level domain as authority
    return ('.'.join(domain.split('.')[-2:]), domain)


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

def uri_is_file(uri):
    source = urlsplit(uri)
    if not source.netloc and (not source.scheme or source.scheme == 'file'):
        abspath = os.path.abspath(source.path)
        return True, abspath
    else:
        if not source.scheme:
            source.scheme = 'http'
        url = urlunsplit(source)
        return False, url

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

def setprocname(name):
    """Set the process name if possible.

    Requires setproctitle (python-setproctitle)
    from https://github.com/dvarrazzo/py-setproctitle
    (preferred) or python-prctl (debian package)
    from https://github.com/seveas/python-prctl .
    """
    try:
        import setproctitle
        setproctitle.setproctitle(name)
    except ImportError:
        try:
            import prctl
            # for ps and top, up to 16 bytes long
            prctl.set_name(name)
            # for ps aux and top -c
            # will silently truncate to **argv (see docs)
            prctl.set_proctitle(name)
        except ImportError:
            return

def daemon_context(settings, **kwargs):
    pidfile = settings.get('PID_FILE', None)
    if pidfile:
        pidfile = PIDLockFile(pidfile)
    doublefork = settings.getbool('DETACH_PROCESS', False)
    if doublefork:
        stdin = stdout = stderr = None
    else:
        stdin, stdout, stderr = sys.stdin, sys.stdout, sys.stderr

    context = daemon.DaemonContext(
        chroot_directory = settings.get('BOT_CHROOTDIR', None),
        working_directory = settings.get('BOT_WORKDIR', '/'),
        umask = settings.get('BOT_UMASK', 0),
        prevent_core = settings.getbool('COREDUMPS_DISABLED', False),
        detach_process = doublefork,
        pidfile = pidfile,
        stdin  = stdin,
        stdout = stdout,
        stderr = stderr,
        **kwargs
    )
    return context

def http_code_ranges():
    codes = {
        '100': set(range(100, 200)), # 100 Informational
        '200': set(range(200, 300)), # 200 Success
        '300': set(range(300, 400)), # 300 Redirect
        '400': set(range(400, 500)), # 400 Client Error
        '500': set(range(500, 600)), # 500 Server Error
        'EXT': set(range(600,1000)), # 999 Other
        'ALL': set(range(100,1000)), # Everything valid
    }
    # exclusions
    codes.update({
        'X100': codes['ALL'] - codes['100'],
        'X200': codes['ALL'] - codes['200'],
        'X300': codes['ALL'] - codes['300'],
        'X400': codes['ALL'] - codes['400'],
        'X500': codes['ALL'] - codes['500'],
        'XEXT': codes['ALL'] - codes['EXT'],
    })
    return codes
