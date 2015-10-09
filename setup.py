#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import (absolute_import, unicode_literals, print_function)
import sys
from os.path import dirname, join
from setuptools import find_packages, setup



def main(argv):

    description = 'Reddit Infobot'

    long_description = description
    try:
        with open('README.md', 'r') as f:
            long_description = f.read().decode('utf-8').strip()
    except (IOError, OSError): pass

    version = '0.0'
    try:
        with open(join(dirname(__file__), 'reddit_info_bot/VERSION'), 'rb') as f:
            version = f.read().decode('ascii').strip()
    except (IOError, OSError): pass

    requirements = []
    try:
        with open(join(dirname(__file__), 'requirements.txt'), 'rb') as f:
            for line in f:
                requirements += [line.decode('ascii').strip()]
    except (IOError, OSError): pass


    setup_args = {
        'name': 'python-reddit-infobot',
        'version': version,
        'url': 'https://github.com/tek0011/reddit_info_bot',
        'description': description,
        'long_description': long_description,
        'keywords': 'python reddit infobot',
        'author': 'python-reddit-infobot developers',
        'maintainer': 'python-reddit-infobot developers',
        'packages': find_packages(),
        'include_package_data': True,
        'zip_safe': False,  # for setuptools
        'entry_points': {
            'console_scripts': [
                'reddit_info_bot = reddit_info_bot.cli:execute'
            ],
        },
        'classifiers': [
            'Development Status :: 3 - Alpha',
            'Operating System :: Linux',
            'Programming Language :: Python',
            'Programming Language :: Python :: 2',
            'Programming Language :: Python :: 2.7',
        ],
        'install_requires': [
            # included from requirements.txt
        ],
    }

    if requirements:
        setup_args['install_requires'] = requirements

    try:
        from local_setup import local_setup_args
        setup_args.update(local_setup_args)
    except ImportError: pass

    setup(**setup_args)


if __name__ == "__main__":
    sys.exit(main(sys.argv))