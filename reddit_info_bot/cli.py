from __future__ import (absolute_import, unicode_literals, print_function)
import sys
from docopt import docopt

from .settings import Settings
from .util import string_translate
from .version import __version__


def _parse_docopt_args(args):
    """Format docopt arguments to options.
    Strips leading slashes, turns other slashes into underscores.
    """
    for arg, argv in args.items():
        akey = arg.lstrip('-')
        akey = string_translate(akey, '-', '_')
        args[akey] = args.pop(arg)
    return args

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

def execute(argv=None, settings=None):
    if argv is None:
        argv = sys.argv
    if settings is None:
        settings = Settings()

    _usage = usage(__version__)
    args = docopt(_usage,
                  argv=argv[1:],
                  help=True,
                  version=__version__,
                  options_first=False)
    options = _parse_docopt_args(args)


if __name__ == '__main__':
    execute()
