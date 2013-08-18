"""
holland.core.config.validators
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Validators for Configspec checks

This module implementations individual validation for
various datatype and checks that can be defined in a
``holland.core.config.Configspec``

:copyright: 2010-2013 Rackspace US, Inc.
:license: BSD, see LICENSE.rst for details
"""

import csv
import logging
import shlex
import subprocess
from io import StringIO, BytesIO
from holland.core.plugin import BasePlugin, plugin_registry, load_plugin, PluginError
from holland.core.exc import HollandError
from .util import unquote

def load_validator(check):
    """Load a validator plugin"""
    try:
        validator = plugin_registry.load('holland.config.validator', check.name)
    except PluginError:
        raise ValidatorError("No validator found for check '%s'" % (check.name), None)
    validator.bind(check.args, check.kwargs)
    return validator

class ValidatorError(HollandError):
    """Raised if an error is encountered during validation"""
    
    def __init__(self, message, value):
        self.message = message
        self.value = value

    def __str__(self):
        return self.message

class AbstractValidator(BasePlugin):
    """Validator interface

    Validators take some value and check that
    it conforms to some set of constraints. If a value
    is the string representation of the real value then
    validate() will convert the string as needed.  format()
    will do the opposite and serialize a value back into
    useful config string.
    """

    #: validator namespace is holland.config.validator
    namespace = 'holland.config.validator'

    #: positional arguments passed to a check
    args = ()

    #: keyword arguments passed to a check
    kwargs = ()

    def __init__(self, name):
        super(AbstractValidator, self).__init__(name)
        # ensure kwargs is initialized to a base dict
        self.kwargs = dict()

    def bind(self, args, kwargs):
        """Bind check paramters to this validator"""
        self.args = args
        self.kwargs.update(kwargs)

    @classmethod
    def normalize(cls, value):
        "Normalize a string value"
        if isinstance(value, basestring):
            return unquote(value)
        else:
            return value

    @classmethod
    def convert(cls, value):
        """Convert a value from its string representation to a python
        object.

        :returns: converted value
        """
        return value

    def validate(self, value):
        """Validate a value and return its conversion

        :raises: ValidationError on failure
        :returns: converted value
        """
        value = self.normalize(value)
        return self.convert(value)

    @classmethod
    def format(cls, value):
        """Format a value as it should be written in a config file

        :returns: value formatted to a string
        """
        if value is None:
            return value
        return str(value)

@plugin_registry.register
class BoolValidator(AbstractValidator):
    """Validator for boolean values

    When converting a string this accepts the
    following boolean formats:
    True:  yes, on, true, 1
    False: no, off, false, 0
    """

    name = 'boolean'

    def convert(self, value):
        """Convert a string value to a python Boolean"""
        valid_bools = {
            'yes'  : True,
            'on'   : True,
            'true' : True,
            '1'    : True,
            'no'   : False,
            'off'  : False,
            'false': False,
            '0'    : False,
        }
        if isinstance(value, bool):
            return value
        return valid_bools[value.lower()]

    def format(self, value):
        """Format a python boolean as a string value"""
        return value and 'yes' or 'no'


@plugin_registry.register
class FloatValidator(AbstractValidator):
    """Validate float strings"""
    name = 'float'

    def convert(self, value):
        """Convert a string to float

        :raises: ValidationError
        :returns: python float representation of value
        """
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            raise ValidationError("Invalid format for float %s" % value, value)

    def format(self, value):
        """Format a float to a string"""
        return "%.2f" % value


@plugin_registry.register
class PercentValidator(AbstractValidator):
    """Validate percent strings and convert to float values

    PercentValidator().convert('100%') => 1
    PercentValidator().convert('3%') => 0.03
    """

    name = 'percent'

    def convert(self, value):
        percent = value
        if percent is None:
            return None
        if isinstance(percent, float):
            return percent
        if percent.endswith('%'):
            percent = percent[0:-1]
        try:
            return float(percent) / 100.0
        except ValueError as exc:
            raise ValidationError("Invalid format for percent: %s (%s)" %
                    (value, exc),
                    value)


@plugin_registry.register
class IntValidator(AbstractValidator):
    """Validate integer values"""
    
    name = 'integer'

    def convert(self, value):
        if value is None:
            return value
        if isinstance(value, int):
            value = value
        else:
            try:
                value = int(value, self.kwargs.get('base', 10))
            except ValueError:
                raise ValidationError("Invalid format for integer %s" % value,
                                      value)

        if self.kwargs.get('min') is not None and \
                value < self.kwargs.get('min'):
            raise ValidationError("Integer value must be > %d" %
                                  self.kwargs['min'], value)

        if self.kwargs.get('max') and value > self.kwargs.get('max'):
            raise ValidationError("Integer value exceeds maximum %d" %
                                  self.kwargs['max'], value)

        return value


