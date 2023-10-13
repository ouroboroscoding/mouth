# coding=utf8
""" Mouth Template Record

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
Template = Storage(

	# The primary definition
	jsonb.load(
		'%s/definitions/template.json' % Path(__file__).parent.parent.resolve()
	),

	# The extensions necessary to store the data in MySQL
	{
		# Table related
		'__sql__': {
			'charset': 'utf8mb4',
			'collate': 'utf8mb4_unicode_ci',
			'create': [ '_created', '_updated', 'name', 'variables' ],
			'db': config.mysql.db('mouth'),
			'indexes': [{
				'name': 'ui_name',
				'fields': 'name',
				'type': 'unique'
			}],
			'name': 'mouth_template',
			'revisions': [ 'user' ]
		},

		# Field related
		'_created': { '__mysql__': { 'opts': 'default CURRENT_TIMESTAMP' } },
		'_updated': { '__mysql__': {
			'opts': 'default CURRENT_TIMESTAMP on update CURRENT_TIMESTAMP'
		} },
		'variables': { '__mysql__': { 'json': True } }
	}
)

TEmail = Storage(

	# The primary definition
	jsonb.load(
		'%s/definitions/template_email.json' % \
			Path(__file__).parent.parent.resolve()
	),

	# The extensions necessary to store the data in MySQL
	{
		# Table related
		'__mysql__': {
			'charset': 'utf8mb4',
			'collate': 'utf8mb4_unicode_ci',
			'create': [
				'_created', '_updated', 'template', 'locale', 'subject', 'text',
				'html'
			],
			'db': config.mysql.db('mouth'),
			'indexes': [{
				'name': 'ui_template_locale',
				'fields': [ 'template', 'locale' ],
				'type': 'unique'
			}],
			'name': 'mouth_template_email',
			'revisions': [ 'user' ]
		},

		# Field related
		'_created': { '__mysql__': { 'opts': 'default CURRENT_TIMESTAMP' } },
		'_updated': { '__mysql__': {
			'opts': 'default CURRENT_TIMESTAMP on update CURRENT_TIMESTAMP'
		} },
		'locale': { '__mysql__': { 'type': 'char(5)' } }
	}
)

TSms = Storage(

	# The primary definition
	jsonb.load(
		'%s/definitions/template_sms.json' % \
			Path(__file__).parent.parent.resolve()
	),

	# The extensions necessary to store the data in MySQL
	{
		# Table related
		'__mysql__': {
			'charset': 'utf8mb4',
			'collate': 'utf8mb4_unicode_ci',
			'create': [
				'_created', '_updated', 'template', 'locale', 'content'
			],
			'db': config.mysql.db('mouth'),
			'indexes': [{
				'name': 'ui_template_locale',
				'fields': [ 'template', 'locale' ],
				'type': 'unique'
			}],
			'name': 'mouth_template_sms',
			'revisions': [ 'user' ]
		},

		# Field related
		'_created': { '__mysql__': { 'opts': 'default CURRENT_TIMESTAMP' } },
		'_updated': { '__mysql__': {
			'opts': 'default CURRENT_TIMESTAMP on update CURRENT_TIMESTAMP'
		} },
		'locale': { '__mysql__': { 'type': 'char(5)' } }
	}
)