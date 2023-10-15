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
import record_mysql
from upgrade import upgrade

# Python imports
from os.path import abspath, expanduser
from pathlib import Path
from sys import argv, exit, stderr

# Module imports
from mouth import install, rest

def main():
	"""Main

	Called from the command line to run from the current directory

	Returns:
		uint
	"""

	# Get Brain config
	conf = config.mouth({
		'data': './.mouth',
		'records': 'primary'
	})

	# Add the primary host
	record_mysql.add_host(config.mysql[conf['records']]({
		'charset': 'utf8',
		'host': 'localhost',
		'passwd': '',
		'port': 3306,
		'user': 'mysql'
	}))

	# Set the timestamp timezone
	record_mysql.timestamp_timezone(
		config.mysql.timestamp_timezone('+00:00')
	)

	# If we have no arguments
	if len(argv) == 1:

		# Run the REST server
		return rest.run()

	# Else, if we have one argument
	elif len(argv) == 2:

		# If we are installing
		if argv[1] == 'install':
			if '~' in conf['data']:
				conf['data'] = expanduser(conf['data'])
			return install.install(conf['data'])

		# Else, if we are explicitly stating the rest service
		elif argv[1] == 'rest':
			return rest.run()

		# Else, if we are upgrading
		elif argv[1] == 'upgrade':
			if '~' in conf['data']:
				conf['data'] = expanduser(conf['data'])
			return upgrade(
				abspath(conf['data']),
				Path(__file__).parent.resolve()
			)

	# Else, arguments are wrong, print and return an error
	print('Invalid arguments', file = stderr)
	return 1

# Only run if called directly
if __name__ == '__main__':
	exit(main())