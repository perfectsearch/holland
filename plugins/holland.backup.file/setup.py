#!/usr/bin/env python2
# -*- coding: utf-8 -*-
import os
import sys
from setuptools import setup, find_packages

version = '1.0.11'

setup(name="holland.backup.file",
      version=version,
      description="File/LVM Snapshot Plugin",
      long_description="""\
      This script provides support for performing safe LVM snapshot backups
      for files and directories.
      """,
      classifiers=[],  # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='',
      author='PerfectSearch',
      author_email='packager@perfectsearchcorp.com',
      url='http://perfectsearchcorp.com/',
      # license='GPLv2',
      packages=find_packages(exclude=["ez_setup", "examples", "tests", "tests.*"]),
      include_package_data=True,
      zip_safe=True,
      install_requires=['holland.lib.lvm', 'holland.backup.mysql_lvm'],
      tests_require=['nose', 'mocker', 'coverage'],
      test_suite='nose.collector',
      entry_points="""
      [holland.backup]
      file = holland.backup.file:FileBackup
      """,
      namespace_packages=['holland', 'holland.backup'],
      )
