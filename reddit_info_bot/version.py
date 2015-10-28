__version__ = '2015.10.1'

def git_version(default_version=None, path=None, local=False):
    import os, subprocess
    try:
        DEVNULL = subprocess.DEVNULL  # py3
    except AttributeError:
        DEVNULL = open(os.devnull, 'wb')

    version = None
    try:
        if path:
            wd = os.getcwd()
            os.chdir(path)
        version = subprocess.check_output(
                ['git', 'describe', '--tags', '--first-parent'],
                stderr=DEVNULL).strip()
        if path:
            os.chdir(wd)
        version = version.decode('utf-8')
        version = version.split('-')
        ''' not pep 440 compliant
        if len(version) == 3:
            del version[1] # drop commit numbers since last tag
            version[1] = version[1][1:] # drop 'g'
        version = '.'.join(version)
        '''
        if len(version) == 3:
            version[1] = '.dev%s' % version[1]
            version[2] = '+%s' % version[2][1:]
            if not local:
                del version[2] # drop hash
        version = ''.join(version)
    except (OSError, subprocess.CalledProcessError): pass

    return version or default_version

# Amend version if inside a local git clone.
# This is certainly not a perfect idea, but should be ok in our case.
# (doing this only at compile time, save the subprocess call, could be nice)
from os.path import abspath, dirname, join, exists
path = abspath(join(dirname(__file__), '../.git'))
if exists(path):
    __version__ = git_version(__version__, path)

version_info = tuple(int(v) if v.isdigit() else v
                     for v in __version__.split('.'))
