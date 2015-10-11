from __future__ import (absolute_import, unicode_literals, print_function)
import sys
from docopt import docopt

from .settings import Settings
from .util import string_translate
from .version import __version__
#from . import run


def _parse_docopt_args(args):
    """Format docopt arguments to options.
    Strips leading slashes, turns other slashes into underscores.
    """
    for arg, argv in args.items():
        akey = arg.lstrip('-')
        akey = string_translate(akey, '-', '_')
        args[akey] = args.pop(arg)
    return args

def _get_commands():
    cmds = {
        'run': run_command,
    }
    return cmds

def usage(version):
    import textwrap

    version = ' %s' % version

    doc = """
    reddit_info_bot{version}

    Usage: reddit_info_bot [-h]

      -h --help               Show this screen.
      --version               Show version.
    """.format(version=version)
    return textwrap.dedent(doc)

def run_command(**kwargs):
    # placeholder
    #return run()
    return

def execute(argv=None, settings=None):
    if argv is None:
        argv = sys.argv
    if settings is None:
        # load default settings
        settings = Settings()
    if isinstance(settings, dict):
        settings = Settings(settings)

    instance = settings.get('BOT_NAME', None)

    _usage = usage(__version__)
    args = docopt(_usage,
                  argv=argv[1:],
                  help=True,
                  version=__version__,
                  options_first=False)
    options = _parse_docopt_args(args)

    # config options, put into settings
    for option, optval in options.items():
        option = 'BOT_%s' % option.upper()
        settings.set(option, optval)

    # write after loading configuration file:
    if instance:
        print('reddit_info_bot launched as: %s' % instance)

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
    }

    exitcode = cmd(**cmdargs)
    if not exitcode:
        exitcode = 0
    #sys.exit(exitcode)

if __name__ == '__main__':
    execute()
