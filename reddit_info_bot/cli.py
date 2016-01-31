from __future__ import absolute_import, unicode_literals
import sys, os
import six
import logging
import atexit
from functools import partial
from docopt import docopt

from .settings import Settings
from .commands import bot_commands
from .util import string_translate, import_string_from_file, import_file, setprocname
from .version import __version__

logger = logging.getLogger(__name__)


def _parse_docopt_args(args):
    """Format docopt arguments to options.

    Strips leading slashes, turns other slashes into underscores,
    uppercases all text.
    """
    for arg, argv in args.items():
        akey = arg.lstrip('-')
        akey = string_translate(akey, '-', '_')
        akey = akey.upper()
        args[akey] = args.pop(arg)
    return args

def _get_option_value(argv, args, pop=False):
    """Return an option's value from argv.
    With `pop`=`True`, pop it from the passed argv.
    """
    i = 0
    optvalue = None
    for arg in argv:
        # sort by length, longest first
        args = list(args)
        args.sort(key=len, reverse=True)
        if arg.startswith(tuple(args)):
            for key in args:
                arg = arg.replace(key, '')
            arg = arg.lstrip('=')
            # was passed as '--option=file'
            if len(arg) > 0:
                optvalue=arg
                if pop:
                    del argv[i]
                break
            # missing value
            if len(argv) < i+2:
                return None
            # was passed as '-o file'
            optvalue = argv[i+1]
            if pop:
                del argv[i], argv[i+1]
            break
        i += 1
    del i
    return optvalue

def _load_config(file):
    def import_config():
        if not isinstance(file, six.string_types):
            return
        #module = import_file(file)
        module = import_string_from_file(file)
        for name in dir(module):
            if name.isupper():
                yield name, getattr(module, name)
        del module

    try:
        cfg = list(import_config())
    except SyntaxError as e:
        import traceback
        msg = 'Error parsing configuration file:\n\n'
        t, e, tb = sys.exc_info()
        args = []
        for i, arg in enumerate(e.args):
            if isinstance(arg, tuple):
                (_, line, pos, string) = arg
                args += [(file, line, pos, string)]
                continue
            args += [arg]
        e.args = tuple(args)
        msg += ''.join(traceback.format_exception(t, e, None, 0))
        sys.exit(msg)

    return cfg

def usage(instance):
    """Format program description output"""
    import textwrap

    doc = """
    {botname}

    Usage: reddit_info_bot [-c CONFIGFILE] [-l LOGFILE] [-v|-vv|-vvv]

      -c FILE --config=FILE    Load configuration from custom file
                               instead of default locations.
                               (To run multiple instances in parallel)
      -l FILE --log-file=FILE  Log to file instead of stdout.
      -v --verbose             Increase log-level verbosity.
                               (-vv for info, -vvv for debug level)
      -h --help                Show this screen.
                               (Use with -c to show CONFIG's instance)
      --version                Show version.
    """.format(botname=instance)
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

def execute(argv=None, settings=None):
    if argv is None:
        argv = sys.argv
    if isinstance(settings, dict):
        settings = Settings(settings)
    if settings is None:
        # load default settings
        settings = Settings()

        # pre-parse config option for docopt output
        config = _get_option_value(argv, ('-c', '--config'))
        if config:
            # import settings from passed configfile
            cfg = _load_config(config)
            if cfg:
                for option, value in cfg:
                    settings.set(option, value)

    bot_name = settings.get('BOT_NAME', '')
    if bot_name:
        procname = bot_name
        if bot_name == 'reddit_info_bot':
            bot_name = ''
        else:
            procname = 'reddit_info_bot (%s)' % bot_name
        setprocname(procname)
    bot_version = settings.get('BOT_VERSION', '')
    if bot_version == __version__:
        bot_version = ''
    bot_instance = '%s %s' % (bot_name, bot_version)
    bot_instance = bot_instance.strip()
    if bot_instance:
        bot_instance = ' (%s)' % bot_instance
    settings.set('_BOT_INSTANCE_', 'reddit_info_bot %s%s' %
                 (__version__, bot_instance)) # (runtime setting)

    _usage = usage(settings.get('_BOT_INSTANCE_'))
    args = docopt(_usage,
                  argv=argv[1:],
                  help=True,
                  version=__version__,
                  options_first=False)
    options = _parse_docopt_args(args)

    config = options.pop('CONFIG')
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

        cfg = _load_config(config)
        if not cfg:
            errmsg = 'Configuration file invalid, no settings found!'
            sys.exit(errmsg)
        for option, value in cfg:
            settings.set(option, value)

    log_file = options.pop('LOG_FILE')
    if log_file:
        settings.set('LOG_FILE', log_file)
    loglevel = {0:'ERROR',1:'WARNING',2:'INFO',3:'DEBUG'}
    loglevel = loglevel[options.pop('VERBOSE')]
    if loglevel != 'ERROR':
        settings.set('LOG_LEVEL', loglevel)
    for option, value in options:
        settings.set(option, value)

    # supported commands
    cmds = bot_commands()

    # command to execute
    cmdname = None
    for opt, arg in options.items(): # argv
        if arg is True and opt in cmds.keys():
            cmdname = opt

    if not cmdname:
        cmdname = 'run' # default action
    cmd = cmds[cmdname]

    # arguments to pass to command
    cmdargs = {
        'settings':settings,
    }

    if 'shutdown' in cmds:
        shutdown = cmds['shutdown']
        shutdown_func = partial(shutdown, settings)
        atexit.register(shutdown_func)

    exitcode = cmd(**cmdargs)
    if not exitcode:
        exitcode = 0
    sys.exit(exitcode)

if __name__ == '__main__':
    execute()
