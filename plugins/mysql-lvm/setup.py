from setuptools import setup, find_packages
import sys, os

version = '2.0.0'

setup(name='holland.mysql.lvm',
      version=version,
      description="MySQL LVM snapshot support for holland",
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
      install_requires=[
          # -*- Extra requirements: -*-
      ],
      entry_points="""
      [holland.backup]
      mysql-lvm     = holland.mysql.lvm:MysqlLVMBackup
      mysqldump-lvm = holland.mysql.lvm.plugin.mysqldump:MysqlDumpLVMBackup
      mylvmdump     = holland.mysql.lvm.plugin.mysqldump:MysqlDumpLVMBackup
      """,
)
