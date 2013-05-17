"""
holland.core.exc
~~~~~~~~~~~~~~~~

Core holland exceptions

:copyright: 2008-2011 Rackspace US, Inc.
:license: BSD, see LICENSE.rst for details
"""

class HollandError(Exception):
    def __init__(self, message, orig_exc=None):
        self.message = message
        self.orig_exc = orig_exc

    def __str__(self):
        return self.message
