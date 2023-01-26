# coding=utf8
""" Mouth Records

Handles the record structures for the Mouth service
"""

__author__		= "Chris Nasr"
__version__		= "1.0.0"
__maintainer__	= "Chris Nasr"
__email__		= "chris@ouroboroscoding.com"
__created__		= "2022-12-12"

# Python imports
import pathlib

# Pip imports
from FormatOC import Tree
from RestOC import Conf, Record_MySQL

# Get the definitions path
_defPath = '%s/definitions' % pathlib.Path(__file__).parent.resolve()

def install():
	"""Install

	Handles the initial creation of the tables in the DB

	Returns:
		None
	"""
	Locale.table_create()
	Template.table_create()
	TemplateEmail.table_create()
	TemplateSMS.table_create()

class Locale(Record_MySQL.Record):
	"""Locale

	Represents an allowed locale for use in templates

	Extends:
		Record_MySQL.Record
	"""

	_conf = None
	"""Configuration"""

	@classmethod
	def config(cls):
		"""Config

		Returns the configuration data associated with the record type

		Returns:
			dict
		"""

		# If we haven't loaded the config yet
		if not cls._conf:
			cls._conf = Record_MySQL.Record.generate_config(
				Tree.fromFile('%s/locale.json' % _defPath),
				override={'db': Conf.get(('mysql', 'db'), 'mouth')}
			)

		# Return the config
		return cls._conf

class Template(Record_MySQL.Record):
	"""Template

	Represents a single template, but not the individual content by locale

	Extends:
		Record_MySQL.Record
	"""

	_conf = None
	"""Configuration"""

	@classmethod
	def config(cls):
		"""Config

		Returns the configuration data associated with the record type

		Returns:
			dict
		"""

		# If we haven't loaded the config yet
		if not cls._conf:
			cls._conf = Record_MySQL.Record.generate_config(
				Tree.fromFile('%s/template.json' % _defPath),
				override={'db': Conf.get(('mysql', 'db'), 'mouth')}
			)

		# Return the config
		return cls._conf

class TemplateEmail(Record_MySQL.Record):
	"""Template Email

	Represents a single email version of a template by locale

	Extends:
		Record_MySQL.Record
	"""

	_conf = None
	"""Configuration"""

	@classmethod
	def config(cls):
		"""Config

		Returns the configuration data associated with the record type

		Returns:
			dict
		"""

		# If we haven't loaded the config yet
		if not cls._conf:
			cls._conf = Record_MySQL.Record.generate_config(
				Tree.fromFile('%s/template_email.json' % _defPath),
				override={'db': Conf.get(('mysql', 'db'), 'mouth')}
			)

		# Return the config
		return cls._conf

class TemplateSMS(Record_MySQL.Record):
	"""Template SMS

	Represents a single sms version of a template by locale

	Extends:
		Record_MySQL.Record
	"""

	_conf = None
	"""Configuration"""

	@classmethod
	def config(cls):
		"""Config

		Returns the configuration data associated with the record type

		Returns:
			dict
		"""

		# If we haven't loaded the config yet
		if not cls._conf:
			cls._conf = Record_MySQL.Record.generate_config(
				Tree.fromFile('%s/template_sms.json' % _defPath),
				override={'db': Conf.get(('mysql', 'db'), 'mouth')}
			)

		# Return the config
		return cls._conf
