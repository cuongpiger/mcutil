#!/usr/bin/env python
# -*- coding: utf-8 -*-
import re
import os

from setuptools import setup

version = "1.0.0"
with open('mcutil/__init__.py', 'r') as f:
    for line in f:
        m = re.match(r'^__version__\s*=\s*(["\'])([^"\']+)\1', line)
        if m:
            version = m.group(2)
            break

assert version is not None, \
    'Could not determine version number from jaeger_client/__init__.py'


def __read__(file_name):
    return open(os.path.join(os.path.dirname(__file__), file_name)).read()


setup(
    name='mcutil',
    version=version,
    url='https://github.com/cuongpiger/mcutil',
    description='Some simple utilities for Python',
    long_description=__read__('README.md'),
    author='Cuong. Duong Manh',
    author_email='cuongdm8499@gmail.com',
    include_package_data=True,
    license='Apache License 2.0',
    zip_safe=False,
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ],
    python_requires='>=3.6',
    install_requires=[],
)
