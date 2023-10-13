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

# Python imports
from base64 import b64decode
from hashlib import md5
from operator import itemgetter
import re

# Pip imports
from brain import access
from RestOC import Conf, DictHelper, Record_Base, SMTP, StrHelper
from RestOC.Services import Error, Response, Service
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

# Records imports
from mouth.records import Locale, Template, TemplateEmail, TemplateSMS

# Errors
from mouth import errors

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
	def _checkTemplateContent(cls, content, names, variables):
		"""Check Template Content

		Goes through template content and makes sure any variables or embedded \
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
			lTemplates = [d['name'] for d in Template.filter({
				'name': list(lsTemplates)
			}, raw=['name'])]

			# If the count doesn't match
			if len(lTemplates) != len(lsTemplates):

				# Get the missing templates
				for s in lsTemplates:
					if s not in lTemplates:
						lErrors.append(['template', s])

		# If there's any variables
		if lsVariables:

			# Go through each one
			for s in lsVariables:

				# If it's not in the templates list
				if s not in variables:
					lErrors.append(['variable', s])

		# Return errors (might be empty)
		return lErrors

	def _email(self, opts):
		"""Email

		Handles the actual sending of the email

		Arguments:
			opts (dict): The options used to generate and send the email

		Returns:
			Response
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
					return Error(
						errors.ATTACHMENT_STRUCTURE, 'attachments.[%d]' % i
					)

				# If the fields are missing
				try:
					DictHelper.eval(
						opts['attachments'][i], ['body', 'filename']
					)
				except ValueError as e:
					return Error(
						errors.body.DATA_FIELDS,
						[['attachments.[%d].%s' % (i, s), 'invalid'] \
							for s in e.args]
					)

				# Try to decode the base64
				try:
					opts['attachments'][i]['body'] = b64decode(
						opts['attachments'][i]['body']
					)
				except TypeError:
					return Response(errors.ATTACHMENT_DECODE)

			# Set the attachments from the opts
			mAttachments = opts['attachments']

		# Only send if anyone is allowed, or the to is in the allowed
		if not self._dEmail['allowed'] or opts['to'] in self._dEmail['allowed']:

			# Send the e-mail
			iRes = SMTP.send(
				'override' in self._dEmail and \
					self._dEmail['override'] or \
					opts['to'],
				subject=opts['subject'],
				text_body=opts['text'],
				html_body=opts['html'],
				from_=opts['from'],
				attachments=mAttachments
			)

			# If there was an error
			if iRes != SMTP.OK:
				return {
					'success': False,
					'error': '%i %s' % (iRes, SMTP.last_error())
				}

		# Return OK
		return {'success': True}

	@classmethod
	def _generate_content(cls, content, variables):
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
					'!!!{%s} does not exist!!!' % sVar
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
							mValue = StrHelper.to_bool(mValue)

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
	def _generate_email(cls, content, locale, variables, templates=None):
		"""Generate Email

		Takes content, locale, and variables, and renders the final result of \
		the three parts of the email template

		Arguments:
			content (dict of str:str): The content to be rendered, 'subject', \
										'text', and 'html'
			locale (str): The locale used for embedded templates
			variables (dict of str:str): The variable names and their values
			templates (dict of str:str): The templates already looked up

		Returns:
			dict of str:str
		"""

		# If there's no templates yet
		if not templates:
			templates = {}

		# Copy the contents
		dContent = DictHelper.clone(content)

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

					# Look for the primary template
					dTemplate = Template.filter({
						'name': sTpl
					}, raw=['_id'], limit=1)

					# If it doesn't exist
					if not dTemplate:
						templates[sTpl] = {
							'subject': '!!!#%s# does not exist!!!' % sTpl,
							'text': '!!!#%s# does not exist!!!' % sTpl,
							'html': '!!!#%s# does not exist!!!' % sTpl
						}

					# Else
					else:

						# Look for the locale dContent
						dEmail = TemplateEmail.filter({
							'template': dTemplate['_id'],
							'locale': locale
						}, raw=['subject', 'text', 'html'], limit=1)

						# If it doesn't exist
						if not dEmail:
							templates[sTpl] = {
								'subject': '!!!#%s.%s# does not exist!!!' % (
									sTpl, locale
								),
								'text': '!!!#%s.%s# does not exist!!!' % (
									sTpl, locale
								),
								'html': '!!!#%s.%s# does not exist!!!' % (
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
	def _generate_sms(cls, content, locale, variables, templates=None):
		"""Generate SMS

		Takes content, locale, and variables, and renders the final result of \
		the template

		Arguments:
			content (str): The content to be rendered
			locale (str): The locale used for embedded templates
			variables (dict of str:str): The variable names and their values
			templates (dict of str:str): The templates already looked up

		Returns:
			str
		"""

		# If there's no templates yet
		if not templates:
			templates = {}

		# Look for embedded templates
		for sTpl in cls._re_tpl.findall(content):

			# If we don't have the template yet
			if sTpl not in templates:

				# Look for the primary template
				dTemplate = Template.filter({
					'name': sTpl
				}, raw=['_id'], limit=1)

				# If it doesn't exist
				if not dTemplate:
					templates[sTpl] = '!!!#%s# does not exist!!!' % sTpl

				# Else
				else:

					# Look for the locale dContent
					dSMS = TemplateSMS.filter({
						'template': dTemplate['_id'],
						'locale': locale
					}, raw=['content'], limit=1)

					# If it doesn't exist
					if not dSMS:
						templates[sTpl] = '!!!#%s.%s# does not exist!!!' % (
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

	def _queue_key(self, data, key=None):
		"""Queue Key

		If the key is not passed we are generating it, else we are validating it

		Arguments:
			data (dict): The data that was passed or retrieved
			key (str): The key to validate if passed

		Returns:
			str|bool
		"""

		# Turn the data into a str and md5 it
		sMD5 = md5(str(data).encode('utf-8')).hexdigest()

		# If a key was received
		if key:

			# Decode it and see if it matches the data
			return StrHelper.decrypt(self._queue_key, key) == sMD5

		# Else
		else:

			# Generate and return a key
			return StrHelper.encrypt(self._queue_key, sMD5)

	def _sms(self, opts):
		"""SMS

		Sends an SMS using twilio

		Arguments:
			opts (dict): The options used to generate and send the SMS

		Returns:
			Response
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

	def email_create(self, req):
		"""E-Mail

		Sends out an email to the requested email address given the correct \
		locale and template, or content

		Arguments:
			req (dict): The request details, which can include 'data', \
						'environment', and 'session'

		Returns:
			Response
		"""

		# Check for internal key
		access.internal(req['data'])

		# Make sure that at minimum, we have a to field
		if 'to' not in req['data']:
			return Error(errors.body.DATA_FIELDS, [['to', 'missing']])

		# Init the email options
		dEmail = {
			'to': req['data']['to'].strip()
		}

		# If we have attachments
		if 'attachments' in req['data']:

			# Add them to the email
			dEmail['attachments'] = req['data']['attachments']

		# If we received a template field
		if 'template' in req['data']:

			# Check minimum fields
			try:
				DictHelper.eval(
					req['data']['template'], ['locale', 'variables']
				)
			except ValueError as e:
				return Error(
					errors.body.DATA_FIELDS,
					[['template.%s' % f, 'missing'] for f in e.args]
				)

			# If we have an id
			if '_id' in req['data']['template']:

				# Store the ID
				sID = req['data']['template']['_id']

			# Else, if we have a name
			elif 'name' in req['data']['template']:

				# Find the template by name
				dTemplate = Template.filter({
					'name': req['data']['template']['name']
				}, raw=['_id'], limit=1)

				# If it's not found
				if not dTemplate:
					return Error(
						errors.body.DB_NO_RECORD,
						[req['data']['template']['name'], 'template']
					)

				# Store the ID
				sID = dTemplate['_id']

			# Else, no way to find the template
			else:
				return Error(
					errors.body.DATA_FIELDS,
					[['name', 'missing']]
				)

			# Find the content by locale
			dContent = TemplateEmail.filter({
				'template': sID,
				'locale': req['data']['template']['locale']
			}, raw=['subject', 'text', 'html'], limit=1)
			if not dContent:
				return Error(
					errors.body.DB_NO_RECORD, [
						'%s.%s' % (
							sID, req['data']['template']['locale']
						),
						'template'
					]
				)

			# Generate the rendered content
			dContent = self._generate_email(
				dContent,
				req['data']['template']['locale'],
				req['data']['template']['variables']
			)

		# Else, if we recieved content
		elif 'content' in req['data']:
			dContent = req['data']['content']

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

	def sms_create(self, req):
		"""SMS

		Sends out an SMS to the requested phone number given the correct \
		locale and template, or content

		Arguments:
			req (dict): The request details, which can include 'data', \
						'environment', and 'session'

		Returns:
			Response
		"""

		# Check for internal key
		access.internal(req['data'])

		# Make sure that at minimum, we have a to field
		if 'to' not in req['data']:
			return Error(errors.body.DATA_FIELDS, [['to', 'missing']])

		# If we received a template field
		if 'template' in req['data']:

			# Check minimum fields
			try:
				DictHelper.eval(
					req['data']['template'], ['locale', 'variables']
				)
			except ValueError as e:
				return Error(
					errors.body.DATA_FIELDS,
					[['template.%s' % f, 'missing'] for f in e.args]
				)

			# If we have an id
			if '_id' in req['data']['template']:

				# Store the ID
				sID = req['data']['_id']

			# Else, if we have a name
			elif 'name' in req['data']['template']:

				# Find the template by name
				dTemplate = Template.filter({
					'name': req['data']['template']['name']
				}, raw=['_id'], limit=1)

				# If it's not found
				if not dTemplate:
					return Error(
						errors.body.DB_NO_RECORD,
						[req['data']['template']['name'], 'template']
					)

				# Store the ID
				sID = dTemplate['_id']

			# Else, no way to find the template
			else:
				return Error(
					errors.body.DATA_FIELDS,
					[['name', 'missing']]
				)

			# Find the content by locale
			dContent = TemplateSMS.filter({
				'template': sID,
				'locale': req['data']['template']['locale']
			}, raw=['content'], limit=1)
			if not dContent:
				return Error(
					errors.body.DB_NO_RECORD, [
						'%s.%s' % (
							sID, req['data']['template']['locale']
						),
						'template'
					]
				)

			# Generate the rendered content
			sContent = self._generate_sms(
				dContent['content'],
				req['data']['template']['locale'],
				req['data']['template']['variables']
			)

		# Else, if we recieved content
		elif 'content' in req['data']:
			sContent = req['data']['content']

		# Else, nothing to send
		else:
			return Error(errors.body.DATA_FIELDS, [['content', 'missing']])

		# Send the sms and return the response
		return Response(
			self._sms({
				'to': req['data']['to'],
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
		dDefault = {
			'allowed': None,
			'errors': 'webmaster@localhost',
			'from': 'support@localehost',
			'method': 'direct',
			'override': None
		}
		self._dEmail = Conf.get('email', dDefault)
		for k in dDefault.keys():
			if k not in self._dEmail:
				self._dEmail[k] = dDefault[k]

		# Fetch and store SMS config
		dDefault = {
			'active': False,
			'allowed': None,
			'method': 'direct',
			'override': None,
			'twilio': {
				'account_sid': '',
				'token': '',
				'from_number': ''
			}
		}
		self._dSMS = Conf.get('sms', dDefault)
		for k in dDefault.keys():
			if k not in self._dSMS:
				self._dSMS[k] = dDefault[k]

		# If SMS is active
		if self._dSMS['active']:

			# Create Twilio client
			self._oTwilio = Client(
				self._dSMS['twilio']['account_sid'],
				self._dSMS['twilio']['token']
			)

		# Return self for chaining
		return self

	def locale_create(self, req):
		"""Locale create

		Creates a new locale record instance

		Arguments:
			req (dict): The request details, which can include 'data', \
						'environment', and 'session'

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		access.verify(req['session'], 'mouth_locale', access.CREATE)

		# Verify the instance
		try:
			oLocale = Locale(req['data'])
		except ValueError as e:
			return Error(errors.body.DATA_FIELDS, e.args[0])

		# If it's valid data, try to add it to the DB
		try:
			oLocale.create()
		except Record_Base.DuplicateException as e:
			return Error(errors.body.DB_DUPLICATE, 'locale')

		# Return OK
		return Response(True)

	def locale_delete(self, req):
		"""Locale delete

		Deletes (or archives) an existing locale record instance

		Arguments:
			req (dict): The request details, which can include 'data', \
						'environment', and 'session'

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		access.verify(req['session'], 'mouth_locale', access.DELETE)

		# Make sure we have an ID
		if '_id' not in req['data']:
			return Error(errors.body.DATA_FIELDS, [['_id', 'missing']])

		# Look for the instance
		oLocale = Locale.get(req['data']['_id'])

		# If it doesn't exist
		if not oLocale:
			return Error(
				errors.body.DB_NO_RECORD,
				(req['data']['_id'], 'locale')
			)

		# If it's being archived
		if 'archive' in req['data'] and req['data']['archive']:

			# Mark the record as archived
			oLocale['_archived'] = True

			# Save it in the DB and return the result
			return Response(
				oLocale.save()
			)

		# Check for templates with the locale
		if TemplateEmail.count(filter={'locale': oLocale['_id']}) or \
			TemplateSMS.count(filter={'locale': oLocale['_id']}):

			# Return an error because we have existing templates still using the
			#	locale
			return Error(
				errors.body.DB_KEY_BEING_USED, (oLocale['_id'], 'locale')
			)

		# Delete the record and return the result
		return Response(
			oLocale.delete()
		)

	def locale_exists_read(self, req):
		"""Locale Exists

		Returns if the requested locale exists (True) or not (False)

		Arguments:
			req (dict): The request details, which can include 'data', \
						'environment', and 'session'

		Returns:
			Response
		"""

		# If the ID is missing
		if '_id' not in req['data']:
			return Error(errors.body.DATA_FIELDS, [['_id', 'missing']])

		# Return if it exists or not
		return Response(
			Locale.exists(req['data']['_id'])
		)

	def locale_read(self, req):
		"""Locale read

		Returns an existing locale record instance or all records

		Arguments:
			req (dict): The request details, which can include 'data', \
						'environment', and 'session'

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		access.verify(req['session'], 'mouth_locale', access.READ)

		# If we have data
		if 'data' in req:

			# If there's an ID
			if '_id' in req['data']:

				# Fetch the record
				dLocale = Locale.get(req['data']['_id'], raw=True)

				# If it doesn't exist
				if not dLocale:
					return Error(
						errors.body.DB_NO_RECORD, (req['data']['_id'], 'locale')
					)

				# Return the raw data
				return Response(dLocale)

		# If we want to include archived
		if 'archived' in req['data'] and req['data']['archived']:

			# Get and return all locales as raw data
			return Response(
				Locale.get(raw=True, orderby='name')
			)

		# Else, return only those not marked as archived
		return Response(
			Locale.get(filter={'_archived': False}, raw=True, orderby='name')
		)

	def locale_update(self, req):
		"""Locale update

		Updates an existing locale record instance

		Arguments:
			req (dict): The request details, which can include 'data', \
						'environment', and 'session'

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		access.verify(req['session'], 'mouth_locale', access.UPDATE)

		# Check minimum fields
		try:
			DictHelper.eval(req['data'], ['_id', 'name'])
		except ValueError as e:
			return Error(
				errors.body.DATA_FIELDS, [[f, 'missing'] for f in e.args]
			)

		# Find the record
		oLocale = Locale.get(req['data']['_id'])

		# If it doesn't exist
		if not oLocale:
			return Error(errors.body.DB_NO_RECORD, (req['data']['_id'], 'locale'))

		# If it's archived
		if oLocale['_archived']:
			return Error(errors.body.DB_ARCHIVED, (req['data']['_id'], 'locale'))

		# Try to update the name
		try:
			oLocale['name'] = req['data']['name']
		except ValueError as e:
			return Error(errors.body.DATA_FIELDS, [e.args[0]])

		# Save the record and return the result
		try:
			return Response(
				oLocale.save()
			)
		except Record_Base.DuplicateException as e:
			return Error(errors.body.DB_DUPLICATE, (req['data']['name'], 'template'))

	def locales_read(self, req):
		"""Locales read

		Returns the list of valid locales without any requirement for being
		signed in

		Arguments:
			req (dict): The request details, which can include 'data', \
						'environment', and 'session'

		Returns:
			Response
		"""

		# If we have data, and we have archived, and it's true
		bArchived = 'data' in req and \
					'archived' in req['data'] and \
					req['data']['archived']

		# If we want to include archived data or not
		filter = not bArchived and {'_archived': False} or None

		# Get and return all locales as raw data
		return Response(
			Locale.get(
				filter=filter,
				raw=['_id', 'name'],
				orderby='name'
			)
		)

	def template_create(self, req):
		"""Template create

		Creates a new template record instance

		Arguments:
			req (dict): The request details, which can include 'data', \
						'environment', and 'session'

		Returns:
			Response
		"""

		# Make sure the client has access via either an internal key, or via the
		#	session
		sUserID = access.internal_or_verify(
			req, 'mouth_template', access.CREATE
		)

		# If the name is missing
		if 'name' not in req['data']:
			return Error(errors.body.DATA_FIELDS, [['name', 'missing']])

		# Verify the instance
		try:
			oTemplate = Template(req['data'])
		except ValueError as e:
			return Error(errors.body.DATA_FIELDS, e.args[0])

		# If it's valid data, try to add it to the DB
		try:
			oTemplate.create(changes={'user': sUserID})
		except Record_Base.DuplicateException as e:
			return Error(errors.body.DB_DUPLICATE, 'template')

		# Return the ID to indicate OK
		return Response(oTemplate['_id'])

	def template_delete(self, req):
		"""Template delete

		Deletes an existing template record instance

		Arguments:
			req (dict): The request details, which can include 'data', \
						'environment', and 'session'

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		sUserID = access.internal_or_verify(
			req, 'mouth_template', access.DELETE
		)

		# If the ID is missing
		if '_id' not in req['data']:
			return Error(errors.body.DATA_FIELDS, [['_id', 'missing']])

		# Find the record
		oTemplate = Template.get(req['data']['_id'])

		# If it's not found
		if not oTemplate:
			return Error(
				errors.body.DB_NO_RECORD, (req['data']['_id'], 'template')
			)

		# For each email template associated
		for o in TemplateEmail.filter({
			'template': req['data']['_id']
		}):

			# Delete it
			o.delete(changes={'user': sUserID})

		# For each sms template associated
		for o in TemplateSMS.filter({
			'template': req['data']['_id']
		}):

			# Delete it
			o.delete(changes={'user': sUserID})

		# Delete the template and return the result
		return Response(
			oTemplate.delete(changes={'user': sUserID})
		)

	def template_read(self, req):
		"""Template read

		Fetches and returns the template with the associated content records

		Arguments:
			req (dict): The request details, which can include 'data', \
						'environment', and 'session'

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		access.internal_or_verify(req, 'mouth_template', access.READ)

		# If the ID is missing
		if '_id' not in req['data']:
			return Error(errors.body.DATA_FIELDS, [['_id', 'missing']])

		# Find the record
		dTemplate = Template.get(req['data']['_id'], raw=True)

		# If we got a list
		if isinstance(dTemplate, list):

			# If the counts don't match
			if len(req['data']['_id']) != len(dTemplate):
				return Error(
					errors.body.DB_NO_RECORD, [req['data']['_id'], 'template']
				)

			# Fetch all email templates with the IDs
			lEmails = TemplateEmail.filter({
				'template': req['data']['_id']
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
				'template': req['data']['_id']
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
					errors.body.DB_NO_RECORD, (req['data']['_id'], 'template')
				)

			# Init the list of content
			dTemplate['content'] = []

			# Find all associated email content
			dTemplate['content'].extend([
				dict(d, type='email') for d in
				TemplateEmail.filter({
					'template': req['data']['_id']
				}, raw=True)
			])

			# Find all associated sms content
			dTemplate['content'].extend([
				dict(d, type='sms') for d in
				TemplateSMS.filter({
					'template': req['data']['_id']
				}, raw=True)
			])

			# If there's content
			if len(dTemplate['content']) > 1:

				# Sort it by locale and type
				dTemplate['content'].sort(key=itemgetter('locale', 'type'))

		# Return the template
		return Response(dTemplate)

	def template_update(self, req):
		"""Template update

		Updates an existing template record instance

		Arguments:
			req (dict): The request details, which can include 'data', \
						'environment', and 'session'

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		sUserID = access.internal_or_verify(
			req, 'mouth_template', access.UPDATE
		)

		# Check for ID
		if '_id' not in req['data']:
			return Error(errors.body.DATA_FIELDS, [['_id', 'missing']])

		# Find the record
		oTemplate = Template.get(req['data']['_id'])

		# If it doesn't exist
		if not oTemplate:
			return Error(
				errors.body.DB_NO_RECORD, (req['data']['_id'], 'template')
			)

		# Remove fields that can't be updated
		for k in ['_id', '_created', '_updated']:
			try: del req['data'][k]
			except KeyError: pass

		# If there's nothing left
		if not req['data']:
			return Response(False)

		# Init errors list
		lErrors = []

		# Update remaining fields
		for k in req['data']:
			try:
				oTemplate[k] = req['data'][k]
			except ValueError as e:
				lErrors.extend(e.args[0])

		# Save the record and return the result
		try:
			return Response(
				oTemplate.save(changes={'user': sUserID})
			)
		except Record_Base.DuplicateException as e:
			return Error(
				errors.body.DB_DUPLICATE, (req['data']['name'], 'template')
			)

	def template_contents_read(self, req):
		"""Template Contents read

		Returns all the content records for a single template

		Arguments:
			req (dict): The request details, which can include 'data', \
						'environment', and 'session'

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		access.internal_or_verify(req, 'mouth_content', access.READ)

		# If 'template' is missing
		if 'template' not in req['data']:
			return Error(errors.body.DATA_FIELDS, [['template', 'missing']])

		# If the template doesn't exist
		if not Template.exists(req['data']['template']):
			return Error(
				errors.body.DB_NO_RECORD, [req['data']['template'], 'template']
			)

		# Init the list of content
		lContents = []

		# Find all associated email content
		lContents.extend([
			dict(d, type='email') for d in
			TemplateEmail.filter({
				'template': req['data']['template']
			}, raw=True)
		])

		# Find all associated sms content
		lContents.extend([
			dict(d, type='sms') for d in
			TemplateSMS.filter({
				'template': req['data']['template']
			}, raw=True)
		])

		# If there's content
		if len(lContents) > 1:

			# Sort it by locale and type
			lContents.sort(key=itemgetter('locale', 'type'))

		# Return the template
		return Response(lContents)

	def template_email_create(self, req):
		"""Template Email create

		Adds an email content record to an existing template record instance

		Arguments:
			req (dict): The request details, which can include 'data', \
						'environment', and 'session'

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		sUserID = access.internal_or_verify(req, 'mouth_content', access.CREATE)

		# Check minimum fields
		try:
			DictHelper.eval(req['data'], ['template', 'locale'])
		except ValueError as e:
			return Error(
				errors.body.DATA_FIELDS, [[f, 'missing'] for f in e.args]
			)

		# Make sure the template exists
		dTemplate = Template.get(req['data']['template'], raw=['variables'])
		if not dTemplate:
			return Error(
				errors.body.DB_NO_RECORD, (req['data']['template'], 'template')
			)

		# Make sure the locale exists
		if not Locale.exists(req['data']['locale']):
			return Error(
				errors.body.DB_NO_RECORD, (req['data']['locale'], 'locale')
			)

		# Verify the instance
		try:
			oEmail = TemplateEmail(req['data'])
		except ValueError as e:
			return Error(errors.body.DATA_FIELDS, e.args[0])

		# Check content for errors
		lErrors = self._checkTemplateContent(
			req['data'],
			['subject', 'text', 'html'],
			dTemplate['variables']
		)

		# If there's any errors
		if lErrors:
			return Error(errors.TEMPLATE_CONTENT_ERROR, lErrors)

		# Create the record
		try:
			oEmail.create(changes={'user': sUserID})
		except Record_Base.DuplicateException as e:
			return Error(
				errors.body.DB_DUPLICATE,
				(req['data']['locale'], 'template_locale')
			)

		# Return the ID to indicate OK
		return Response(oEmail['_id'])

	def template_email_delete(self, req):
		"""Template Email delete

		Deletes email content from an existing template record instance

		Arguments:
			req (dict): The request details, which can include 'data', \
						'environment', and 'session'

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		sUserID = access.internal_or_verify(req, 'mouth_content', access.DELETE)

		# If the ID is missing
		if '_id' not in req['data']:
			return Error(errors.body.DATA_FIELDS, [['_id', 'missing']])

		# Find the record
		oEmail = TemplateEmail.get(req['data']['_id'])

		# If it doesn't exist
		if not oEmail:
			return Error(
				errors.body.DB_NO_RECORD,
				(req['data']['_id'], 'template_email')
			)

		# Delete the record and return the result
		return Response(
			oEmail.delete(changes={'user': sUserID})
		)

	def template_email_update(self, req):
		"""Template Email update

		Updated email content of an existing template record instance

		Arguments:
			req (dict): The request details, which can include 'data', \
						'environment', and 'session'

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		sUserID = access.internal_or_verify(req, 'mouth_content', access.UPDATE)

		# If the ID is missing
		if '_id' not in req['data']:
			return Error(errors.body.DATA_FIELDS, [['_id', 'missing']])

		# Find the record
		oEmail = TemplateEmail.get(req['data']['_id'])

		# If it doesn't exist
		if not oEmail:
			return Error(
				errors.body.DB_NO_RECORD, (req['data']['_id'], 'template_email')
			)

		# Remove fields that can't be updated
		for k in ['_id', '_created', '_updated', 'template', 'locale']:
			try: del req['data'][k]
			except KeyError: pass

		# If there's nothing left
		if not req['data']:
			return Response(False)

		# Init errors list
		lErrors = []

		# Update remaining fields
		for k in req['data']:
			try:
				oEmail[k] = req['data'][k]
			except ValueError as e:
				lErrors.extend(e.args[0])

		# If there's any errors
		if lErrors:
			return Error(errors.body.DATA_FIELDS, lErrors)

		# Find the primary template variables
		dTemplate = Template.get(oEmail['template'], raw=['variables'])

		# Check content for errors
		lErrors = self._checkTemplateContent(
			req['data'],
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

	def template_email_generate_create(self, req):
		"""Template Email Generate create

		Generates a template from the base variable data for the purposes of \
		testing / validating

		Arguments:
			req (dict): The request details, which can include 'data', \
						'environment', and 'session'

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		sUserID = access.internal_or_verify(req, 'mouth_content', access.READ)

		# Check minimum fields
		try:
			DictHelper.eval(req['data'], ['template', 'locale', 'text', 'html'])
		except ValueError as e:
			return Error(
				errors.body.DATA_FIELDS, [[f, 'missing'] for f in e.args]
			)

		# If the subject isn't passed
		if 'subject' not in req['data']:
			req['data']['subject'] = ''

		# Find the template variables
		dTemplate = Template.get(req['data']['template'], raw=['variables'])
		if not dTemplate:
			return Error(
				errors.body.DB_NO_RECORD, (req['data']['template'], 'template')
			)

		# If the locale doesn't exist
		if not Locale.exists(req['data']['locale']):
			return Error(
				errors.body.DB_NO_RECORD, (req['data']['locale'], 'locale')
			)

		# Generate the template and return it
		return Response(
			self._generate_email({
				'subject': req['data']['subject'],
				'text': req['data']['text'],
				'html': req['data']['html']
			}, req['data']['locale'], dTemplate['variables'])
		)

	def template_sms_create(self, req):
		"""Template SMS create

		Adds an sms content record to an existing template record instance

		Arguments:
			req (dict): The request details, which can include 'data', \
						'environment', and 'session'

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		sUserID = access.internal_or_verify(req, 'mouth_content', access.CREATE)

		# Check minimum fields
		try: DictHelper.eval(req['data'], ['template', 'locale'])
		except ValueError as e:
			return Error(
				errors.body.DATA_FIELDS, [[f, 'missing'] for f in e.args]
			)

		# Make sure the template exists
		dTemplate = Template.get(req['data']['template'], raw=['variables'])
		if not dTemplate:
			return Error(
				errors.body.DB_NO_RECORD, (req['data']['template'], 'template')
			)

		# Make sure the locale exists
		if not Locale.exists(req['data']['locale']):
			return Error(
				errors.body.DB_NO_RECORD, (req['data']['locale'], 'locale')
			)

		# Verify the instance
		try:
			oSMS = TemplateSMS(req['data'])
		except ValueError as e:
			return Error(errors.body.DATA_FIELDS, e.args[0])

		# Check content for errors
		lErrors = self._checkTemplateContent(
			req['data'],
			['content'],
			dTemplate['variables']
		)

		# If there's any errors
		if lErrors:
			return Error(errors.TEMPLATE_CONTENT_ERROR, lErrors)

		# Create the record
		try:
			oSMS.create(changes={'user': sUserID})
		except Record_Base.DuplicateException as e:
			return Error(
				errors.body.DB_DUPLICATE,
				(req['data']['locale'], 'template_locale')
			)

		# Return the ID to indicate OK
		return Response(oSMS['_id'])

	def template_sms_delete(self, req):
		"""Template SMS delete

		Deletes sms content from an existing template record instance

		Arguments:
			req (dict): The request details, which can include 'data', \
						'environment', and 'session'

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		sUserID = access.internal_or_verify(req, 'mouth_content', access.DELETE)

		# If the ID is missing
		if '_id' not in req['data']:
			return Error(errors.body.DATA_FIELDS, [['_id', 'missing']])

		# Find the record
		oSMS = TemplateSMS.get(req['data']['_id'])

		# If it doesn't exist
		if not oSMS:
			return Error(
				errors.body.DB_NO_RECORD, (req['data']['_id'], 'template_sms')
			)

		# Delete the record and return the result
		return Response(
			oSMS.delete(changes={'user': sUserID})
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
		sUserID = access.internal_or_verify(req, 'mouth_content', access.UPDATE)

		# Check minimum fields
		try: DictHelper.eval(req['data'], ['_id', 'content'])
		except ValueError as e:
			return Error(
				errors.body.DATA_FIELDS, [[f, 'missing'] for f in e.args]
			)

		# Find the record
		oSMS = TemplateSMS.get(req['data']['_id'])

		# If it doesn't exist
		if not oSMS:
			return Error(
				errors.body.DB_NO_RECORD, (req['data']['_id'], 'template_sms')
			)

		# Update the content
		try:
			oSMS['content'] = req['data']['content']
		except ValueError as e:
			return Error(errors.body.DATA_FIELDS, [e.args[0]])

		# Find the primary template variables
		dTemplate = Template.get(oSMS['template'], raw=['variables'])

		# Check content for errors
		lErrors = self._checkTemplateContent(
			req['data'],
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

	def template_sms_generate_create(self, req):
		"""Template SMS Generate create

		Generates a template from the base variable data for the purposes of
		testing / validating

		Arguments:
			req (dict): The request details, which can include 'data', \
						'environment', and 'session'

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		sUserID = access.internal_or_verify(req, 'mouth_content', access.READ)

		# Check minimum fields
		try: DictHelper.eval(req['data'], ['template', 'locale', 'content'])
		except ValueError as e:
			return Error(
				errors.body.DATA_FIELDS, [[f, 'missing'] for f in e.args]
			)

		# Find the template variables
		dTemplate = Template.get(req['data']['template'], raw=['variables'])
		if not dTemplate:
			return Error(errors.body.DB_NO_RECORD, (req['data']['template'], 'template'))

		# If the locale doesn't exist
		if not Locale.exists(req['data']['locale']):
			return Error(
				errors.body.DB_NO_RECORD, (req['data']['locale'], 'locale')
			)

		# Generate the template and return it
		return Response(
			self._generate_sms(
				req['data']['content'],
				req['data']['locale'],
				dTemplate['variables']
			)
		)

	def templates_read(self, req):
		"""Templates read

		Returns all templates in the system

		Arguments:
			req (dict): The request details, which can include 'data', \
						'environment', and 'session'

		Returns:
			Response
		"""

		# Make sure the client has access via the session
		access.verify(req['session'], 'mouth_template', access.READ)

		# Fetch and return all templates
		return Response(
			Template.get(raw=True, orderby='name')
		)