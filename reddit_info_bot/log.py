from __future__ import absolute_import, unicode_literals
import sys
import logging
from logging.config import dictConfig

from .settings import Settings


def setup_logging(settings=None, install_root_handler=True):
    log_config = {
        'version': 1,
        'disable_existing_loggers': False,
        'loggers': {
            'reddit_info_bot': {
                'level': 'DEBUG',
            },
        },
    }

    if not sys.warnoptions:
        logging.captureWarnings(True)
    if isinstance(settings, dict) or settings is None:
        settings = Settings(settings)

    log_config.update(settings.getdict('LOG_CONFIG'))
    dictConfig(log_config)

    if install_root_handler:
        logging.root.setLevel(logging.NOTSET)

        if settings.getbool('LOG_ENABLED', True):
            filename = settings.get('LOG_FILE')
            if filename:
                encoding = settings.get('LOG_FILE_ENCODING', 'utf-8')
                handler = logging.FileHandler(filename, encoding=encoding)
            else:
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
        handler.setLevel(settings.get('LOG_LEVEL'))

        logging.root.addHandler(handler)

        return handler

def release_logging(handler):
    handler.close()
    logging.root.removeHandler(handler)
