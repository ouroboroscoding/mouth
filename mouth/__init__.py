# coding=utf8
""" Mouth Service

Handles communication
"""

__author__		= "Chris Nasr"
__copyright__	= "Ouroboros Coding Inc."
__version__		= "1.0.0"
__email__		= "chris@ouroboroscoding.com"
__created__		= "2023-01-05"

# Python imports
from operator import itemgetter
import re

# Pip imports
from body import access, errors
from RestOC import	DictHelper, Record_Base, Services

# Records imports
from .records import Locale, Template, TemplateEmail, TemplateSMS

# Errors
from .errors import TEMPLATE_CONTENT_ERROR

class Mouth(Services.Service):
	"""Mouth Service class

	Service for outgoing communication
	"""

	_re_conditional = re.compile(r'\[if:([A-Za-z_]+):(eq|lt|lte|gt|gte|neq):([^\]]+)\](.+?)\[fi\]', re.DOTALL)
	_re_data = re.compile(r'\{([A-Za-z_]+)\}')
	_re_tpl = re.compile(r'\#([A-Za-z_]+)\#')
	"""Regular expressions for parsing/replacing"""

	_conditional = {
		'eq': lambda x, y: x == y,
		'lt': lambda x, y: x < y,
		'lte': lambda x, y: x <= y,
		'gt': lambda x, y: x > y,
		'gte': lambda x, y: x >= y,
		'neq': lambda x, y: x != y
	}
	"""Conditional lambdas"""

	@classmethod
	def _checkTemplateContent(cls, content, names, variables):
		"""Check Template Content

		Goes through template content and makes sure any variables or embedded
		templates actually exist

		Arguments:
			content (dict): A dictionary of content type data
			names (dict): A list of content type names
			variables (dict): The list of valid variables

		Returns:
			list
		"""

		# Init a list of variables and inner templates
		lsTemplates = set()
		lsVariables = set()

		# Go through each of the content types
		for k in names:
			try:

				# Look for, and store, templates
				for sTpl in cls._re_tpl.findall(content[k]):
					lsTemplates.add(sTpl)

				# Look for, and store, variables
				for sVar in cls._re_data.findall(content[k]):
					lsVariables.add(sVar)

			except KeyError:
				pass

		# Init errors list
		lErrors = []

		# If there's any templates
		if lsTemplates:

			# Look for all of them
			lTemplates = [d['name'] for d in Template.get(list(lsTemplates), raw=['name'])]

			# If the count doesn't match
			if len(lTemplates) != len(lsTemplates):

				# Get the missing templates
				for s in lsTemplates:
					if s not in lTemplates:
						lErrors.add(('template', s))

		# If there's any variables
		if lsVariables:

			# Go through each one
			for s in lsVariables:

				# If it's not in the templates list
				if s not in variables:
					lErrors.add(('variable', s))

		# Return errors (might be empty)
		return lErrors

	def initialise(self):
		"""Initialise

		Initialises the instance and returns itself for chaining

		Returns:
			Authorization
		"""

		# Return self for chaining
		return self

	def locale_create(self, req):
		"""Locale create

		Creates a new locale record instance

		Arguments:
			req (dict): The request data: body, session, and environment

		Returns:
			Services.Response
		"""

		# Make sure the client has access via the session
		access.verify(req['session'], 'mouth_locale', access.CREATE)

		# Verify the instance
		try:
			oLocale = Locale(req['data'])
		except ValueError as e:
			return Services.Error(errors.BODY_FIELD, e.args[0])

		# If it's valid data, try to add it to the DB
		try:
			oLocale.create()
		except Record_Base.DuplicateException as e:
			return Services.Error(errors.DB_DUPLICATE, 'locale')

		# Return OK
		return Services.Response(True)

	def locale_delete(self, req):
		"""Locale delete

		Deletes (or archives) an existing locale record instance

		Arguments:
			req (dict): The request data: body, session, and environment

		Returns:
			Services.Response
		"""

		# Make sure the client has access via the session
		access.verify(req['session'], 'mouth_locale', access.DELETE)

		# Make sure we have an ID
		if '_id' not in req['body']:
			return Services.Error(errors.BODY_FIELD, (('_id', 'missing')))

		# Look for the instance
		oLocale = Locale.get(req['body']['_id'])

		# If it doesn't exist
		if not oLocale:
			return Services.Error(errors.DB_NO_RECORD, (req['body']['_id'], 'locale'))

		# If it's being archived
		if 'archive' in req['body'] and req['body']['archive']:

			# Mark the record as archived
			oLocale['_archived'] = True

			# Save it in the DB and return the result
			return Services.Response(
				oLocale.save()
			)

		# Check for templates with the locale
		if TemplateEmail.count(filter={'locale': oLocale['_id']}) or \
			TemplateSMS.count(filter={'locale': oLocale['_id']}):

			# Return an error because we have existing templates still using the
			#	locale
			return Services.Error(errors.DB_KEY_BEING_USED, (oLocale['_id'], 'locale'))

		# Delete the record and return the result
		return Services.Response(
			oLocale.delete()
		)

	def locale_read(self, req):
		"""Locale read

		Returns an existing locale record instance or all records

		Arguments:
			req (dict): The request data: body, session, and environment

		Returns:
			Services.Response
		"""

		# Make sure the client has access via the session
		access.verify(req['session'], 'mouth_locale', access.READ)

		# If there's an ID
		if '_id' in req['body']:

			# Fetch the record
			dLocale = Locale.get(req['body'], raw=True)

			# If it doesn't exist
			if not dLocale:
				return Services.Error(errors.DB_NO_RECORD, (req['body']['_id'], 'locale'))

			# Return the raw data
			return Services.Response(dLocale)

		# If we want to include archived
		if 'archived' in req['body'] and req['body']['archived']:

			# Get and return all locales as raw data
			return Services.Response(
				Locale.get(raw=True, orderby='name')
			)

		# Else, return only those not marked as archived
		return Services.Response(
			Locale.get(filter={'_archived': False}, raw=True, orderby='name')
		)

	def locale_update(self, req):
		"""Locale update

		Updates an existing locale record instance

		Arguments:
			req (dict): The request data: body, session, and environment

		Returns:
			Services.Response
		"""

		# Make sure the client has access via the session
		access.verify(req['session'], 'mouth_locale', access.UPDATE)

		# Check minimum fields
		try: DictHelper.eval(req['body'], ['_id', 'name'])
		except ValueError as e: return Services.Error(errors.BODY_FIELD, ((f, 'missing') for f in e.args))

		# Find the record
		oLocale = Locale.get(req['body']['_id'])

		# If it doesn't exist
		if not oLocale:
			return Services.Error(errors.DB_NO_RECORD, (req['body']['_id'], 'locale'))

		# If it's archived
		if oLocale['_archived']:
			return Services.Error(errors.DB_ARCHIVED, (req['body']['_id'], 'locale'))

		# Try to update the name
		try:
			oLocale['name'] = req['body']['name']
		except ValueError as e:
			return Services.Error(errors.BODY_FIELD, [e.args[0]])

		# Save the record and return the result
		try:
			return Services.Response(
				oLocale.save()
			)
		except Record_Base.DuplicateException as e:
			return Services.Error(errors.DB_DUPLICATE, (req['body']['name'], 'template'))

	def template_create(self, req):
		"""Template create

		Creates a new template record instance

		Arguments:
			req (dict): The request data: body, session, and environment

		Returns:
			Services.Response
		"""

		# Make sure the client has access via the session
		access.verify(req['session'], 'mouth_template', access.CREATE)

		# If the name is missing
		if 'name' not in req['body']:
			return Services.Error(errors.BODY_FIELD, (('name', 'missing')))

		# Verify the instance
		try:
			oTemplate = Template(req['data'])
		except ValueError as e:
			return Services.Error(errors.BODY_FIELD, e.args[0])

		# If it's valid data, try to add it to the DB
		try:
			oTemplate.create()
		except Record_Base.DuplicateException as e:
			return Services.Error(errors.DB_DUPLICATE, 'template')

		# Return the ID to indicate OK
		return Services.Response(oTemplate['_id'])

	def template_delete(self, req):
		"""Template delete

		Deletes an existing template record instance

		Arguments:
			req (dict): The request data: body, session, and environment

		Returns:
			Services.Response
		"""

		# Make sure the client has access via the session
		access.verify(req['session'], 'mouth_template', access.DELETE)

		# If the ID is missing
		if '_id' not in req['body']:
			return Services.Error(errors.BODY_FIELD, (('_id', 'missing')))

		# Find the record
		oTemplate = Template.get(req['body']['_id'])

		# If it's not found
		if not oTemplate:
			return Services.Error(errors.DB_NO_RECORD, (req['body']['_id'], 'template'))

		# Delete all Email templates associated
		TemplateEmail.delete_get(req['body']['_id'], index='template')

		# Delete all SMS templates associated
		TemplateSMS.delete_get(req['body']['_id'], index='template')

		# Delete the template and return the result
		return Services.Response(
			oTemplate.delete()
		)

	def template_read(self, req):
		"""Template read

		Fetches and returns the template with the associated content records

		Arguments:
			req (dict): The request data: body, session, and environment

		Returns:
			Services.Response
		"""

		# Make sure the client has access via the session
		access.verify(req['session'], 'mouth_template', access.READ)

		# If the ID is missing
		if '_id' not in req['body']:
			return Services.Error(errors.BODY_FIELD, (('_id', 'missing')))

		# Find the record
		dTemplate = Template.get(req['body']['_id'], raw=True)

		# if it doesn't exist
		if not dTemplate:
			return Services.Error(errors.DB_NO_RECORD, (req['body']['_id'], 'template'))

		# Init the list of content
		dTemplate['content'] = []

		# Find all associated email content
		dTemplate['content'].extend([
			dict(d, type='email') for d in
			TemplateEmail.get(req['body']['_id'], index='template', raw=True)
		])

		# Find all associated sms content
		dTemplate['content'].extend([
			dict(d, type='sms') for d in
			TemplateSMS.get(req['body']['_id'], index='template', raw=True)
		])

		# If there's content
		if len(dTemplate['content']) > 1:

			# Sort it by locale and type
			dTemplate['content'].sort(key=itemgetter('locale', 'type'))

		# Return the template
		return Services.Response(dTemplate)

	def template_update(self, req):
		"""Template update

		Updates an existing template record instance

		Arguments:
			req (dict): The request data: body, session, and environment

		Returns:
			Services.Response
		"""

		# Make sure the client has access via the session
		access.verify(req['session'], 'mouth_template', access.UPDATE)

		# Check for ID
		if '_id' not in req['body']:
			return Services.Error(errors.BODY_FIELD, (('_id', 'missing')))

		# Find the record
		oTemplate = Template.get(req['body']['_id'])

		# If it doesn't exist
		if not oTemplate:
			return Services.Error(errors.DB_NO_RECORD, (req['body']['_id'], 'template'))

		# Remove fields that can't be updated
		for k in ['_id', '_created', '_updated']:
			try: del req['body'][k]
			except KeyError: pass

		# If there's nothing left
		if not req['body']:
			return Services.Response(False)

		# Init errors list
		lErrors = []

		# Update remaining fields
		for k in req['body']:
			try:
				oTemplate[k] = req['body'][k]
			except ValueError as e:
				lErrors.extend(e.args[0])

		# Save the record and return the result
		try:
			return Services.Response(
				oTemplate.save()
			)
		except Record_Base.DuplicateException as e:
			return Services.Error(errors.DB_DUPLICATE, (req['body']['name'], 'template'))

	def template_email_create(self, req):
		"""Template Email create

		Adds an email content record to an existing template record instance

		Arguments:
			req (dict): The request data: body, session, and environment

		Returns:
			Services.Response
		"""

		# Make sure the client has access via the session
		access.verify(req['session'], 'mouth_content', access.CREATE)

		# Check minimum fields
		try: DictHelper.eval(req['body'], ['template', 'locale'])
		except ValueError as e: return Services.Error(errors.BODY_FIELD, ((f, 'missing') for f in e.args))

		# Make sure the template exists
		dTemplate = Template.get(req['body']['template'], raw=['variables'])
		if not dTemplate:
			return Services.Error(errors.DB_NO_RECORD, (req['body']['template'], 'template'))

		# Make sure the locale exists
		if not Locale.exists(req['body']['locale']):
			return Services.Error(errors.DB_NO_RECORD, (req['body']['locale'], 'locale'))

		# Verify the instance
		try:
			oEmail = TemplateEmail(req['body'])
		except ValueError as e:
			return Services.Error(errors.BODY_FIELD, e.args[0])

		# Check content for errors
		lErrors = self._checkTemplateContent(
			req['body'],
			['subject', 'text', 'html'],
			dTemplate['variables']
		)

		# If there's any errors
		if lErrors:
			return Services.Error(TEMPLATE_CONTENT_ERROR, lErrors)

		# Create the record
		try:
			oEmail.create()
		except Record_Base.DuplicateException as e:
			return Services.Error(errors.DB_DUPLICATE, (req['body']['locale'], 'template_locale'))

		# Return the ID to indicate OK
		return Services.Response(oEmail['_id'])

	def template_email_delete(self, req):
		"""Template Email delete

		Deletes email content from an existing template record instance

		Arguments:
			req (dict): The request data: body, session, and environment

		Returns:
			Services.Response
		"""

		# Make sure the client has access via the session
		access.verify(req['session'], 'mouth_content', access.DELETE)

		# If the ID is missing
		if '_id' not in req['body']:
			return Services.Error(errors.BODY_FIELD, (('_id', 'missing')))

		# Find the record
		oEmail = TemplateEmail.get(req['body']['_id'])

		# If it doesn't exist
		if not oEmail:
			return Services.Error(errors.DB_NO_RECORD, (req['body']['_id'], 'template_email'))

		# Delete the record and return the result
		return Services.Response(
			oEmail.delete()
		)

	def template_email_update(self, req):
		"""Template Email update

		Updated email content of an existing template record instance

		Arguments:
			req (dict): The request data: body, session, and environment

		Returns:
			Services.Response
		"""

		# Make sure the client has access via the session
		access.verify(req['session'], 'mouth_content', access.UPDATE)

		# If the ID is missing
		if '_id' not in req['body']:
			return Services.Error(errors.BODY_FIELD, (('_id', 'missing')))

		# Find the record
		oEmail = TemplateEmail.get(req['body']['_id'])

		# If it doesn't exist
		if not oEmail:
			return Services.Error(errors.DB_NO_RECORD, (req['body']['_id'], 'template_email'))

		# Remove fields that can't be updated
		for k in ['_id', '_created', '_updated', 'template', 'locale']:
			try: del req['body'][k]
			except KeyError: pass

		# If there's nothing left
		if not req['body']:
			return Services.Response(False)

		# Init errors list
		lErrors = []

		# Update remaining fields
		for k in req['body']:
			try:
				oEmail[k] = req['body'][k]
			except ValueError as e:
				lErrors.extend(e.args[0])

		# If there's any errors
		if lErrors:
			return Services.Error(errors.BODY_FIELD, lErrors)

		# Find the primary template variables
		dTemplate = Template.get(oEmail['template'], raw=['variables'])

		# Check content for errors
		lErrors = self._checkTemplateContent(
			req['body'],
			['subject', 'text', 'html'],
			dTemplate['variables']
		)

		# If there's any errors
		if lErrors:
			return Services.Error(TEMPLATE_CONTENT_ERROR, lErrors)

		# Save the record and return the result
		return Services.Response(
			oEmail.save()
		)

	def template_sms_create(self, req):
		"""Template SMS create

		Adds an sms content record to an existing template record instance

		Arguments:
			req (dict): The request data: body, session, and environment

		Returns:
			Services.Response
		"""

		# Make sure the client has access via the session
		access.verify(req['session'], 'mouth_content', access.CREATE)

		# Check minimum fields
		try: DictHelper.eval(req['body'], ['template', 'locale'])
		except ValueError as e: return Services.Error(errors.BODY_FIELD, ((f, 'missing') for f in e.args))

		# Make sure the template exists
		dTemplate = Template.get(req['body']['template'], raw=['variables'])
		if not dTemplate:
			return Services.Error(errors.DB_NO_RECORD, (req['body']['template'], 'template'))

		# Make sure the locale exists
		if not Locale.exists(req['body']['locale']):
			return Services.Error(errors.DB_NO_RECORD, (req['body']['locale'], 'locale'))

		# Verify the instance
		try:
			oSMS = TemplateSMS(req['body'])
		except ValueError as e:
			return Services.Error(errors.BODY_FIELD, e.args[0])

		# Check content for errors
		lErrors = self._checkTemplateContent(
			req['body'],
			['content'],
			dTemplate['variables']
		)

		# If there's any errors
		if lErrors:
			return Services.Error(TEMPLATE_CONTENT_ERROR, lErrors)

		# Create the record
		try:
			oSMS.create()
		except Record_Base.DuplicateException as e:
			return Services.Error(errors.DB_DUPLICATE, (req['body']['locale'], 'template_locale'))

		# Return the ID to indicate OK
		return Services.Response(oSMS['_id'])

	def template_sms_delete(self, req):
		"""Template SMS delete

		Deletes sms content from an existing template record instance

		Arguments:
			req (dict): The request data: body, session, and environment

		Returns:
			Services.Response
		"""

		# Make sure the client has access via the session
		access.verify(req['session'], 'mouth_content', access.DELETE)

		# If the ID is missing
		if '_id' not in req['body']:
			return Services.Error(errors.BODY_FIELD, (('_id', 'missing')))

		# Find the record
		oSMS = TemplateSMS.get(req['body']['_id'])

		# If it doesn't exist
		if not oSMS:
			return Services.Error(errors.DB_NO_RECORD, (req['body']['_id'], 'template_sms'))

		# Delete the record and return the result
		return Services.Response(
			oSMS.delete()
		)

	def template_sms_update(self, req):
		"""Template SMS update

		Updated sms content of an existing template record instance

		Arguments:
			req (dict): The request data: body, session, and environment

		Returns:
			Services.Response
		"""

		# Make sure the client has access via the session
		access.verify(req['session'], 'mouth_content', access.UPDATE)

		# Check minimum fields
		try: DictHelper.eval(req['body'], ['_id', 'content'])
		except ValueError as e: return Services.Error(errors.BODY_FIELD, ((f, 'missing') for f in e.args))

		# Find the record
		oSMS = TemplateSMS.get(req['body']['_id'])

		# If it doesn't exist
		if not oSMS:
			return Services.Error(errors.DB_NO_RECORD, (req['body']['_id'], 'template_sms'))

		# Update the content
		try:
			oSMS['content'] = req['body']['content']
		except ValueError as e:
			return Services.Error(errors.BODY_FIELD, [e.args[0]])

		# Find the primary template variables
		dTemplate = Template.get(oSMS['template'], raw=['variables'])

		# Check content for errors
		lErrors = self._checkTemplateContent(
			req['body'],
			['content'],
			dTemplate['variables']
		)

		# If there's any errors
		if lErrors:
			return Services.Error(TEMPLATE_CONTENT_ERROR, lErrors)

		# Save the record and return the result
		return Services.Response(
			oSMS.save()
		)