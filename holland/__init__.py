"""
holland
~~~~~~~

Holland backup manager

This is the base namespace for the holland backup manager

This is namespace package.  The core holland implemtation uses
the holland.core namespace and the holland command line interface
uses the holland.cli namespace.  Holland plugins implemented by
the Holland Core development team will exist under holland.{plugin_name}.
"""
__import__('pkg_resources').declare_namespace(__name__)
