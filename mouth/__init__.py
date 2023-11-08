# coding=utf8
""" Mouth

Exposes internal modules
"""

__author__		= "Chris Nasr"
__copyright__	= "Ouroboros Coding Inc."
__email__		= "chris@ouroboroscoding.com"
__created__		= "2023-10-13"

__all__ = ['errors', 'service', 'TemplateSystem']

# Local
from mouth import errors, service
from mouth.template_system import TemplateSystem