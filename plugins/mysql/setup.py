from setuptools import setup, find_packages
import sys, os

version = '2.0.0'

setup(name='holland.mysql',
      version=version,
      description="",
      long_description="""\
""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='',
      author='Andrew Garner',
      author_email='holland-coredev@lists.launchpad.net',
      url='http://hollandbackup.org',
      license='GPLv2',
      packages=find_packages(exclude=['tests', 'tests.*']),
      include_package_data=True,
      zip_safe=False,
      test_suite='tests',
      install_requires=[
          # -*- Extra requirements: -*-
      ],
      entry_points="""
      [holland.backup]
      mysqldump = holland.mysql.mysqldump:MySQLDumpBackupPlugin
      xtrabackup = holland.mysql.xtrabackup:XtrabackupPlugin
      #delphini  = holland.mysql.delphini:DelphiniPlugin
      """,
)
