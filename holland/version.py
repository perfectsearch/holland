"""
holland.version
~~~~~~~~~~~~~~~

Holland version information

This module includes two variables:

__version__ - a string version of the current holland release
__version_info__ - __version__ as a tuple

This is used by setup.py to set the version as well as internally
by various holland utilities that report the holland version.
"""

__version__ = '2.0.2'
__version_info__ = tuple([int(part) for part in __version__.split('.')])
