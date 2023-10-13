# coding=utf8
""" Install

Method to install the necessary mouth tables
"""

__author__		= "Chris Nasr"
__copyright__	= "Ouroboros Coding Inc."
__version__		= "1.0.0"
__email__		= "chris@ouroboroscoding.com"
__created__		= "2023-10-12"

# Ouroboros imports
from upgrade import set_latest

# Python imports
from os.path import abspath
from pathlib import Path

# Module imports
from mouth.records import locale, template

def install(data):
	"""Install

	Installs required files, tables, records, etc. for the service

	Arguments:
		data (str): The full path to the folder where install/upgrade data \
			files are stored

	Returns:
		int
	"""

	# Install records
	locale.Locale.install()
	template.Template.install()
	template.TEmail.install()
	template.TSms.install()

	# Store the last known upgrade version
	set_latest(
		abspath(data),
		Path(__file__).parent.resolve()
	)

	# Return OK
	return 0