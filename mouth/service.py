# coding=utf8
""" Mouth Service

Handles communication
"""

__author__		= "Chris Nasr"
__copyright__	= "Ouroboros Coding Inc."
__version__		= "1.0.0"
__email__		= "chris@ouroboroscoding.com"
__created__		= "2023-01-05"

# Limit exports
__all__ = ['errors', 'Mouth']

# Ouroboros imports
from body import Error, Response, ResponseException, Service
from brain.helpers import access
from config import config
import em
from jobject import jobject
from rest_mysql.Record_MySQL import DuplicateException
from strings import to_bool
from tools import clone, evaluate, without
import undefined

# Python imports
from base64 import b64decode
from hashlib import md5
from operator import itemgetter
import re
from typing import Dict, List

# Mouth imports
from mouth import errors
from mouth.records import Locale, Template, TemplateEmail, TemplateSMS

class Mouth(Service):
	"""Mouth Service class

	Service for outgoing communication
	"""

	_special_conditionals = {
		'$EMPTY': '',
		'$NULL': None
	}
	"""Special conditional values"""

	_re_if_else = re.compile(
		r'\[[\t ]*if[\t ]+([A-Za-z_]+)(?:[\t ]+(==|<|<=|>|>=|!=)[\t ]+([^\]]+))?[\t ]*\]\n?(.+?)\n?(?:\[[\t ]*else[\t ]*\]\n?(.+?)\n?)?\[[\t ]*fi[\t ]*\]',
		re.DOTALL
	)
	_re_data = re.compile(r'\{([A-Za-z_]+)\}')
	_re_tpl = re.compile(r'\#([A-Za-z_]+)\#')
	"""Regular expressions for parsing/replacing"""

	_conditional = {
		'==': lambda x, y: x == y,
		'<': lambda x, y: x < y,
		'<=': lambda x, y: x <= y,
		'>': lambda x, y: x > y,
		'>=': lambda x, y: x >= y,
		'!=': lambda x, y: x != y
	}
	"""Conditional lambdas"""

	@classmethod
	def _check_template_content(cls,
		content: Dict[str, str],
		names: List[str],
		variables: Dict[str, str]
	) -> list:
		"""Check Template Content

		Goes through template content and makes sure any variables or embedded \
		templates actually exist. Returns a list of errors where each error is \
		a list of strings with 0 being the type of data missing, and 1 being \
		the name / variable not found. For example:
			[ [ 'template', 'header' ], [ 'template', 'footer' ] ], or
			[ [ 'variable', 'title' ] ], or
			[ [ 'variable', 'var1' ], [ 'template', 'main' ] ]
		Errors are found as files are looked at from top to bottom and \
		template to template.

		Arguments:
			content (dict): A dictionary of content type data
			names (list): A list of content type names
			variables (dict): The list of valid variables

		Returns:
			str[][]
		"""

		# Init sets of variables and inner templates
		lsTemplates = set()
		lsVariables = set()

		# Go through each of the content types passed in
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

		# If any templates were found
		if lsTemplates:

			# Look for all of them in the DB and return just their names
			lTemplates = [d['name'] for d in Template.filter({
				'name': list(lsTemplates)
			}, raw = [ 'name' ])]

			# If the counts of requested and fetched don't match up
			if len(lTemplates) != len(lsTemplates):

				# Go through the missing templates and add them as errors
				for s in lsTemplates:
					if s not in lTemplates:
						lErrors.append([ 'template', s ])

		# If there's any variables
		if lsVariables:

			# Go through each one
			for s in lsVariables:

				# If it's not in the variables list, add it as an error
				if s not in variables:
					lErrors.append([ 'variable', s ])

		# Return errors (might be empty)
		return lErrors

	def _email(self, opts: Dict[str, any]) -> dict:
		"""Email

		Handles the actual sending of the email, returns a dict with \
		success:bool, and error:str if success is False

		Arguments:
			opts (dict): The options used to generate and send the email

		Raises:
			ResponseException

		Returns:
			dict
		"""

		# If the from is not set
		if 'from' not in opts:
			opts['from'] = self._dEmail['from']

		# Init the attachments var
		mAttachments = None

		# If there's an attachment
		if 'attachments' in opts:

			# Make sure it's a list
			if not isinstance(opts['attachments'], ( list, tuple )):
				opts['attachments'] = [ opts['attachments' ]]

			# Loop through the attachments
			for i in range(len(opts['attachments'])):

				# If we didn't get a dictionary
				if not isinstance(opts['attachments'][i], dict):
					raise ResponseException(error = (
						errors.ATTACHMENT_STRUCTURE, 'attachments.[%d]' % i
					))

				# If the fields are missing
				try:
					evaluate(
						opts['attachments'][i], ['body', 'filename']
					)
				except ValueError as e:
					raise ResponseException(error = (
						errors.body.DATA_FIELDS,
						[['attachments.[%d].%s' % (i, s), 'invalid'] \
							for s in e.args]
					))

				# Try to decode the base64
				try:
					opts['attachments'][i]['body'] = b64decode(
						opts['attachments'][i]['body']
					)
				except TypeError:
					raise ResponseException(error = errors.ATTACHMENT_DECODE)

			# Set the attachments from the opts
			mAttachments = opts['attachments']

		# Only send if anyone is allowed, or the to is in the allowed
		if not self._dEmail['allowed'] or opts['to'] in self._dEmail['allowed']:

			# Send the e-mail
			iRes = em.send(
				'override' in self._dEmail and \
					self._dEmail['override'] or \
					opts['to'],
				opts['subject'],
				{	'from': opts['from'],
					'text': opts['text'],
					'html': opts['html'],
					'attachments': mAttachments }
			)

			# If there was an error
			if iRes != em.OK:
				return {
					'success': False,
					'error': '%i %s' % (iRes, em.last_error())
				}

		# Return OK
		return { 'success': True }

	@classmethod
	def _generate_content(cls,
		content: str,
		variables: Dict[str, str]
	) -> str:
		"""Generate Content

		Takes template content from any source, parses it, then fills in \
		template names and variables found with what's available.

		Arguments:
			content (str): The template content to render
			variables (dict): The current variable names and values available

		Returns:
			str
		"""

		# Look for variables
		for sVar in cls._re_data.findall(content):

			# Replace the string with the data value or an error message
			content = content.replace(
				'{%s}' % sVar,
				sVar in variables and \
					str(variables[sVar]) or \
					'!!!{%s}!!!' % sVar
			)

		# Look for if/else conditionals
		for oConditional in cls._re_if_else.finditer(content):

			# Get the entire text to replace
			sReplace = oConditional.group(0)

			# Get the conditional parts
			sVariable, sTest, mValue, sIf, sElse = oConditional.groups()

			# Get the groups and the length
			lGroups = list(oConditional.groups())

			# If we have no test or value
			if sTest is None and mValue is None:

				# Get the status of the variable
				bPassed = sVariable in variables and variables[sVariable]

				# Figure out the replacement content
				sNewContent = bPassed and sIf or (sElse or '')

				# Replace the content
				content = content.replace(sReplace, sNewContent)

			# Else, we have a condition and value to run
			else:

				# Replace special tags in variable value
				for n,v in cls._special_conditionals.items():
					if mValue == n:
						mValue = v

				# Check for the variable
				if sVariable not in variables:
					content = content.replace(
						sReplace,
						'INVALID VARIABLE (%s) IN CONDITIONAL' % sVariable
					)
					continue

				# If we didn't get None for the value
				if mValue is not None:

					# Get the type of value for the variable
					oVarType = type(variables[sVariable])

					# Attempt to convert the value from a string if required
					try:

						# If it's a bool
						if oVarType == bool:
							mValue = to_bool(mValue)

						# Else, if it's not a string
						elif oVarType != str and oVarType != None:
							mValue = oVarType(mValue)

					# If we can't convert the value
					except ValueError:
						content = content.replace(
							sReplace,
							'%s HAS INVALID VALUE IN CONDITIONAL' % sVariable
						)
						continue

				# Figure out if the condition passed or not
				bPassed = cls._conditional[lGroups[cls.COND_TYPE]](
					variables[sVariable], mValue
				)

				# Figure out the replacement content
				sNewContent = bPassed and lGroups[cls.COND_IF_CONTENT] or (
					lGroups[cls.COND_ELSE_CONTENT] or ''
				)

				# Replace the conditional with the inner text if it passed, else
				#	just remove it
				content = content.replace(sReplace, sNewContent)

		# Return new content
		return content

	@classmethod
	def _generate_email(cls,
		content: Dict[str, str],
		locale: str,
		variables: Dict[str, str],
		templates: Dict[str, Dict[str, str]] = undefined
	) -> Dict[str, str]:
		"""Generate Email

		Takes content, locale, and variables, and renders the final result of \
		the three parts of the email template

		Arguments:
			content (dict): The content to be rendered, 'subject', 'text', and \
				'html'
			locale (str): The locale used for embedded templates
			variables (dict): The variable names and their values
			templates (dict): The templates already looked up

		Returns:
			dict
		"""

		# If there's no templates yet
		if templates is undefined:
			templates = {}

		# Copy the contents
		dContent = clone(content)

		# Go through each each part of the template
		for s in [ 'subject', 'text', 'html' ]:

			# If the part is somehow missing
			if s not in dContent:
				dContent[s] = '!!!%s missing!!!' % s
				continue

			# Look for embedded templates
			for sTpl in cls._re_tpl.findall(dContent[s]):

				# If we don't have the template yet
				if sTpl not in templates:

					# Look for the primary template
					dTemplate = Template.filter({
						'name': sTpl
					}, raw = [ '_id' ], limit = 1)

					# If it doesn't exist
					if not dTemplate:
						templates[sTpl] = {
							'subject': '!!!#%s#!!!' % sTpl,
							'text': '!!!#%s#!!!' % sTpl,
							'html': '!!!#%s#!!!' % sTpl
						}

					# Else
					else:

						# Look for the locale dContent
						dEmail = TemplateEmail.filter({
							'template': dTemplate['_id'],
							'locale': locale
						}, raw = [ 'subject', 'text', 'html' ], limit = 1)

						# If it doesn't exist
						if not dEmail:
							templates[sTpl] = {
								'subject': '!!!#%s.%s#!!!' % (
									sTpl, locale
								),
								'text': '!!!#%s.%s#!!!' % (
									sTpl, locale
								),
								'html': '!!!#%s.%s#!!!' % (
									sTpl, locale
								)
							}

						# Else, generate the embedded template
						else:
							templates[sTpl] = cls._generate_email(
								dEmail, locale, variables, templates
							)

				# Replace the string with the value from the child
				dContent[s] = dContent[s].replace(
					'#%s#' % sTpl, templates[sTpl][s]
				)

			# Handle the variables and conditionals
			dContent[s] = cls._generate_content(dContent[s], variables)

		# Return the new contents
		return dContent

	@classmethod
	def _generate_sms(cls,
		content: str,
		locale: str,
		variables: Dict[str, str],
		templates: Dict[str, Dict[str, str]] = undefined
	) -> str:
		"""Generate SMS

		Takes content, locale, and variables, and renders the final result of \
		the template

		Arguments:
			content (str): The content to be rendered
			locale (str): The locale used for embedded templates
			variables (dict): The variable names and their values
			templates (dict): The templates already looked up

		Returns:
			str
		"""

		# If there's no templates yet
		if templates is undefined:
			templates = {}

		# Look for embedded templates
		for sTpl in cls._re_tpl.findall(content):

			# If we don't have the template yet
			if sTpl not in templates:

				# Look for the primary template
				dTemplate = Template.filter({
					'name': sTpl
				}, raw = [ '_id' ], limit = 1)

				# If it doesn't exist
				if not dTemplate:
					templates[sTpl] = '!!!#%s#!!!' % sTpl

				# Else
				else:

					# Look for the locale dContent
					dSMS = TemplateSMS.filter({
						'template': dTemplate['_id'],
						'locale': locale
					}, raw = [ 'content' ], limit = 1)

					# If it doesn't exist
					if not dSMS:
						templates[sTpl] = '!!!#%s.%s#!!!' % (
							sTpl, locale
						)

					# Else, generate the embedded template
					else:
						templates[sTpl] = cls._generate_sms(
							dSMS['content'], locale, variables, templates
						)

			# Replace the string with the value from the child
			content = content.replace('#%s#' % sTpl, templates[sTpl])

		# Handle the variables and conditionals
		content = cls._generate_content(content, variables)

		# Return the new contents
		return content

	def _sms(self, opts: dict) -> dict:
		"""SMS

		Sends an SMS using twilio

		Arguments:
			opts (dict): The options used to generate and send the SMS

		Returns:
			dict
		"""

		# Only send if anyone is allowed, or the to is in the allowed
		if not self._dSMS['allowed'] or opts['to'] in self._dSMS['allowed']:

			# Import twilio exception here for lazyish loading
			from twilio.base.exceptions import TwilioRestException

			# Init the base arguments
			dArgs = {
				'to': 'override' in self._dSMS and \
						self._dSMS['override'] or \
						opts['to'],
				'body': opts['content']
			}

			# If we are using a service
			if 'messaging_sid' in self._dSMS['twilio']:
				dArgs['messaging_service_sid'] = \
					self._dSMS['twilio']['messaging_sid']

			# Else, use a phone number
			else:
				dArgs['from_'] = self._dSMS['twilio']['from_number']

			# Try to send the message via Twilio
			try:
				dRes = self._oTwilio.messages.create(**dArgs)

				# Return ok
				return {
					'success': True,
					'sid': dRes.sid
				}

			# Catch any Twilio exceptions
			except TwilioRestException as e:

				# Return failure
				return {
					'success': False,
					'error': [ v for v in e.args ]
				}

	def email_create(self, req: jobject) -> Response:
		"""E-Mail

		Sends out an email to the requested email address given the correct \
		locale and template, or content

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Check for internal key
		access.internal()

		# Make sure that at minimum, we have a 'to' field
		if 'to' not in req.data:
			return Error(errors.body.DATA_FIELDS, [ [ 'to', 'missing' ] ])

		# Init the email options
		dEmail = { 'to': req.data.to.strip() }

		# If we have attachments
		if 'attachments' in req.data:

			# Add them to the email
			dEmail['attachments'] = req.data.attachments

		# If we received a template field
		if 'template' in req.data:

			# Check minimum fields
			try:
				evaluate(
					req.data.template, [ 'locale', 'variables' ]
				)
			except ValueError as e:
				return Error(
					errors.body.DATA_FIELDS,
					[ [ 'template.%s' % f, 'missing' ] for f in e.args ]
				)

			# If we have an id
			if '_id' in req.data.template:

				# Store the ID
				sID = req.data.template._id

			# Else, if we have a name
			elif 'name' in req.data.template:

				# Find the template by name
				dTemplate = Template.filter({
					'name': req.data.template.name
				}, raw = [ '_id' ], limit = 1)

				# If it's not found
				if not dTemplate:
					return Error(
						errors.body.DB_NO_RECORD,
						[ req.data.template.name, 'template' ]
					)

				# Store the ID
				sID = dTemplate['_id']

			# Else, no way to find the template
			else:
				return Error(
					errors.body.DATA_FIELDS,
					[ [ 'name', 'missing' ] ]
				)

			# Find the content by locale
			dContent = TemplateEmail.filter({
				'template': sID,
				'locale': req.data.template.locale
			}, raw = [ 'subject', 'text', 'html' ], limit = 1)
			if not dContent:
				return Error(
					errors.body.DB_NO_RECORD, [
						'%s.%s' % (
							sID, req.data.template.locale
						),
						'template'
					]
				)

			# Generate the rendered content
			dContent = self._generate_email(
				dContent,
				req.data.template.locale,
				req.data.template.variables
			)

		# Else, if we recieved content
		elif 'content' in req.data:
			dContent = req.data.content

		# Else, nothing to send
		else:
			return Error(errors.body.DATA_FIELDS, [ [ 'content', 'missing' ] ])

		# Add it to the email
		dEmail['subject'] = dContent['subject']
		dEmail['text'] = dContent['text']
		dEmail['html'] = dContent['html']

		# Send the email and return the response
		return Response(
			self._email(dEmail)
		)

	def sms_create(self, req: jobject) -> Response:
		"""SMS

		Sends out an SMS to the requested phone number given the correct \
		locale and template, or content

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Check for internal key
		access.internal()

		# Make sure that at minimum, we have a to field
		if 'to' not in req.data:
			return Error(errors.body.DATA_FIELDS, [ [ 'to', 'missing' ] ])

		# If we received a template field
		if 'template' in req.data:

			# Check minimum fields
			try:
				evaluate(
					req.data.template, [ 'locale', 'variables' ]
				)
			except ValueError as e:
				return Error(
					errors.body.DATA_FIELDS,
					[ [ 'template.%s' % f, 'missing' ] for f in e.args ]
				)

			# If we have an id
			if '_id' in req.data.template:

				# Store the ID
				sID = req.data._id

			# Else, if we have a name
			elif 'name' in req.data.template:

				# Find the template by name
				dTemplate = Template.filter({
					'name': req.data.template.name
				}, raw = [ '_id' ], limit = 1)

				# If it's not found
				if not dTemplate:
					return Error(
						errors.body.DB_NO_RECORD,
						[ req.data.template.name, 'template' ]
					)

				# Store the ID
				sID = dTemplate['_id']

			# Else, no way to find the template
			else:
				return Error(
					errors.body.DATA_FIELDS,
					[ [ 'name', 'missing' ] ]
				)

			# Find the content by locale
			dContent = TemplateSMS.filter({
				'template': sID,
				'locale': req.data.template.locale
			}, raw = [ 'content' ], limit = 1)
			if not dContent:
				return Error(
					errors.body.DB_NO_RECORD, [
						'%s.%s' % ( sID, req.data.template.locale ),
						'template'
					]
				)

			# Generate the rendered content
			sContent = self._generate_sms(
				dContent['content'],
				req.data.template.locale,
				req.data.template.variables
			)

		# Else, if we recieved content
		elif 'content' in req.data:
			sContent = req.data.content

		# Else, nothing to send
		else:
			return Error(errors.body.DATA_FIELDS, [ [ 'content', 'missing' ] ])

		# Send the sms and return the response
		return Response(
			self._sms({
				'to': req.data.to,
				'content': sContent
			})
		)

	def initialise(self):
		"""Initialise

		Initialises the instance and returns itself for chaining

		Returns:
			Authorization
		"""

		# Init the config values
		self.reset()

		# Return self for chaining
		return self

	def locale_create(self, req: jobject) -> Response:
		"""Locale create

		Creates a new locale record instance

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		access.internal_or_verify(req.session, 'mouth_locale', access.CREATE)

		# Check minimum fields
		try:
			evaluate(req.data, [ { 'record': [ 'name' ] } ])
		except ValueError as e:
			return Error(
				errors.body.DATA_FIELDS, [ [ f, 'missing' ] for f in e.args ]
			)

		# Set archived flag
		req.data.record._archived = False

		# Verify the instance
		try:
			oLocale = Locale(req.data)
		except ValueError as e:
			return Error(errors.body.DATA_FIELDS, e.args[0])

		# If it's valid data, try to add it to the DB
		try:
			oLocale.create()

		# If there's a duplicate ID or name
		except DuplicateException as e:
			return Error(
				errors.body.DB_DUPLICATE,
				[ e.args[0], 'locale.%s' % e.args[1] ]
			)

		# Return OK
		return Response(True)

	def locale_delete(self, req: jobject) -> Response:
		"""Locale delete

		Deletes (or archives) an existing locale record instance

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		access.internal_or_verify(req.session, 'mouth_locale', access.DELETE)

		# Make sure we have an ID
		if '_id' not in req.data:
			return Error(errors.body.DATA_FIELDS, [ [ '_id', 'missing' ] ])

		# Look for the instance
		oLocale = Locale.get(req.data._id)

		# If it doesn't exist
		if not oLocale:
			return Error(
				errors.body.DB_NO_RECORD,
				[ req.data._id, 'locale' ]
			)

		# If it's being archived
		if 'archive' in req.data and req.data.archive:

			# Mark the record as archived
			oLocale['_archived'] = True

			# Save it in the DB and return the result
			return Response(
				oLocale.save()
			)

		# Check for templates with the locale
		if TemplateEmail.count(filter = { 'locale': oLocale['_id'] }) or \
			TemplateSMS.count(filter = { 'locale': oLocale['_id'] }):

			# Return an error because we have existing templates still using the
			#	locale
			return Error(
				errors.body.DB_KEY_BEING_USED, ( oLocale['_id'], 'locale' )
			)

		# Delete the record and return the result
		return Response(
			oLocale.delete()
		)

	def locale_exists_read(self, req: jobject) -> Response:
		"""Locale Exists

		Returns if the requested locale exists (True) or not (False)

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# If the ID is missing
		if '_id' not in req.data:
			return Error(errors.body.DATA_FIELDS, [ [ '_id', 'missing' ] ])

		# If we got an array
		if isinstance(req.data._id, list):

			# If the list is empty
			if not req.data._id:
				return Response(False)

			# Get the IDs
			lRecords = Locale.get(req.data._id, raw = [ '_id' ])

			# Return OK if the counts match
			return Response(
				len(lRecords) == len(req.data._id)
			)

		# Return if it exists or not
		return Response(
			Locale.exists(req.data._id)
		)

	def locale_read(self, req: jobject) -> Response:
		"""Locale read

		Returns an existing locale record instance or all records

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		access.internal_or_verify(req.session, 'mouth_locale', access.READ)

		# If we have data
		if 'data' in req:

			# If there's an ID
			if '_id' in req.data:

				# Fetch the record
				dLocale = Locale.get(req.data._id, raw = True)

				# If it doesn't exist
				if not dLocale:
					return Error(
						errors.body.DB_NO_RECORD, [ req.data._id, 'locale' ]
					)

				# Return the raw data
				return Response(dLocale)

		# If we want all records
		if 'archived' in req.data and req.data.archived:
			lRecords = Locale.get(raw = True)

		# Else, filter by archived
		else:
			lRecords = Locale.filter({ '_archived': False }, raw = True)

		# If we got no records
		if not lRecords:
			return Response([])

		# Return the sorted list
		return Response(
			sorted(lRecords, key = itemgetter('name'))
		)

	def locale_update(self, req: jobject) -> Response:
		"""Locale update

		Updates an existing locale record instance

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		access.internal_or_verify(req.session, 'mouth_locale', access.UPDATE)

		# Check minimum fields
		try:
			evaluate(req.data, [ '_id', { 'record': [ 'name' ] } ])
		except ValueError as e:
			return Error(
				errors.body.DATA_FIELDS, [ [ f, 'missing' ] for f in e.args ]
			)

		# Find the record
		oLocale = Locale.get(req.data._id)

		# If it doesn't exist
		if not oLocale:
			return Error(errors.body.DB_NO_RECORD, [ req.data._id, 'locale' ])

		# If it's archived
		if oLocale['_archived']:
			return Error(errors.body.DB_ARCHIVED, [ req.data._id, 'locale' ])

		# If there's nothing to update, return False
		if not req.data.record:
			return Response(False)

		# Init possible errors
		lErrors = []

		# Remove fields that can't be changed and add them to errors
		for f in [ '_id', '_archived', '_created' ]:
			try:
				del req.data.record[f]
				lErrors.append([ f, 'update not allowed' ])
			except KeyError:
				pass

		# Go through remaining fields and attempt to update them, keeping track
		#	of any errors
		for k in req.data.record:
			try:
				oLocale[k] = req.data.record[k]
			except ValueError as e:
				lErrors.extend(e.args[0])

		# If there's any errors
		if lErrors:
			return Error(errors.body.DATA_FIELDS, lErrors)

		# Save the record and return the result
		try:
			return Response(
				oLocale.save()
			)
		except DuplicateException as e:
			return Error(
				errors.body.DB_DUPLICATE,
				[ e.args[0], 'locale.%s' % e.args[1] ]
			)

	def locales_read(self, req: jobject) -> Response:
		"""Locales read

		Returns the list of valid locales without any requirement for being
		signed in

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# If we have data, and we have archived, and it's true
		if 'data' in req and 'archived' in req.data and req.data.archived:

			# Get all records
			lRecords = Locale.get(raw = [ '_id', 'name' ])

		# Else, get just the non-archived ones
		else:
			lRecords = Locale.filter({
				'_archived': False
			}, raw = [ '_id', 'name' ])

		# If there's none
		if not lRecords:
			return Response([])

		# Sort them by name and return them
		return Response(
			sorted(lRecords, key = itemgetter('name'))
		)

	def reset(self):
		"""Reset

		Fetches the data from the config and sets up twilio client if necessary

		Returns:
			None
		"""

		# Fetch and store Email config
		self._dEmail = config.email({
			'allowed': None,
			'errors': 'webmaster@localhost',
			'from': 'support@localehost',
			'method': 'direct',
			'override': None
		})

		# Fetch and store SMS config
		self._dSMS = config.sms({
			'active': False,
			'allowed': None,
			'method': 'direct',
			'override': None,
			'twilio': {
				'account_sid': '',
				'token': '',
				'from_number': ''
			}
		})

		# If we have an existing client
		if self._oTwilio:

			# Delete it
			del self._oTwilio

		# If SMS is active
		if self._dSMS['active']:

			# Import twilio client here for lazyish loading
			from twilio.rest import Client

			# Create Twilio client
			self._oTwilio = Client(
				self._dSMS['twilio']['account_sid'],
				self._dSMS['twilio']['token']
			)

	def template_contents_read(self, req):
		"""Template Contents read

		Returns all the content records for a single template

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		access.internal_or_verify(req.session, 'mouth_content', access.READ)

		# If 'template' is missing
		if 'template' not in req.data:
			return Error(errors.body.DATA_FIELDS, [ [ 'template', 'missing' ] ])

		# If the template doesn't exist
		if not Template.exists(req.data.template):
			return Error(
				errors.body.DB_NO_RECORD, [ req.data.template, 'template' ]
			)

		# Init the list of content
		lContents = []

		# Find all associated email content
		lContents.extend([
			dict(d, type = 'email') for d in
			TemplateEmail.filter({
				'template': req.data.template
			}, raw = True)
		])

		# Find all associated sms content
		lContents.extend([
			dict(d, type = 'sms') for d in
			TemplateSMS.filter({
				'template': req.data.template
			}, raw = True)
		])

		# If there's content
		if len(lContents) > 1:

			# Sort it by locale and type
			lContents.sort(key = itemgetter('locale', 'type'))

		# Return the template
		return Response(lContents)

	def template_create(self, req: jobject) -> Response:
		"""Template create

		Creates a new template record instance

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Make sure the client has access via either an internal key, or via the
		#	session
		lAccess = access.internal_or_verify(
			req.session, 'mouth_template', access.CREATE
		)

		# Check minimum fields
		try:
			evaluate(req.data, [ { 'record': [ 'name' ] } ])
		except ValueError as e:
			return Error(
				errors.body.DATA_FIELDS, [ [ f, 'missing' ] for f in e.args ]
			)

		# Set archived flag
		req.data.record._archived = False

		# Verify the instance
		try:
			oTemplate = Template(req.data.record)
		except ValueError as e:
			return Error(errors.body.DATA_FIELDS, e.args[0])

		# Verify the instance
		try:
			oTemplate = Template(req.data)
		except ValueError as e:
			return Error(errors.body.DATA_FIELDS, e.args[0])

		# If it's valid data, try to add it to the DB
		try:
			oTemplate.create(changes = { 'user': lAccess[0] })
		except DuplicateException as e:
			return Error(
				errors.body.DB_DUPLICATE,
				[ e.args[0], 'template.%s' % e.args[1] ]
			)

		# Return the ID to indicate OK
		return Response(oTemplate['_id'])

	def template_delete(self, req: jobject) -> Response:
		"""Template delete

		Deletes an existing template record instance

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		lAccess = access.internal_or_verify(
			req.session, 'mouth_template', access.DELETE
		)

		# If the ID is missing
		if '_id' not in req.data:
			return Error(errors.body.DATA_FIELDS, [ [ '_id', 'missing' ] ])

		# Find the record
		oTemplate = Template.get(req.data._id)

		# If it's not found
		if not oTemplate:
			return Error(
				errors.body.DB_NO_RECORD, [ req.data._id, 'template' ]
			)

		# If it's being archived
		if 'archive' in req.data and req.data.archive:

			# Mark the record as archived
			oTemplate['_archived'] = True

			# Save it in the DB and return the result
			return Response(
				oTemplate.save(changes = { 'user': lAccess[0] })
			)

		# For each email template associated
		for o in TemplateEmail.filter({
			'template': req.data._id
		}):

			# Delete it
			o.delete(changes = { 'user': lAccess[0] })

		# For each sms template associated
		for o in TemplateSMS.filter({
			'template': req.data._id
		}):

			# Delete it
			o.delete(changes = { 'user': lAccess[0] })

		# Delete the template and return the result
		return Response(
			oTemplate.delete(changes = { 'user': lAccess[0] })
		)

	def template_email_create(self, req):
		"""Template Email create

		Adds an email content record to an existing template record instance

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		lAccess = access.internal_or_verify(
			req.session, 'mouth_content', access.CREATE
		)

		# Check minimum fields
		try:
			evaluate(req.data, [ { 'record': [ 'template', 'locale' ] } ])
		except ValueError as e:
			return Error(
				errors.body.DATA_FIELDS, [ [ f, 'missing' ] for f in e.args ]
			)

		# Make sure the template exists while fetching its variables
		dTemplate = Template.get(
			req.data.record.template,
			raw = [ 'variables' ]
		)
		if not dTemplate:
			return Error(
				errors.body.DB_NO_RECORD,
				[ req.data.record.template, 'template' ]
			)

		# Make sure the locale exists
		if not Locale.exists(req.data.record.locale):
			return Error(
				errors.body.DB_NO_RECORD,
				[ req.data.record.locale, 'locale' ]
			)

		# Verify the instance
		try:
			oEmail = TemplateEmail(req.data.record)
		except ValueError as e:
			return Error(errors.body.DATA_FIELDS, e.args[0])

		# Check content for errors
		lErrors = self._check_template_content(
			req.data.record,
			[ 'subject', 'text', 'html' ],
			dTemplate['variables']
		)

		# If there's any errors
		if lErrors:
			return Error(errors.TEMPLATE_CONTENT_ERROR, lErrors)

		# Create the record
		try:
			oEmail.create(changes = { 'user': lAccess[0] })
		except DuplicateException as e:
			return Error(
				errors.body.DB_DUPLICATE,
				[ req.data.record.locale, 'template_locale' ]
			)

		# Return the ID to indicate OK
		return Response(oEmail['_id'])

	def template_email_delete(self, req):
		"""Template Email delete

		Deletes email content from an existing template record instance

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		lAccess = access.internal_or_verify(
			req.session, 'mouth_content', access.DELETE
		)

		# If the ID is missing
		if '_id' not in req.data:
			return Error(errors.body.DATA_FIELDS, [ [ '_id', 'missing' ] ])

		# Find the record
		oEmail = TemplateEmail.get(req.data._id)

		# If it doesn't exist
		if not oEmail:
			return Error(
				errors.body.DB_NO_RECORD,
				[ req.data._id, 'template_email' ]
			)

		# Delete the record and return the result
		return Response(
			oEmail.delete(changes = { 'user': lAccess[0] })
		)

	def template_email_generate_create(self, req: jobject) -> Response:
		"""Template Email Generate create

		Generates a template from the base variable data for the purposes of \
		testing / validating

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		lAccess = access.internal_or_verify(
			req.session, 'mouth_content', access.READ
		)

		# Check minimum fields
		try:
			evaluate(req.data, [ 'template', 'locale', 'text', 'html' ])
		except ValueError as e:
			return Error(
				errors.body.DATA_FIELDS, [ [ f, 'missing' ] for f in e.args ]
			)

		# If the subject isn't passed
		if 'subject' not in req.data:
			req.data.subject = ''

		# Find the template variables
		dTemplate = Template.get(req.data.template, raw = [ 'variables' ])
		if not dTemplate:
			return Error(
				errors.body.DB_NO_RECORD, [ req.data.template, 'template' ]
			)

		# If the locale doesn't exist
		if not Locale.exists(req.data.locale):
			return Error(
				errors.body.DB_NO_RECORD, [ req.data.locale, 'locale' ]
			)

		# Generate the template and return it
		return Response(
			self._generate_email({
				'subject': req.data.subject,
				'text': req.data.text,
				'html': req.data.html
			}, req.data.locale, dTemplate['variables'])
		)

	def template_email_update(self, req):
		"""Template Email update

		Updated email content of an existing template record instance

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		lAccess = access.internal_or_verify(
			req.session, 'mouth_content', access.UPDATE
		)

		# Check minimum fields
		try:
			evaluate(req.data, [ '_id', 'record' ])
		except ValueError as e:
			return Error(
				errors.body.DATA_FIELDS, [ [ f, 'missing' ] for f in e.args ]
			)

		# Find the record
		oEmail = TemplateEmail.get(req.data._id)

		# If it doesn't exist
		if not oEmail:
			return Error(
				errors.body.DB_NO_RECORD, [ req.data._id, 'template_email' ]
			)

		# If there's nothing to update, return False
		if not req.data.record:
			return Response(False)

		# Init possible errors
		lErrors = []

		# Remove fields that can't be changed and add them to errors
		for f in [ '_id', '_created', '_updated', 'template' ]:
			try:
				del req.data.record[f]
				lErrors.append([ f, 'update not allowed' ])
			except KeyError:
				pass

		# Go through remaining fields and attempt to update them, keeping track
		#	of any errors
		for k in req.data.record:
			try:
				oEmail[k] = req.data.record[k]
			except ValueError as e:
				lErrors.extend(e.args[0])

		# If there's any errors
		if lErrors:
			return Error(errors.body.DATA_FIELDS, lErrors)

		# Find the primary template variables
		dTemplate = Template.get(oEmail['template'], raw = [ 'variables' ])

		# If it's not found
		if not dTemplate:
			return Error(
				errors.body.DB_NO_RECORD, [ oEmail['template'], 'template' ]
			)

		# Check content for errors
		lErrors = self._check_template_content(
			oEmail.record(),
			[ 'subject', 'text', 'html' ],
			dTemplate['variables']
		)

		# If there's any errors
		if lErrors:
			return Error(errors.TEMPLATE_CONTENT_ERROR, lErrors)

		# Save the record and return the result
		return Response(
			oEmail.save(changes = { 'user': lAccess[0] })
		)

	def template_read(self, req: jobject) -> Response:
		"""Template read

		Fetches and returns the template with the associated content records

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		access.internal_or_verify(req.session, 'mouth_template', access.READ)

		# If the ID is missing
		if '_id' not in req.data:
			return Error(errors.body.DATA_FIELDS, [ [ '_id', 'missing' ] ])

		# Find the record(s)
		mTemplate = Template.get(req.data._id, raw = True)

		# If we got a list
		if isinstance(mTemplate, list):

			# If the counts don't match
			if len(req.data._id) != len(mTemplate):
				return Error(
					errors.body.DB_NO_RECORD, [ req.data._id, 'template' ]
				)

			# Fetch all email templates with the IDs
			lEmails = TemplateEmail.filter({
				'template': req.data._id
			}, raw = True)

			# Go through each email and store it by it's template
			dEmails = {}
			for d in lEmails:
				d['type'] = 'email'
				try:
					dEmails[d['template']].append(d)
				except KeyError:
					dEmails[d['template']] = [ d ]

			# Fetch all email templates with the IDs
			lSMSs = TemplateSMS.filter({
				'template': req.data._id
			}, raw = True)

			# Go through each email and store it by it's template
			dSMSs = {}
			for d in lSMSs:
				d['type'] = 'sms'
				try:
					dSMSs[d['template']].append(d)
				except KeyError:
					dSMSs[d['template']] = [ d ]

			# Go through each template and add the emails and sms messages
			for d in mTemplate:
				d['content'] = []

				# Add the email templates
				if d['_id'] in dEmails:
					d['content'].extend(dEmails[d['_id']])

				# Add the SMS templates
				if d['_id'] in dSMSs:
					d['content'].extend(dSMSs[d['_id']])

				# If there's content
				if len(d['content']) > 1:

					# Sort it by locale and type
					d['content'].sort(key = itemgetter('locale', 'type'))

		# Else, it's most likely one
		else:

			# if it doesn't exist
			if not mTemplate:
				return Error(
					errors.body.DB_NO_RECORD, [ req.data._id, 'template' ]
				)

			# Init the list of content
			mTemplate['content'] = []

			# Find all associated email content
			mTemplate['content'].extend([
				dict(d, type = 'email') for d in
				TemplateEmail.filter({
					'template': req.data._id
				}, raw = True)
			])

			# Find all associated sms content
			mTemplate['content'].extend([
				dict(d, type='sms') for d in
				TemplateSMS.filter({
					'template': req.data._id
				}, raw = True)
			])

			# If there's content
			if len(mTemplate['content']) > 1:

				# Sort it by locale and type
				mTemplate['content'].sort(key = itemgetter('locale', 'type'))

		# Return the template
		return Response(mTemplate)

	def template_sms_create(self, req):
		"""Template SMS create

		Adds an sms content record to an existing template record instance

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		lAccess = access.internal_or_verify(
			req.session, 'mouth_content', access.CREATE
		)

		# Check minimum fields
		try: evaluate(req.data, [ { 'record': [ 'template', 'locale' ] } ])
		except ValueError as e:
			return Error(
				errors.body.DATA_FIELDS, [ [ f, 'missing' ] for f in e.args ]
			)

		# Make sure the template exists while fetching its variables
		dTemplate = Template.get(
			req.data.record.template,
			raw = [ 'variables' ]
		)
		if not dTemplate:
			return Error(
				errors.body.DB_NO_RECORD,
				[ req.data.record.template, 'template' ]
			)

		# Make sure the locale exists
		if not Locale.exists(req.data.record.locale):
			return Error(
				errors.body.DB_NO_RECORD,
				[ req.data.record.locale, 'locale' ]
			)

		# Verify the instance
		try:
			oSMS = TemplateSMS(req.data.record)
		except ValueError as e:
			return Error(errors.body.DATA_FIELDS, e.args[0])

		# Check content for errors
		lErrors = self._check_template_content(
			req.data.record,
			[ 'content' ],
			dTemplate['variables']
		)

		# If there's any errors
		if lErrors:
			return Error(errors.TEMPLATE_CONTENT_ERROR, lErrors)

		# Create the record
		try:
			oSMS.create(changes = { 'user': lAccess[0] })
		except DuplicateException as e:
			return Error(
				errors.body.DB_DUPLICATE,
				[ req.data.record.locale, 'template_locale' ]
			)

		# Return the ID to indicate OK
		return Response(oSMS['_id'])

	def template_sms_delete(self, req):
		"""Template SMS delete

		Deletes sms content from an existing template record instance

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		lAccess = access.internal_or_verify(
			req.session, 'mouth_content', access.DELETE
		)

		# If the ID is missing
		if '_id' not in req.data:
			return Error(errors.body.DATA_FIELDS, [ [ '_id', 'missing' ] ])

		# Find the record
		oSMS = TemplateSMS.get(req.data._id)

		# If it doesn't exist
		if not oSMS:
			return Error(
				errors.body.DB_NO_RECORD, [ req.data._id, 'template_sms' ]
			)

		# Delete the record and return the result
		return Response(
			oSMS.delete(changes = { 'user': lAccess[0] })
		)

	def template_sms_generate_create(self, req: jobject) -> Response:
		"""Template SMS Generate create

		Generates a template from the base variable data for the purposes of
		testing / validating

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		lAccess = access.internal_or_verify(
			req.session, 'mouth_content', access.READ
		)

		# Check minimum fields
		try: evaluate(req.data, [ 'template', 'locale', 'content' ])
		except ValueError as e:
			return Error(
				errors.body.DATA_FIELDS, [ [ f, 'missing' ] for f in e.args ]
			)

		# Find the template variables
		dTemplate = Template.get(req.data.template, raw = [ 'variables' ])
		if not dTemplate:
			return Error(
				errors.body.DB_NO_RECORD, [ req.data.template, 'template' ])

		# If the locale doesn't exist
		if not Locale.exists(req.data.locale):
			return Error(
				errors.body.DB_NO_RECORD, [ req.data.locale, 'locale' ]
			)

		# Generate the template and return it
		return Response(
			self._generate_sms(
				req.data.content,
				req.data.locale,
				dTemplate['variables']
			)
		)

	def template_sms_update(self, req):
		"""Template SMS update

		Updated sms content of an existing template record instance

		Arguments:
			req (dict): The request details, which can include 'data', \
						'environment', and 'session'

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		lAccess = access.internal_or_verify(
			req.session, 'mouth_content', access.UPDATE
		)

				# Check minimum fields
		try:
			evaluate(req.data, [ '_id', 'record' ])
		except ValueError as e:
			return Error(
				errors.body.DATA_FIELDS, [ [ f, 'missing' ] for f in e.args ]
			)

		# Find the record
		oSMS = TemplateSMS.get(req.data._id)

		# If it doesn't exist
		if not oSMS:
			return Error(
				errors.body.DB_NO_RECORD, [ req.data._id, 'template_email' ]
			)

		# If there's nothing to update, return False
		if not req.data.record:
			return Response(False)

		# Init possible errors
		lErrors = []

		# Remove fields that can't be changed and add them to errors
		for f in [ '_id', '_created', '_updated', 'template' ]:
			try:
				del req.data.record[f]
				lErrors.append([ f, 'update not allowed' ])
			except KeyError:
				pass

		# Go through remaining fields and attempt to update them, keeping track
		#	of any errors
		for k in req.data.record:
			try:
				oSMS[k] = req.data.record[k]
			except ValueError as e:
				lErrors.extend(e.args[0])

		# If there's any errors
		if lErrors:
			return Error(errors.body.DATA_FIELDS, lErrors)

		# Find the primary template variables
		dTemplate = Template.get(oSMS['template'], raw = [ 'variables' ])

		# If it's not found
		if not dTemplate:
			return Error(
				errors.body.DB_NO_RECORD, [ oSMS['template'], 'template' ]
			)

		# Check content for errors
		lErrors = self._check_template_content(
			oSMS.record(),
			[ 'content' ],
			dTemplate['variables']
		)

		# If there's any errors
		if lErrors:
			return Error(errors.TEMPLATE_CONTENT_ERROR, lErrors)

		# Save the record and return the result
		return Response(
			oSMS.save(changes = { 'user': lAccess[0] })
		)

	def template_update(self, req: jobject) -> Response:
		"""Template update

		Updates an existing template record instance

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		lAccess = access.internal_or_verify(
			req.session, 'mouth_template', access.UPDATE
		)

		# Check minimum fields
		try:
			evaluate(req.data, [ '_id', { 'record': [ 'name' ] } ])
		except ValueError as e:
			return Error(
				errors.body.DATA_FIELDS, [ [ f, 'missing' ] for f in e.args ]
			)

		# Check for ID
		if '_id' not in req.data:
			return Error(errors.body.DATA_FIELDS, [ [ '_id', 'missing' ] ])

		# Find the record
		oTemplate = Template.get(req.data._id)

		# If it doesn't exist
		if not oTemplate:
			return Error(
				errors.body.DB_NO_RECORD, [ req.data._id, 'template' ]
			)

		# If it's archived
		if oTemplate['_archived']:
			return Error(errors.body.DB_ARCHIVED, [ req.data._id, 'locale' ])

		# If there's nothing to update, return False
		if not req.data.record:
			return Response(False)

		# Init possible errors
		lErrors = []

		# Remove fields that can't be changed and add them to errors
		for f in [ '_id', '_archived', '_created', '_updated' ]:
			try:
				del req.data.record[f]
				lErrors.append([ f, 'update not allowed' ])
			except KeyError:
				pass

		# Go through remaining fields and attempt to update them, keeping track
		#	of any errors
		for k in req.data.record:
			try:
				oTemplate[k] = req.data.record[k]
			except ValueError as e:
				lErrors.extend(e.args[0])

		# If there's any errors
		if lErrors:
			return Error(errors.body.DATA_FIELDS, lErrors)

		# Save the record and return the result
		try:
			return Response(
				oTemplate.save(changes = { 'user': lAccess[0] })
			)
		except DuplicateException as e:
			return Error(
				errors.body.DB_DUPLICATE,
				[ e.args[0], 'template.%s' % e.args[1] ]
			)

	def templates_read(self, req: jobject) -> Response:
		"""Templates read

		Returns all templates in the system

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		access.verify(req.session, 'mouth_template', access.READ)

		# Fetch and return all templates
		return Response(
			Template.get(raw = True)
		)