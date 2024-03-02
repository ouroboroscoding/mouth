# coding=utf8
""" Mouth

Handles communication
"""

__author__		= "Chris Nasr"
__version__		= "1.0.0"
__copyright__	= "Ouroboros Coding Inc."
__email__		= "chris@ouroboroscoding.com"
__created__		= "2022-12-12"

# Ouroboros imports
from config import config

# Python imports
import sys

# Pip imports
from body import errors
from RestOC import EMail, Record_MySQL, REST, Services, Session

# Module imports
from . import Mouth
from . import records

def cli():
	"""CLI

	Called from the command line to run from the current directory

	Returns:
		uint
	"""

	# Get Mouth config
	dConfig = config.mouth({
		'mysql_host': 'mouth',
		'verbose': False
	})

	# Add the global prepend
	Record_MySQL.db_prepend(config.mysql.prepend(''))

	# Add the primary mysql DB
	Record_MySQL.add_host('mouth', config.mysql.hosts[dConfig['mysql_host']]({
		'host': 'localhost',
		'port': 3306,
		'charset': 'utf8',
		'user': 'root',
		'passwd': ''
	}))

	# Set the timestamp timezone
	Record_MySQL.timestamp_timezone(
		config.mysql.timestamp_timezone('+00:00')
	)

	# If we are installing
	if len(sys.argv) > 1 and sys.argv[1] == 'install':
		return install()

	# Init the email module
	EMail.init(config.email({
		'error_to': 'errors@localhost',
		'from': 'admin@localhost',
		'smtp': {
			'host': 'localhost',
			'port': 587,
			'tls': True,
			'user': 'noone',
			'passwd': 'nopasswd'
		}
	}))

	# Init the Session module
	Session.init('session')

	# Get the REST config
	dRest = config.rest({
		'allowed': 'localhost',
		'default': {
			'domain': 'localhost',
			'host': '0.0.0.0',
			'port': 8800,
			'protocol': 'http',
			'workers': 1
		},
		'services': {
			'brain': {'port': 0},
			'mouth': {'port': 1}
		}
	})

	# Create the REST config instance
	oRestConf = REST.Config(dRest)

	# Set verbose mode if requested
	if dConfig['verbose']:
		Services.verbose()

	# Get all the services
	dServices = {k:None for k in dRest['services']}

	# Add this service
	dServices['mouth'] = Mouth()

	# Register all services
	Services.register(
		dServices,
		oRestConf,
		config.services.salt(),
		config.services.internal_key_timeout(10)
	)

	# Create the HTTP server and map requests to service
	REST.Server({

		'/email': {'methods': REST.CREATE},

		'/locale': {'methods': REST.ALL},
		'/locales': {'methods': REST.READ},
		'/locale/exists': {'methods': REST.READ},

		'/sms': {'methods': REST.CREATE},

		'/template': {'methods': REST.ALL},
		'/template/contents': {'methods': REST.READ},
		'/template/email': {'methods': REST.CREATE | REST.UPDATE | REST.DELETE},
		'/template/email/generate': {'methods': REST.CREATE},
		'/template/sms': {'methods': REST.CREATE | REST.UPDATE | REST.DELETE},
		'/template/sms/generate': {'methods': REST.CREATE},
		'/templates': {'methods': REST.READ}

		},
		'mouth',
		'https?://(.*\\.)?%s' % config.rest.allowed('localhost').replace('.', '\\.'),
		error_callback = errors.service_error
	).run(
		host = oRestConf['mouth']['host'],
		port = oRestConf['mouth']['port'],
		workers = oRestConf['mouth']['workers'],
		timeout = 'timeout' in oRestConf['mouth'] and \
					oRestConf['mouth']['timeout'] or \
					30
	)

	# Return OK
	return 0

def install():
	"""Install

	Installs required files, tables, records, etc. for the service

	Returns:
		int
	"""

	# Install tables
	records.install()

	# Return OK
	return 0

# Only run if called directly
if __name__ == '__main__':
	sys.exit(cli())