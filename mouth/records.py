# coding=utf8
""" Mouth Test Record

Handles the locale record structure
"""

__author__		= "Chris Nasr"
__version__		= "1.0.0"
__maintainer__	= "Chris Nasr"
__email__		= "chris@ouroboroscoding.com"
__created__		= "2023-10-12"

# Ouroboros imports
from config import config
from define import Tree
from rest_mysql import Record_MySQL

# Python imports
import pathlib

# Get the definitions path
_defPath = '%s/definitions' % pathlib.Path(__file__).parent.resolve()

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
				Tree.from_file('%s/locale.json' % _defPath),
				override={'db': config.mysql.db('mouth')}
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
				Tree.from_file('%s/template.json' % _defPath),
				override={'db': config.mysql.db('mouth')}
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
				Tree.from_file('%s/template_email.json' % _defPath),
				override={'db': config.mysql.db('mouth')}
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
				Tree.from_file('%s/template_sms.json' % _defPath),
				override={'db': config.mysql.db('mouth')}
			)

		# Return the config
		return cls._conf