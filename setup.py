#!/usr/bin/env python

import os
import sys

from setuptools import setup

os.chdir(os.path.dirname(sys.argv[0]) or ".")

try:
    long_description = open("README.rst", "U").read()
except IOError:
    long_description = "See https://github.com/wolever/slack-archiver"

setup(
    name="slack-archiver",
    version="0.1.0",
    url="https://github.com/wolever/slack-archiver",
    author="David Wolever",
    author_email="david@wolever.net",
    description="Incrementall download messages, files, and links from Slack teams, using the same format as Slack's team export.",
    long_description=long_description,
    py_modules=["slack_archiver"],
    entry_points={
        'console_scripts': [
            'slack-archiver = slack_archiver:main',
        ],
    },
    install_requires=[],
    license="BSD",
    classifiers=[ x.strip() for x in """
        Development Status :: 3 - Alpha
        Environment :: Console
        License :: OSI Approved :: BSD License
        Natural Language :: English
        Operating System :: OS Independent
        Programming Language :: Python :: 2
        Topic :: Utilities
    """.split("\n") if x.strip() ],
)
