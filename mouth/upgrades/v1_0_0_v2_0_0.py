# coding=utf8
""" Upgrade 1.0.0 to 2.0.0

This script does nothing, but it establishes the upgrade system so it's in \
place for future upgrades
"""
__author__		= "Chris Nasr"
__copyright__	= "Ouroboros Coding Inc."
__version__		= "1.0.0"
__email__		= "chris@ouroboroscoding.com"
__created__		= "2023-10-12"

def run():
	"""Run

	Main entry into the script, called by the upgrade module

	Returns:
		bool
	"""

	# Notify the user
	print('Running 1.0 to 2.0 Upgrade script')

	# Notify the user
	print('Finished')

	# Return OK
	return True