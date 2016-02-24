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
from six.moves.urllib.parse import urlsplit

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

def domain_suffix(link):
    parse = urlsplit(link)
    return psl_cached.get_public_suffix(parse.netloc)


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