@plugin_registry.register
class StringValidator(AbstractValidator):
    """Validate string values"""
    name = 'string'


@plugin_registry.register
class OptionValidator(AbstractValidator):
    """Validate against a list of options

    This constrains a value to being one of a series of constants
    """

    name = 'option'

    def convert(self, value):
        """Ensure value is one of the available options"""
        if value in self.args:
            return value
        raise ValidationError("invalid option '%s' - choose from: %s" %
                              (value, ','.join(self.args)),
                              value)


@plugin_registry.register
class ListValidator(AbstractValidator):
    """Validate a list

    This will validate a string is a proper comma-separate list. Each string
    in the list will be unquoted and a normal python list of the unquoted
    and unescaped values will be returned.
    """

    name = 'list'
    aliases = tuple(['force_list'])

    @staticmethod
    def _utf8_encode(unicode_csv_data):
        """Shim to convert lines of text to utf8 byte strings to allow
        processing by the csv module

        :returns: iterable of utf8 bytestrings
        """
        for line in unicode_csv_data:
            yield line.encode('utf-8')

    def normalize(self, value):
        "Normalize a value"
        # skip AbstractValidator's unquoting behavior
        return value

    def convert(self, value):
        """Convert a csv string to a python list"""
        if isinstance(value, list):
            return value
        reader = csv.reader(BytesIO(value.encode('utf8')),
                            delimiter=',',
                            skipinitialspace=True)
        result = []
        for row in reader:
            for cell in row:
                if cell:
                    result.append(unquote(cell.decode('utf8')))
        return result

    def format(self, value):
        """Format a list to a csv string"""
        result = BytesIO()
        writer = csv.writer(result, dialect='excel')
        writer.writerow([cell.encode('utf8') for cell in value])
        return result.getvalue().decode('utf8').strip()


@plugin_registry.register
class TupleValidator(ListValidator):
    """Validate a tuple

    Identical to ``ListValidator`` but returns a tuple rather than
    a list.
    """

    name = 'tuple'
    aliases = ()

    def convert(self, value):
        """Convert a csv string to a python tuple"""
        value = super(TupleValidator, self).convert(value)
        return tuple(value)


@plugin_registry.register
class SetValidator(ListValidator):
    """Validate a tuple

    Identical to ``ListValidator`` but returns a tuple rather than
    a list.
    """
    
    name = 'set'
    aliases = ()

    def convert(self, value):
        """Convert a csv string to a python tuple"""
        value = super(SetValidator, self).convert(value)
        return set(value)


from collections import namedtuple

NameArg = namedtuple('NameArg', 'name arg')

@plugin_registry.register
class NameArgValidator(AbstractValidator):
    """Validate a name:arg pair

    Converts to a namedtuple(name, arg)
    """

    name = 'namearg'

    def convert(self, value):
        if isinstance(value, NameArg):
            return value
        name, _, arg = value.partition(':')
        return NameArg(name=name, arg=arg)

    def format(self, value):
        if isinstance(value, basestring):
            return value

        return u'%s:%s' % value


@plugin_registry.register
class CmdlineValidator(AbstractValidator):
    """Validate a commmand line"""

    name = 'cmdline'

    def convert(self, value):
        """Convert a command line string to a list of command args"""
        if isinstance(value, list):
            return value
        if value is None:
            return []
        return [arg.decode('utf8') for arg in shlex.split(value.encode('utf8'))]

    def format(self, value):
        """Convert a list of command args to a single command line string"""
        if value is None:
            return ""
        return subprocess.list2cmdline(value)


@plugin_registry.register
class LogLevelValidator(AbstractValidator):
    """Validate a logging level

    This constraints a logging level to one of the standard levels supported
    by the python logging module:

    * debug
    * info
    * warning
    * error
    * fatal
    """

    name = 'log_level'

    levels = {
        'debug'         : logging.DEBUG,
        'info'          : logging.INFO,
        'warning'       : logging.WARNING,
        'error'         : logging.ERROR,
        'fatal'         : logging.FATAL,
        logging.DEBUG   : 'debug',
        logging.INFO    : 'info',
        logging.WARNING : 'warning',
        logging.ERROR   : 'error',
        logging.FATAL   : 'fatal',
    }

    def convert(self, value):
        """Convert a string log level to its integer equivalent"""
        if isinstance(value, int):
            return value
        try:
            return self.levels[value.lower()]
        except KeyError:
            raise ValidationError("Invalid log level '%s'" % value, value)

    def format(self, value):
        """Format an integer log level to its string representation"""
        try:
            return self.levels[value].lower()
        except KeyError:
            raise ValidationError("Unknown logging level '%s'" % value, value)

