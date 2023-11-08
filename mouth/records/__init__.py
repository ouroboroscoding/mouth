# coding=utf8
""" Records

Just passes along the modules
"""

__author__		= "Chris Nasr"
__copyright__	= "Ouroboros Coding Inc"
__version__		= "1.0.0"
__email__		= "chris@ouroboroscoding.com"
__created__		= "2023-11-07"

# Limit exports
__all__ = [
	'locale', 'Locale',
	'template', 'Template'
]

# Local imports
from mouth.records import locale, template

# Record imports
from mouth.records.locale import Locale
from mouth.records.template import Template