# coding=utf8
"""Template System

Holds base class used by each individual template implementation
"""
from __future__ import annotations

__author__		= "Chris Nasr"
__copyright__	= "Ouroboros Coding Inc."
__email__		= "chris@ouroboroscoding.com"
__created__		= "2023-10-14"

# Ouroboros imports
from body import ResponseException
import undefined

# Python imports
import abc
from typing import List, Literal

# Project imports
from mouth import errors
from mouth.records.template import Template, TEmail, TSms

# Types
TemplateType = Literal['email', 'sms']

class TemplateSystem(abc.ABC):
	"""Template System

	Base class that all other template implementations must extend from

	Extends:
		abc.ABC
	"""

	__implementations = {}
	"""Classes used to create new cache instances"""

	def __init__(self):
		"""Constructor

		Initialises the object and adds the member variables

		Returns:
			TemplateSystem
		"""

		# Add the list of found template records
		self.__t: dict = {}

	@abc.abstractmethod
	def valid(self, content: str, variables: List[str]) -> bool:
		"""Valid

		Returns if a template is valid or not based on the content and \
		available variables

		Arguments:
			content (str): The content to validate
			variables (str[]): The list of valid variables

		Returns:
			bool
		"""
		pass

	def _fetch(self,
		type_: TemplateType,
		name: List[str],
		locale: str = 'en-US',
		field: str = undefined
	) -> dict:
		"""Fetch

		Fetches the content associated with a template type by the given names \
		locale, and optionally, field

		Arguments:
			type_ ('email' | 'sms): The type of template data to fetch
			name (str[]): The name of the template
			locale (str): The name of the locale we want the template for
			field (str): The name of the field in the type

		Returns:
			dict
		"""

		# Init the return dict
		dRet = {}
		dMissing = { 't': [], 'c': [] }

		# Go through each name passed
		for s in name:

			# Do we have the record already?
			if s in self.__t:

				# Generate a combo of the locale and type
				sItem = '%s:%s' % (locale, type_)

				# Do we have the locale and type?
				if sItem in self.__t[s]['i']:

					# If there's a field, return it, else assume there's
					#	only the one string in the type
					dRet[s] = field is not undefined and \
						self.__t[s]['i'][locale][type_][field] or \
						self.__t[s]['i'][locale][type_]

				# Else, we are missing the content
				else:
					dMissing['c'].append([locale, type_, ])

			# Else, we are missing the template and the content
			else:
				dMissing['t'].append(s)
				dMissing['c'].append([locale, type_])

		# If we have any missing templates
		if dMissing['t']:

			# Find the templates by name
			lTemplates = Template.filter({
				'name': dMissing['t']
			}, raw=['_id', 'name'])

			# If the template is not found, raise an exception
			if not lTemplates or len(lTemplates) != len(dMissing['t']):
				raise ResponseException(error = (
					errors.body.DB_NO_RECORD,
					[dMissing['t'], 'template']
				))

			# Add each of the templates to the instance
			for d in lTemplates:
				self.__t[d['name']] = {
					'_id': d['_id'],
					'i': {}
				}



		# Generate a list of just the IDs
		lIDs = [d['_id'] for d in lTemplates]

		# If an email was requested
		if type_ == 'email':

			# Find the content by locale
			lContent = TEmail.filter({
				'template': lIDs,
				'locale': locale
			}, raw=['subject', 'text', 'html'], limit=1)

		# Else, if an sms was requested
		elif type_ == 'sms':

			# Find the content by locale
			lContent = TSms.filter({
				'template': lIDs,
				'locale': locale
			}, raw=['content'], limit=1)

		# If the content was not found, raise an exception
		if len(lContent) != len(name):
			raise ResponseException(error = (
				errors.body.DB_NO_RECORD, [
					'%s.%s' % (str(lIDs), locale),
					'template'
				]
			))

		# Return the found content
		return lContent

	@abc.abstractmethod
	def generate(self, content: str, variables: dict, ) -> str:
		"""Generate

		Takes template content and fully renders it using the variables \
		provided

		Arguments:
			content (str): The content to validate
			variables (str[]): The list of valid variables

		Returns:
			str
		"""
		pass

	@classmethod
	def register(cls, implementation: str) -> bool:
		"""Register

		Registers the class `cls` as a type that can be instantiated using the \
		implementation name

		Arguments:
			implementation (str): the name of the implementation that will be \
				added

		Raises:
			ValueError if the name has already been used

		Returns:
			None
		"""

		# If the name already exists
		if implementation in cls.__implementations:
			raise ValueError(implementation, 'already registered')

		# Store the new constructor
		cls.__implementations[implementation] = cls

	@classmethod
	def factory(cls, conf: dict) -> TemplateSystem:
		"""Factory

		Create an instance of the template system which will be able to fetch \
		and generate templates
`
		Arguments:
			conf (dict): The configuration for the template system, must \
				contain the implementation config

		Raises:
			KeyError if configuration for the implementation is missing
			ValueError if the implementation doesn't exist

		Returns:
			TemplateSystem
		"""

		# Get the configuration
		dConf = conf[conf['implementation']]

		# Create the instance by calling the implementation
		try:
			return cls.__implementations[conf['implementation']](dConf)
		except KeyError:
			raise ValueError(conf['implementation'], 'not registered')