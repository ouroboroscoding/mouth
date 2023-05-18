# coding=utf8
""" Mouth

Handles communication
"""

__author__		= "Chris Nasr"
__version__		= "1.0.0"
__copyright__	= "Ouroboros Coding Inc."
__email__		= "chris@ouroboroscoding.com"
__created__		= "2022-12-12"

# Python imports
import os
import platform
import sys

# Pip imports
from body import errors
from RestOC import Conf, EMail, Record_MySQL, REST, Services, Session

# Module imports
from . import Mouth
from . import records

def cli():
	"""CLI

	Called from the command line to run from the current directory

	Returns:
		uint
	"""

	# Load the config
	Conf.load('config.json')
	sConfOverride = 'config.%s.json' % platform.node()
	if os.path.isfile(sConfOverride):
		Conf.load_merge(sConfOverride)

	# Get Brain config
	dConfig = Conf.get('mouth', {
		'mysql_host': 'mouth'
	})

	# Add the global prepend
	Record_MySQL.db_prepend(Conf.get(('mysql', 'prepend'), ''))

	# Add the primary mysql DB
	Record_MySQL.add_host('mouth', Conf.get(('mysql', 'hosts', dConfig['mysql_host']), {
		'host': 'localhost',
		'port': 3306,
		'charset': 'utf8',
		'user': 'root',
		'passwd': ''
	}))

	# Set the timestamp timezone
	Record_MySQL.timestamp_timezone(
		Conf.get(('mysql', 'timestamp_timezone'), '+00:00')
	)

	# If we are installing
	if len(sys.argv) > 1 and sys.argv[1] == 'install':
		return install()

	# Init the email module
	EMail.init(Conf.get('email', {
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

	# Get redis session config
	dRedis = Conf.get(('redis', 'session'), {
		'host': 'localhost',
		'port': 6379,
		'db': 0,
		'charset': 'utf8'
	})

	# Init the Session module
	Session.init(dRedis)

	# Get the REST config
	dRest = Conf.get('rest', {
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
	if 'VERBOSE' in os.environ and os.environ['VERBOSE'] == '1':
		Services.verbose()

	# Get all the services
	dServices = {k:None for k in dRest['services']}

	# Add this service
	dServices['mouth'] = Mouth()

	# Register all services
	Services.register(
		dServices,
		oRestConf,
		Conf.get(('services', 'salt')),
		Conf.get(('services', 'internal_key_timeout'), 10)
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
		'https?://(.*\\.)?%s' % Conf.get(('rest', 'allowed')).replace('.', '\\.'),
		error_callback=errors.service_error
	).run(
		host=oRestConf['mouth']['host'],
		port=oRestConf['mouth']['port'],
		workers=oRestConf['mouth']['workers'],
		timeout='timeout' in oRestConf['mouth'] and oRestConf['mouth']['timeout'] or 30
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
