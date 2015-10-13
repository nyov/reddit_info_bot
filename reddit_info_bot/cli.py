from __future__ import (absolute_import, unicode_literals, print_function)
import sys, os
import six
from docopt import docopt

from .settings import Settings
from .util import string_translate, import_string_from_file, import_file
from .version import __version__
from . import run


def _parse_docopt_args(args):
    """Format docopt arguments to options.
    Strips leading slashes, turns other slashes into underscores.
    """
    for arg, argv in args.items():
        akey = arg.lstrip('-')
        akey = string_translate(akey, '-', '_')
        args[akey] = args.pop(arg)
    return args

def _load_config(file):
    if not isinstance(file, six.string_types):
        return
    #module = import_file(file)
    module = import_string_from_file(file)
    for name in dir(module):
        if name.isupper():
            yield name, getattr(module, name)
    del module

def _get_commands():
    cmds = {
        'run': run_command,
    }
    return cmds

def usage(version):
    """Format program description output"""
    import textwrap

    version = ' %s' % version

    doc = """
    reddit_info_bot{version}

    Usage: reddit_info_bot [-c CONFIGFILE]

      -c FILE --config=FILE   Load configuration from custom file
                              instead of default locations.
                              (To run multiple instances in parallel)
      -h --help               Show this screen.
      --version               Show version.
    """.format(version=version)
    return textwrap.dedent(doc)

def get_config_sources(name, ext='cfg', dir=None):
    """Return default configuration locations.

    When `dir` is given, look for `name` inside `dir`.
    """
    xdg_config_home = os.environ.get('XDG_CONFIG_HOME') or \
            os.path.expanduser('~/.config')
    _ext = ''
    if ext:
        _ext = '.%s' % (ext,)
    _dir = _dirname = name
    if dir:
        _dir = '%s' % dir
        _dirname = '%s/%s' % (dir, name)

    sources = [
        '/etc/%s%s' % (_dirname, _ext),
        r'c:\%s\%s%s' % (_dir, name, _ext),
        os.path.expanduser('~/.%s%s' % (_dirname, _ext)),
        '%s/%s%s' % (xdg_config_home, _dirname, _ext),
        '%s%s' % (name, _ext),
    ]
    return sources

def run_command(**kwargs):
    return run(**kwargs)

def execute(argv=None, settings=None):
    if argv is None:
        argv = sys.argv
    if settings is None:
        # load default settings
        settings = Settings()
    if isinstance(settings, dict):
        settings = Settings(settings)

    _usage = usage(__version__)
    args = docopt(_usage,
                  argv=argv[1:],
                  help=True,
                  version=__version__,
                  options_first=False)
    options = _parse_docopt_args(args)

    config = options.pop('config')
    if not config:
        # check hardcoded name and place of default configuration
        sources = get_config_sources('config', 'py', dir='reddit-infobot')
        sources.reverse()
        for source in sources:
            if os.path.isfile(source):
                config = source
                break
        if not config:
            errmsg = (
                'No configuration file found!\n'
                '(valid locations, in order of importance:\n - %s )'
                % '\n - '.join(sources)
            )
            sys.exit(errmsg)

    try:
        cfg = _load_config(config)
        cfg = list(cfg)
    except SyntaxError as e:
        import traceback
        print('Error parsing configuration file:')
        t, e, tb = sys.exc_info()
        args = []
        for i, arg in enumerate(e.args):
            if isinstance(arg, tuple):
                (file, line, pos, string) = arg
                args += [(config, line, pos, string)]
                continue
            args += [arg]
        e.args = tuple(args)
        traceback.print_exception(t, e, None, 0)
        sys.exit(1)

    if not cfg:
        errmsg = 'Configuration file invalid, no settings found!'
        sys.exit(errmsg)
    for option, value in cfg:
        settings.set(option, value)

    instance = settings.get('BOT_NAME', None)
    if instance:
        print('reddit_info_bot configured as: %s' % instance)

    # supported commands
    cmds = _get_commands()

    # command to execute
    cmdname = None
    for opt, arg in options.items(): # argv
        if arg is True and opt in cmds.keys():
            cmdname = opt

    if not cmdname:
        # default action
        cmdname = 'run'
    cmd = cmds[cmdname]

    cmdargs = {
        'instance':instance,
        'settings':settings,
    }

    exitcode = cmd(**cmdargs)
    if not exitcode:
        exitcode = 0
    sys.exit(exitcode)

if __name__ == '__main__':
    execute()
