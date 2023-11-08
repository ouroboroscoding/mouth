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
from brain import rights
from brain.helpers import access
from config import config
import em
from jobject import jobject
from strings import to_bool
from record.exceptions import RecordDuplicate
from tools import clone, evaluate
import undefined

# Python imports
from base64 import b64decode
from hashlib import md5
from operator import itemgetter
from typing import Dict

# Pip imports
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

# Mouth imports
from mouth import errors
from mouth.records.locale import Locale
from mouth.records import Template

class Mouth(Service):
	"""Mouth Service class

	Service for outgoing communication
	"""

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
			if not isinstance(opts['attachments'], (list,tuple)):
				opts['attachments'] = [opts['attachments']]

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
				{
					'from': opts['from'],
					'text': opts['text'],
					'html': opts['html'],
					'attachments': mAttachments
				}
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
		variables: str
	) -> str:
		"""Generate Content

		Handles variables and conditionals in template content as it's the \
		same logic for Emails and SMSs

		Arguments:
			content (str): The content to render
			variables (dict of str:mixed): The variable names and values

		Returns:
			str
		"""

		# Look for variables
		for sVar in cls._re_data.findall(content):

			# Replace the string with the data value
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
		for s in ['subject', 'text', 'html']:

			# If the part is somehow missing
			if s not in dContent:
				dContent[s] = '!!!%s missing!!!' % s
				continue

			# Look for embedded templates
			for sTpl in cls._re_tpl.findall(dContent[s]):

				# If we don't have the template yet
				if sTpl not in templates:

					# Look for the primary template record
					dTemplate = Template.get(
						sTpl,
						index = 'ui_name',
						raw = True
					)

					# If it doesn't exist
					if not dTemplate:
						templates[sTpl] = {
							'subject': '!!!#%s.%s#!!!' % sTpl,
							'text': '!!!#%s#!!!' % sTpl,
							'html': '!!!#%s#!!!' % sTpl
						}

					# Else, if the locale doesn't exist
					elif locale not in dTemplate['locales']:
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

					# Else
					else:

						# Make sure all the fields exists
						for s in [ 'html', 'subject', 'text']:
							if s not in dTemplate['locales'][locale]:
								dTemplate['locales'][locale][s] = \
									'!!!#%s.%s.%s#!!!' % (
										sTpl, locale, s
									)

						# Generate the email
						templates[sTpl] = cls._generate_email(
							dTemplate['locales'][locale],
							locale,
							variables,
							templates
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
		templates: Dict[str, Dict[str, str]] = undefined) -> str:
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
				dTemplate = Template.get(
					sTpl,
					index = 'ui_name',
					raw = True
				)

				# If it doesn't exist
				if not dTemplate:
					templates[sTpl] = '!!!#%s#!!!' % sTpl

				# Else, if the locale doesn't exist
				elif locale not in dTemplate['locales']:
					templates[sTpl] = '!!!#%s.%s#!!!' % ( sTpl, locale )

				# Else, if the type doesn't exist
				elif 'sms' not in dTemplate['locales'][locale]:
					templates[sTpl] = '!!!#%s.%s.sms#!!!' % ( sTpl, locale )

				# Else
				else:
					templates[sTpl] = cls._generate_sms(
						dTemplate['locales'][locale]['sms'],
						locale,
						variables,
						templates
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
					'error': [v for v in e.args]
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

		# Make sure that at minimum, we have a to field
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
					req.data.template, ['locale', 'variables']
				)
			except ValueError as e:
				return Error(
					errors.body.DATA_FIELDS,
					[ [ 'template.%s' % f, 'missing' ] for f in e.args ]
				)

			# If we have an id
			if '_id' in req.data.template:

				# Fetch the template by ID
				dTemplate = Template.get(
					req.data.template._id,
					raw = True
				)

				# If it's not found
				if not dTemplate:
					return Error(
						errors.body.DB_NO_RECORD,
						[ req.data.template._id, 'template' ]
					)

			# Else, if we have a name
			elif 'name' in req.data.template:

				# Fetch the template by name
				dTemplate = Template.get(
					req.data.template.name,
					index = 'ui_name',
					raw = True
				)

				# If it's not found
				if not dTemplate:
					return Error(
						errors.body.DB_NO_RECORD,
						[ req.data.template.name, 'template' ]
					)

			# Else, no way to find the template
			else:
				return Error(
					errors.body.DATA_FIELDS,
					[ [ 'name', 'missing' ] ]
				)

			# If we don't have the locale
			if req.data.template.locale not in dTemplate:
				return Error(
					errors.body.DB_NO_RECORD, [
						'%s.%s' % (
							dTemplate['name'], req.data.template.locale
						),
						'template'
					]
				)

			# Generate the rendered content
			dContent = self._generate_email(
				dTemplate[req.data.template.locale],
				req.data.template.locale,
				req.data.template.variables
			)

		# Else, if we recieved content
		elif 'content' in req.data:
			dContent = req.data.content

		# Else, nothing to send
		else:
			return Error(errors.body.DATA_FIELDS, [['content', 'missing']])

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
					req.data.template, ['locale', 'variables']
				)
			except ValueError as e:
				return Error(
					errors.body.DATA_FIELDS,
					[ [ 'template.%s' % f, 'missing' ] for f in e.args ]
				)

			# If we have an id
			if '_id' in req.data.template:

				# Fetch the template by ID
				dTemplate = Template.get(
					req.data.template._id,
					raw = True
				)

				# If it's not found
				if not dTemplate:
					return Error(
						errors.body.DB_NO_RECORD,
						[ req.data.template._id, 'template' ]
					)

			# Else, if we have a name
			elif 'name' in req.data.template:

				# Fetch the template by ID
				dTemplate = Template.get(
					req.data.template._id,
					index = 'ui_name',
					raw = True
				)

				# If it's not found
				if not dTemplate:
					return Error(
						errors.body.DB_NO_RECORD,
						[ req.data.template.name, 'template' ]
					)

			# Else, no way to find the template
			else:
				return Error(
					errors.body.DATA_FIELDS,
					[ [ 'name', 'missing' ] ]
				)

			# If we don't have the locale
			if req.data.template.locale not in dTemplate:
				return Error(
					errors.body.DB_NO_RECORD, [
						'%s.%s' % (
							dTemplate['name'], req.data.template.locale
						),
						'template'
					]
				)

			# Generate the rendered content
			sContent = self._generate_sms(
				dTemplate[req.data.template.locale]['sms'],
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

		# If SMS is active
		if self._dSMS['active']:

			# Create Twilio client
			self._oTwilio = Client(
				self._dSMS['twilio']['account_sid'],
				self._dSMS['twilio']['token']
			)

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
		access.verify(req.session, 'mouth_locale', rights.CREATE)

		# Verify the instance
		try:
			oLocale = Locale(req.data)
		except ValueError as e:
			return Error(errors.body.DATA_FIELDS, e.args[0])

		# If it's valid data, try to add it to the DB
		try:
			oLocale.create()
		except RecordDuplicate as e:
			return Error(errors.body.DB_DUPLICATE, 'locale')

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
		access.verify(req.session, 'mouth_locale', rights.DELETE)

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
			oLocale.update({ '_archived': True })

			# Save it in the DB and return the result
			return Response(
				oLocale.save()
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
		access.verify(req.session, 'mouth_locale', rights.READ)

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
		access.verify(req.session, 'mouth_locale', rights.UPDATE)

		# Check minimum fields
		try:
			evaluate(req.data, ['_id', 'name'])
		except ValueError as e:
			return Error(
				errors.body.DATA_FIELDS, [[f, 'missing'] for f in e.args]
			)

		# Find the record
		oLocale = Locale.get(req.data._id)

		# If it doesn't exist
		if not oLocale:
			return Error(errors.body.DB_NO_RECORD, [ req.data._id, 'locale' ])

		# If it's archived
		if oLocale['_archived']:
			return Error(errors.body.DB_ARCHIVED, [ req.data._id, 'locale' ])

		# Update the name
		oLocale.update({ 'name': req.data.name })

		# Test if the updates are valid
		if not oLocale.valid():
			return Error(errors.DATA_FIELDS, oLocale.errors)

		# Save the record and return the result
		try:
			return Response( oLocale.save() )
		except RecordDuplicate as e:
			return Error(
				errors.body.DB_DUPLICATE, [ req.data.name, 'template' ]
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
			lRecords = Locale.filte({
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
		"""Reset"""
		pass

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
		sUserID = access.internal_or_verify(
			req, 'mouth_template', rights.CREATE
		)

		# If the name is missing
		if 'name' not in req.data:
			return Error(errors.body.DATA_FIELDS, [['name', 'missing']])

		# Verify the instance
		try:
			oTemplate = Template(req.data)
		except ValueError as e:
			return Error(errors.body.DATA_FIELDS, e.args[0])

		# If it's valid data, try to add it to the DB
		try:
			oTemplate.create(changes={'user': sUserID})
		except RecordDuplicate as e:
			return Error(errors.body.DB_DUPLICATE, 'template')

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
		sUserID = access.internal_or_verify(
			req, 'mouth_template', rights.DELETE
		)

		# If the ID is missing
		if '_id' not in req.data:
			return Error(errors.body.DATA_FIELDS, [['_id', 'missing']])

		# Find the record
		oTemplate = Template.get(req.data._id)

		# If it's not found
		if not oTemplate:
			return Error(
				errors.body.DB_NO_RECORD, (req.data._id, 'template')
			)

		# For each email template associated
		for o in TemplateEmail.filter({
			'template': req.data._id
		}):

			# Delete it
			o.delete(changes={'user': sUserID})

		# For each sms template associated
		for o in TemplateSMS.filter({
			'template': req.data._id
		}):

			# Delete it
			o.delete(changes={'user': sUserID})

		# Delete the template and return the result
		return Response(
			oTemplate.delete(changes={'user': sUserID})
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
		access.internal_or_verify(req, 'mouth_template', rights.READ)

		# If the ID is missing
		if '_id' not in req.data:
			return Error(errors.body.DATA_FIELDS, [['_id', 'missing']])

		# Find the record
		dTemplate = Template.get(req.data._id, raw=True)

		# If we got a list
		if isinstance(dTemplate, list):

			# If the counts don't match
			if len(req.data._id) != len(dTemplate):
				return Error(
					errors.body.DB_NO_RECORD, [req.data._id, 'template']
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
					dEmails[d['template']] = [d]

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
					dSMSs[d['template']] = [d]

			# Go through each template and add the emails and sms messages
			for d in dTemplate:
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
					d['content'].sort(key=itemgetter('locale', 'type'))

		# Else, it's most likely one
		else:

			# if it doesn't exist
			if not dTemplate:
				return Error(
					errors.body.DB_NO_RECORD, (req.data._id, 'template')
				)

			# Init the list of content
			dTemplate['content'] = []

			# Find all associated email content
			dTemplate['content'].extend([
				dict(d, type='email') for d in
				TemplateEmail.filter({
					'template': req.data._id
				}, raw=True)
			])

			# Find all associated sms content
			dTemplate['content'].extend([
				dict(d, type='sms') for d in
				TemplateSMS.filter({
					'template': req.data._id
				}, raw=True)
			])

			# If there's content
			if len(dTemplate['content']) > 1:

				# Sort it by locale and type
				dTemplate['content'].sort(key=itemgetter('locale', 'type'))

		# Return the template
		return Response(dTemplate)

	def template_update(self, req: jobject) -> Response:
		"""Template update

		Updates an existing template record instance

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		sUserID = access.internal_or_verify(
			req, 'mouth_template', rights.UPDATE
		)

		# Check for ID
		if '_id' not in req.data:
			return Error(errors.body.DATA_FIELDS, [['_id', 'missing']])

		# Find the record
		oTemplate = Template.get(req.data._id)

		# If it doesn't exist
		if not oTemplate:
			return Error(
				errors.body.DB_NO_RECORD, (req.data._id, 'template')
			)

		# Remove fields that can't be updated
		for k in ['_id', '_created', '_updated']:
			try: del req.data[k]
			except KeyError: pass

		# If there's nothing left
		if not req.data:
			return Response(False)

		# Init errors list
		lErrors = []

		# Update remaining fields
		for k in req.data:
			try:
				oTemplate[k] = req.data[k]
			except ValueError as e:
				lErrors.extend(e.args[0])

		# Save the record and return the result
		try:
			return Response(
				oTemplate.save(changes={'user': sUserID})
			)
		except RecordDuplicate as e:
			return Error(
				errors.body.DB_DUPLICATE, (req.data['name'], 'template')
			)

	def template_contents_read(self, req: jobject) -> Response:
		"""Template Contents read

		Returns all the content records for a single template

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		access.internal_or_verify(req, 'mouth_content', rights.READ)

		# If 'template' is missing
		if 'template' not in req.data:
			return Error(errors.body.DATA_FIELDS, [['template', 'missing']])

		# If the template doesn't exist
		if not Template.exists(req.data.template):
			return Error(
				errors.body.DB_NO_RECORD, [req.data.template, 'template']
			)

		# Init the list of content
		lContents = []

		# Find all associated email content
		lContents.extend([
			dict(d, type='email') for d in
			TemplateEmail.filter({
				'template': req.data.template
			}, raw=True)
		])

		# Find all associated sms content
		lContents.extend([
			dict(d, type='sms') for d in
			TemplateSMS.filter({
				'template': req.data.template
			}, raw=True)
		])

		# If there's content
		if len(lContents) > 1:

			# Sort it by locale and type
			lContents.sort(key=itemgetter('locale', 'type'))

		# Return the template
		return Response(lContents)

	def template_email_create(self, req: jobject) -> Response:
		"""Template Email create

		Adds an email content record to an existing template record instance

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		sUserID = access.internal_or_verify(req, 'mouth_content', rights.CREATE)

		# Check minimum fields
		try:
			evaluate(req.data, ['template', 'locale'])
		except ValueError as e:
			return Error(
				errors.body.DATA_FIELDS, [[f, 'missing'] for f in e.args]
			)

		# Make sure the template exists
		dTemplate = Template.get(req.data.template, raw=['variables'])
		if not dTemplate:
			return Error(
				errors.body.DB_NO_RECORD, (req.data.template, 'template')
			)

		# Make sure the locale exists
		if not Locale.exists(req.data['locale']):
			return Error(
				errors.body.DB_NO_RECORD, (req.data['locale'], 'locale')
			)

		# Verify the instance
		try:
			oEmail = TemplateEmail(req.data)
		except ValueError as e:
			return Error(errors.body.DATA_FIELDS, e.args[0])

		# Check content for errors
		lErrors = self._checkTemplateContent(
			req.data,
			['subject', 'text', 'html'],
			dTemplate['variables']
		)

		# If there's any errors
		if lErrors:
			return Error(errors.TEMPLATE_CONTENT_ERROR, lErrors)

		# Create the record
		try:
			oEmail.create(changes={'user': sUserID})
		except RecordDuplicate as e:
			return Error(
				errors.body.DB_DUPLICATE,
				(req.data['locale'], 'template_locale')
			)

		# Return the ID to indicate OK
		return Response(oEmail['_id'])

	def template_email_delete(self, req: jobject) -> Response:
		"""Template Email delete

		Deletes email content from an existing template record instance

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		sUserID = access.internal_or_verify(req, 'mouth_content', rights.DELETE)

		# If the ID is missing
		if '_id' not in req.data:
			return Error(errors.body.DATA_FIELDS, [['_id', 'missing']])

		# Find the record
		oEmail = TemplateEmail.get(req.data._id)

		# If it doesn't exist
		if not oEmail:
			return Error(
				errors.body.DB_NO_RECORD,
				(req.data._id, 'template_email')
			)

		# Delete the record and return the result
		return Response(
			oEmail.delete(changes={'user': sUserID})
		)

	def template_email_update(self, req: jobject) -> Response:
		"""Template Email update

		Updated email content of an existing template record instance

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		sUserID = access.internal_or_verify(req, 'mouth_content', rights.UPDATE)

		# If the ID is missing
		if '_id' not in req.data:
			return Error(errors.body.DATA_FIELDS, [['_id', 'missing']])

		# Find the record
		oEmail = TemplateEmail.get(req.data._id)

		# If it doesn't exist
		if not oEmail:
			return Error(
				errors.body.DB_NO_RECORD, (req.data._id, 'template_email')
			)

		# Remove fields that can't be updated
		for k in ['_id', '_created', '_updated', 'template', 'locale']:
			try: del req.data[k]
			except KeyError: pass

		# If there's nothing left
		if not req.data:
			return Response(False)

		# Init errors list
		lErrors = []

		# Update remaining fields
		for k in req.data:
			try:
				oEmail[k] = req.data[k]
			except ValueError as e:
				lErrors.extend(e.args[0])

		# If there's any errors
		if lErrors:
			return Error(errors.body.DATA_FIELDS, lErrors)

		# Find the primary template variables
		dTemplate = Template.get(oEmail['template'], raw=['variables'])

		# Check content for errors
		lErrors = self._checkTemplateContent(
			req.data,
			['subject', 'text', 'html'],
			dTemplate['variables']
		)

		# If there's any errors
		if lErrors:
			return Error(errors.TEMPLATE_CONTENT_ERROR, lErrors)

		# Save the record and return the result
		return Response(
			oEmail.save(changes={'user': sUserID})
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
		sUserID = access.internal_or_verify(req, 'mouth_content', rights.READ)

		# Check minimum fields
		try:
			evaluate(req.data, ['template', 'locale', 'text', 'html'])
		except ValueError as e:
			return Error(
				errors.body.DATA_FIELDS, [[f, 'missing'] for f in e.args]
			)

		# If the subject isn't passed
		if 'subject' not in req.data:
			req.data['subject'] = ''

		# Find the template variables
		dTemplate = Template.get(req.data.template, raw=['variables'])
		if not dTemplate:
			return Error(
				errors.body.DB_NO_RECORD, (req.data.template, 'template')
			)

		# If the locale doesn't exist
		if not Locale.exists(req.data['locale']):
			return Error(
				errors.body.DB_NO_RECORD, (req.data['locale'], 'locale')
			)

		# Generate the template and return it
		return Response(
			self._generate_email({
				'subject': req.data['subject'],
				'text': req.data['text'],
				'html': req.data['html']
			}, req.data['locale'], dTemplate['variables'])
		)

	def template_sms_create(self, req: jobject) -> Response:
		"""Template SMS create

		Adds an sms content record to an existing template record instance

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		sUserID = access.internal_or_verify(req, 'mouth_content', rights.CREATE)

		# Check minimum fields
		try: evaluate(req.data, ['template', 'locale'])
		except ValueError as e:
			return Error(
				errors.body.DATA_FIELDS, [[f, 'missing'] for f in e.args]
			)

		# Make sure the template exists
		dTemplate = Template.get(req.data.template, raw=['variables'])
		if not dTemplate:
			return Error(
				errors.body.DB_NO_RECORD, (req.data.template, 'template')
			)

		# Make sure the locale exists
		if not Locale.exists(req.data['locale']):
			return Error(
				errors.body.DB_NO_RECORD, (req.data['locale'], 'locale')
			)

		# Verify the instance
		try:
			oSMS = TemplateSMS(req.data)
		except ValueError as e:
			return Error(errors.body.DATA_FIELDS, e.args[0])

		# Check content for errors
		lErrors = self._checkTemplateContent(
			req.data,
			['content'],
			dTemplate['variables']
		)

		# If there's any errors
		if lErrors:
			return Error(errors.TEMPLATE_CONTENT_ERROR, lErrors)

		# Create the record
		try:
			oSMS.create(changes={'user': sUserID})
		except RecordDuplicate as e:
			return Error(
				errors.body.DB_DUPLICATE,
				(req.data['locale'], 'template_locale')
			)

		# Return the ID to indicate OK
		return Response(oSMS['_id'])

	def template_sms_delete(self, req: jobject) -> Response:
		"""Template SMS delete

		Deletes sms content from an existing template record instance

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		sUserID = access.internal_or_verify(req, 'mouth_content', rights.DELETE)

		# If the ID is missing
		if '_id' not in req.data:
			return Error(errors.body.DATA_FIELDS, [['_id', 'missing']])

		# Find the record
		oSMS = TemplateSMS.get(req.data._id)

		# If it doesn't exist
		if not oSMS:
			return Error(
				errors.body.DB_NO_RECORD, (req.data._id, 'template_sms')
			)

		# Delete the record and return the result
		return Response(
			oSMS.delete(changes={'user': sUserID})
		)

	def template_sms_update(self, req: jobject) -> Response:
		"""Template SMS update

		Updated sms content of an existing template record instance

		Arguments:
			req (jobject): Contains data and session if available

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		sUserID = access.internal_or_verify(req, 'mouth_content', rights.UPDATE)

		# Check minimum fields
		try: evaluate(req.data, ['_id', 'content'])
		except ValueError as e:
			return Error(
				errors.body.DATA_FIELDS, [[f, 'missing'] for f in e.args]
			)

		# Find the record
		oSMS = TemplateSMS.get(req.data._id)

		# If it doesn't exist
		if not oSMS:
			return Error(
				errors.body.DB_NO_RECORD, (req.data._id, 'template_sms')
			)

		# Update the content
		try:
			oSMS['content'] = req.data['content']
		except ValueError as e:
			return Error(errors.body.DATA_FIELDS, [e.args[0]])

		# Find the primary template variables
		dTemplate = Template.get(oSMS['template'], raw=['variables'])

		# Check content for errors
		lErrors = self._checkTemplateContent(
			req.data,
			['content'],
			dTemplate['variables']
		)

		# If there's any errors
		if lErrors:
			return Error(errors.TEMPLATE_CONTENT_ERROR, lErrors)

		# Save the record and return the result
		return Response(
			oSMS.save(changes={'user': sUserID})
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
		sUserID = access.internal_or_verify(req, 'mouth_content', rights.READ)

		# Check minimum fields
		try: evaluate(req.data, ['template', 'locale', 'content'])
		except ValueError as e:
			return Error(
				errors.body.DATA_FIELDS, [[f, 'missing'] for f in e.args]
			)

		# Find the template variables
		dTemplate = Template.get(req.data.template, raw=['variables'])
		if not dTemplate:
			return Error(errors.body.DB_NO_RECORD, (req.data.template, 'template'))

		# If the locale doesn't exist
		if not Locale.exists(req.data['locale']):
			return Error(
				errors.body.DB_NO_RECORD, (req.data['locale'], 'locale')
			)

		# Generate the template and return it
		return Response(
			self._generate_sms(
				req.data['content'],
				req.data['locale'],
				dTemplate['variables']
			)
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
		access.verify(req.session, 'mouth_template', rights.READ)

		# Fetch and return all templates
		return Response(
			Template.get(raw=True, orderby='name')
		)