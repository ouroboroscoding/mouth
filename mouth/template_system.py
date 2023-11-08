# coding=utf8
"""Template System

Holds base class used by each individual template implementation
"""
from __future__ import annotations

__author__		= "Chris Nasr"
__copyright__	= "Ouroboros Coding Inc."
__email__		= "chris@ouroboroscoding.com"
__created__		= "2023-10-14"

# Python imports
import abc
from typing import List, Literal

# Project imports
from mouth.records.template import Template

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

	def _exists(self, name: List[str]) -> bool:
		"""Exists

		Returns if the list of templates exists or not

		Arguments:
			name (str[]): The names of templates to check

		Returns:
			bool
		"""
		pass

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

	def _fetch(self, names: List[str], locale: str, field: str) -> dict:
		"""Fetch

		Fetches the content associated with a template type by the given names \
		locale, and optionally, field

		Arguments:
			names (str[]): The names of the templates
			locale (str): The name of the locale we want the template for
			field (str): The name of the field in the locale

		Returns:
			dict
		"""

		# Init the return dict
		dRet = {}
		lMissing = []

		# Go through each name passed
		for s in names:

			# If we don't have the name
			if s not in self.__t:

				# Add it to the missing
				lMissing.append(s)

		# If we have any missing templates
		if lMissing:

			# Find the templates by name
			lTemplates = Template.fetch(filter = {
				'name': lMissing
			}, raw = True)

			# If we are missing any
			if len(lTemplates) != len(lMissing):

				# Go through each one returned
				for d in lTemplates:
					lMissing.remove(d['name'])

				return

			# Add each of the templates to the instance
			for d in lTemplates:
				self.__t[d['name']] = d

		# Go through each name requested
		for s in names:

			# If we don't have the name
			if self.__t[s] is None:
				return '!%s INVALID TEMPLATE!' % s

			# If we don't have the type
			try:
				dRet[s] = self.__t[s]['locales'][locale][type_][field]
			except KeyError as e:
				return '!%s.%s.%s.%s NOT FOUND!' % (s, locale, type_, field)

		# Return the found content
		return dRet

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

	@abc.abstractmethod
	def errors(self,
		content: str,
		variables: List[str]
	) -> List[List[str]] | None:
		"""Errors

		Returns any errors in a template, else None for valid

		Arguments:
			content (str): The content to validate
			variables (str[]): The list of valid variables

		Returns:
			str[][] | None
		"""
		pass