# coding=utf8
""" Mouth Locale Record

Handles the locale record structure
"""

__author__		= "Chris Nasr"
__version__		= "1.0.0"
__maintainer__	= "Chris Nasr"
__email__		= "chris@ouroboroscoding.com"
__created__		= "2023-10-12"

# Ouroboros imports
from config import config
import jsonb
from record_mysql import Storage

# Python imports
from pathlib import Path

# Create the Storage instance
Locale = Storage(

	# The primary definition
	jsonb.load(
		'%s/definitions/locale.json' % Path(__file__).parent.parent.resolve()
	),

	# The extensions necessary to store the data in MySQL
	{
		# Table related
		'__mysql__': {
			'charset': 'utf8mb4',
			'collate': 'utf8mb4_unicode_ci',
			'create': [
				'_archived', '_created', 'name'
			],
			'db': config.mysql.db('mouth'),
			'indexes': {
				'ui_name': {
					'fields': 'name',
					'type': 'unique'
				}
			},
			'name': 'mouth_locale'
		},

		# Field related
		'_id': { '__mysql__': { 'type': 'char(5)' } },
		'_archived': { '__mysql__': { 'opts': 'default 0' } },
		'_created': { '__mysql__': { 'opts': 'default CURRENT_TIMESTAMP' } }
	}
)