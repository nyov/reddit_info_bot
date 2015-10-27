from __future__ import absolute_import, unicode_literals
import sys
import logging

from .settings import Settings


class StreamLogger(object):
    """Fake file-like stream object that redirects writes to a logger instance

    Taken from scrapy, in turn taken from:
        http://www.electricmonk.nl/log/2011/08/14/redirect-stdout-and-stderr-to-a-logger-in-python/
    """
    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ''

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.log_level, line.rstrip())


def setup_logging(settings=None, install_root_handler=True):
    if not sys.warnoptions:
        logging.captureWarnings(True)
    if isinstance(settings, dict) or settings is None:
        settings = Settings(settings)
    if settings.getbool('LOG_CAPTURE_STDOUT', False):
        sys.stdout = StreamLogger(logging.getLogger('stdout'))
    if install_root_handler:
        logging.root.setLevel(logging.NOTSET)

        filename = settings.get('LOG_FILE')
        if filename and settings.getbool('LOG_ENABLED', False):
            encoding = settings.get('LOG_FILE_ENCODING', 'utf-8')
            handler = logging.FileHandler(filename, encoding=encoding)
        elif settings.getbool('LOG_ENABLED', True):
            handler = logging.StreamHandler()
        else:
            handler = logging.NullHandler()

        formatter = logging.Formatter(
            fmt=settings.get('LOG_FORMAT',
                '%(asctime)s [%(name)s] %(levelname)s: %(message)s'
            ),
            datefmt=settings.get('LOG_DATEFORMAT',
                '%Y-%m-%d %H:%M:%S'
            )
        )
        handler.setFormatter(formatter)
        handler.setLevel(settings.get('LOG_LEVEL', 'DEBUG'))

        logging.root.addHandler(handler)
