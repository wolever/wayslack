#!/usr/bin/env python

import os
import sys

from setuptools import setup

os.chdir(os.path.dirname(sys.argv[0]) or ".")

try:
    long_description = open("README.rst", "U").read()
except IOError:
    long_description = "See https://github.com/wolever/wayslack"

setup(
    name="wayslack",
    version="0.1.1",
    url="https://github.com/wolever/wayslack",
    author="David Wolever",
    author_email="david@wolever.net",
    description="The Wayslack Machine: incrementally archive Slack messages and files using Slack's team export format",
    long_description=long_description,
    py_modules=["wayslack"],
    entry_points={
        'console_scripts': [
            'wayslack = wayslack:main',
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
