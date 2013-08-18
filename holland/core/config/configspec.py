"""
holland.core.config.configspec
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Support for defining valid config parameters and values and validating
candidate configs

:copyright: 2010-2013 Rackspace US, Inc.
:license: BSD, see LICENSE.rst for details
"""

import logging
from .config import Config, BaseFormatter
from .util import missing
from .checks import Check, CheckError
from .validators import load_validator, ValidatorError

LOG = logging.getLogger(__name__)

class ValidateError(ValueError):
    """Raised when one or more errors are encountered during
    Configspec.validate()

    """
    def __init__(self, errors):
        ValueError.__init__(self)
        self.errors = errors

    def __repr__(self):
        result = [
            "%d validation errors encountered" % len(self.errors)
        ]
        for error, source in self.errors:
            if source:
                lines = source[1:]
                if lines[0] != lines[-1]:
                    lines = "-".join([str(x) for x in lines])
                else:
                    lines = str(lines[-1])
                result.append("%s line %s: %s" % (source[0], lines, error))
            else:
                result.append("%s" % error)
        return "\n".join(result)

    __str__ = __repr__

class CheckFormatter(BaseFormatter):
    """Format a ``Config`` instance based on
    the validators associated with a Configspec
    """

    def __init__(self, configspec):
        BaseFormatter.__init__(self)
        self.configspec = configspec

    def format(self, key, value):
        """Format an option/value pair based on the
        associated Validator's format method

        :returns: formatted value string
        """
        try:
            check = Check.parse(self.configspec.get(key, ''))
        except CheckError:
            return value

        try:
            validator = load_validator(check)
            return validator.format(value)
        except ValidatorError:
            return value

class Configspec(Config):
    """A configuration that can validate other configurations
    """

    def __init__(self, *args, **kwargs):
        super(Configspec, self).__init__(*args, **kwargs)

    def validate(self, config, suppress_missing=False):
        """Validate a config against this configspec.

        This method modifies ``config`` replacing option values with the
        conversion provided by the associated check.

        :param config: config instance to validate
        :returns: validated config
        """
        errors = []
        if not isinstance(config, Config):
            config = Config(config)

        for key, value in self.iteritems():
            if isinstance(value, dict):
                try:
                    self._validate_section(key, config)
                except ValidateError as exc:
                    errors.extend(exc.errors)
            else:
                try:
                    self.validate_option(key, config)
                except ValidatorError as exc:
                    errors.append((exc, config.source.get(key, None)))

        if not suppress_missing:
            self.check_missing(config, suppress_missing)
        config.formatter = CheckFormatter(self)
        if errors:
            raise ValidateError(errors)
        return config

    def _validate_section(self, key, config):
        """Validate a subsection """
        try:
            cfgsect = config[key]
        except KeyError:
            # missing section in config that we are validating
            cfgsect = config.setdefault(key, config.__class__())
            cfgsect.name = key
            if key not in config.source:
                config.source[key] = self.source[key]

        # ensure we are always validating a Config instance
        if not isinstance(cfgsect, Config):
            cfgsect = config.__class__(cfgsect)
            config[key] = cfgsect
            config.source[key] = self.source[key]

        check = self[key]
        # handle raw dict objects as configspec input
        if not isinstance(check, Configspec):
            check = self.__class__(check)

        # recurse to the Configspec subsection
        check.validate(cfgsect)

    def validate_option(self, key, config):
        """Validate a single option"""
        check = Check.parse(self[key])

        if key not in config:
            if check.is_alias:
                LOG.debug("Skipping check for configspec option %s in [%s] "
                          "because config %s has no option and option %s is "
                          "an alias for canonical option '%s'",
                          key, config.section,
                          config.path,
                          key, check.aliasof)
                return
            if check.default is not missing:
                value = check.default
            else:
                value = missing
        else:
            value = config[key]

        validator = load_validator(check)

        try:
            value = validator.validate(value)
        except ValidatorError as exc:
            raise ValidatorError("[%s] -> %s : %s" % (
                                    config.section,
                                    key,
                                    exc
                                  ), value)

        config[key] = value
        if key not in config.source:
            config.source[key] = self.source[key]

        if check.is_alias:
            if check.aliasof not in config or \
                    config.is_after(key, check.aliasof):
                config.rename(key, check.aliasof)
            else:
                # check.aliasof is in config
                # or check.aliasof is after key
                del config[key]

    def _resolve_value(self, key, check, config):
        """Resolve a value for a given key

        This will find where a value is defined or raise an error if no such
        key exists.  This looks for the value in the following places:

        * Use the original config's value if one was specified
        * if the config did not have a value, attempt to use the aliasof value
        * if the key is not aliased then use the default value provided by the
          check
        * if no value at all is specified and there is no default for the check
          raise a ValidatorError
        """
        value = config.get(key, missing)
        if value is missing:
            value = check.default
        # if not even a default value, raise an error noting this option is
        # required
        if value is missing:
            raise ValidatorError("Option '%s' requires a specified value" %
                                  key, None)
        return value

    def _validate_option(self, key, checkstr, config):
        """Validate a single option for this configspec"""
        try:
            check = Check.parse(checkstr)
        except CheckError:
            raise ValidatorError("Internal Error.  Failed to parse a "
                                  "validation check '%s'" % checkstr, checkstr)

        # Missing key that's an aliasof some other key
        # if that other name is in the config, use that instead
        if key not in config and check.aliasof in config:
            return

        try:
            validator = load_validator(check)
        except ValidatorError:
            raise ValidatorError("Unknown validation check '%s'" % check.name,
                                  checkstr)
        value = config.get(key, check.default)
        try:
            value = validator.validate(value)
        except ValidatorError as exc:
            raise ValidatorError("%s.%s : %s" % (config.section, key, exc),
                                  exc.value)
        config[key] = value
        if key not in config.source:
            config.source[key] = self.source[key]

        if check.aliasof is not missing:
            return check.aliasof


    def check_missing(self, config, ignore_unknown_sections):
        """Check for values in config with no corresponding configspec entry

        These are either bugs in the configspec or simply typos or invalid
        options.
        """
        for key in config.keys():
            if key not in self:
                if isinstance(config[key], dict):
                    if ignore_unknown_sections:
                        continue
                    source  = config.source.get(key)
                    LOG.warn("Unknown section[%s]", key)
                else:
                    #source, start, end = config.source[key]
                    source = config.source.get(key)
                    if source:
                        source, start, end = source
                        if start == end:
                            line_range = "line %d" % start
                        else:
                            line_range = "lines %d-%d" % (start, end)
                        LOG.warn("Unknown option %s in [%s] from %s %s", key,
                                config.section, source, line_range)
                    else:
                        LOG.warn("Unknown option %s in [%s]",
                                 key, config.section)
                del config[key]
