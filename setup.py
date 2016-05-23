#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import sys
from os.path import dirname, join, abspath, split, splitext
from setuptools import find_packages, setup
from importlib import import_module

def _import_file(filepath):
    abspath_ = abspath(filepath)
    dirname, file = split(abspath_)
    fname, fext = splitext(file)
    if fext != '.py':
        raise ValueError("Not a Python source file: %s" % abspath_)
    if dirname:
        sys.path = [dirname] + sys.path
    try:
        module = import_module(fname)
    finally:
        if dirname:
            sys.path.pop(0)
    return module

def main(argv):

    description = 'Reddit Infobot'

    long_description = description
    try:
        with open('README.md', 'r') as f:
            long_description = f.read().strip()
    except (IOError, OSError): pass

    filename = join(dirname(__file__), 'reddit_info_bot/version.py')
    version = _import_file(filename).__version__

    requirements = []
    try:
        with open(join(dirname(__file__), 'requirements.txt'), 'r') as f:
            for line in f:
                requirements += [line.strip()]
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
                'reddit-infobot = reddit_info_bot.cli:execute'
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
        'dependency_links': [
            # imgurpython unreleased 1.1.8
            'https://github.com/Imgur/imgurpython/zipball/1.1.8',
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
