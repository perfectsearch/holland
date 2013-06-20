from nose.tools import *
from holland.lvm.errors import *

def test_errors():
    exc = LVMCommandError('cmd', -1, 'error message')
    assert_equal(exc.cmd, 'cmd')
    assert_equal(exc.status, -1)
    assert_equal(exc.error, 'error message')
