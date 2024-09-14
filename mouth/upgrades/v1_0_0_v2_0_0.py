# coding=utf8
""" Upgrade 1.0.0 to 2.0.0

Addes the `_archived` flag to `mouth_template` records
"""
__author__		= "Chris Nasr"
__copyright__	= "Ouroboros Coding Inc."
__version__		= "1.0.0"
__email__		= "chris@ouroboroscoding.com"
__created__		= "2023-10-12"

# Ouroboros imports
from rest_mysql import Record_MySQL

# Record imports
from mouth.records.public import Locale, Template

def run():
	"""Run

	Main entry into the script, called by the upgrade module

	Returns:
		bool
	"""

	# Notify the user of start of script
	print('Running 1.0 to 2.0 Upgrade script')

	# Alter the locale table
	print('Altering `mouth_locale` table...', end='')
	dLocale = Locale.struct()
	Record_MySQL.Commands.execute(
		dLocale['host'],
		'ALTER TABLE `%(db)s`.`%(table)s`\n' \
		'CHANGE COLUMN `_archived` `_archived TINYINT(1) UNSIGNED NOT NULL' \
		' DEFAULT 0,\n' \
		'ADD INDEX `_archived` (`_archived` ASC) VISIBLE' % dLocale
	)
	print(' done')

	# Alter the template table
	print('Altering `mouth_template` table...', end='')
	dTemplate = Template.struct()
	Record_MySQL.Commands.execute(
		dTemplate['host'],
		'ALTER TABLE `%(db)s`.`%(table)s`\n' \
		'ADD COLUMN `_archived` TINYINT(1) UNSIGNED NOT NULL DEFAULT 0 AFTER' \
		' `_id`,\n' \
		'ADD INDEX `_archived` (`_archived` ASC) VISIBLE' % dTemplate
	)
	print(' done')

	# Notify the user of end of script
	print('Finished')

	# Return OK
	return True