# coding=utf8
""" Mouth REST

Handles starting the REST server using the Mouth service
"""

__author__		= "Chris Nasr"
__version__		= "1.0.0"
__copyright__	= "Ouroboros Coding Inc."
__email__		= "chris@ouroboroscoding.com"
__created__		= "2022-10-12"

# Ouroboros imports
from body import register_services, REST
from config import config
import em

# Python imports
from os import environ
from pprint import pformat

# Module imports
from mouth.service import Mouth

def errors(error):

	# If we don't send out errors
	if not config.mouth.send_error_emails(False):
		return True

	# Generate a list of the individual parts of the error
	lErrors = [
		'ERROR MESSAGE\n\n%s\n' % error['traceback'],
		'REQUEST\n\n%s %s:%s\n' % (
			error['method'], error['service'], error['path']
		)
	]
	if 'data' in error and error['data']:
		lErrors.append('DATA\n\n%s\n' % pformat(error['data']))
	if 'session' in error and error['session']:
		lErrors.append('SESSION\n\n%s\n' % pformat({
			k:error['session'][k] for k in error['session']
		}))
	if 'environment' in error and error['environment']:
		lErrors.append('ENVIRONMENT\n\n%s\n' % pformat(error['environment']))

	# Send the email
	return em.error('\n'.join(lErrors))

def run():
	"""Run

	Starts the http REST server
	"""

	# Get the config
	dConf = config.mouth({
		'verbose': False
	})

	# Init the service
	oMouth = Mouth()

	# Register the services
	oRest = register_services({ 'mouth': oMouth })

	# Run the REST server with the Client instance
	REST(
		'mouth',
		oMouth,
		config.body.rest.allowed('mouth.local'),
		errors,
		dConf['verbose']
	).run(
		host = oRest['mouth']['host'],
		port = oRest['mouth']['port'],
		workers = oRest['mouth']['workers'],
		timeout = 'timeout' in oRest['mouth'] and \
			oRest['mouth']['timeout'] or 30
	)