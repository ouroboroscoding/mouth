# coding=utf8
""" Errors

Mouth error codes
"""

__author__ = "Chris Nasr"
__copyright__ = "Ouroboros Coding Inc"
__version__ = "1.0.0"
__email__ = "chris@ouroboroscoding.com"
__created__ = "2023-01-11"

__all__ = [
	'ATTACHMENT_DECODE', 'ATTACHMENT_STRUCTURE', 'body',
	'TEMPLATE_CONTENT_ERROR', 'SMTP_ERROR'
]

# Ouroboros imports
from body import errors as body

TEMPLATE_CONTENT_ERROR = 1300
"""The content of the template is using a variable that doesn't exist"""

ATTACHMENT_STRUCTURE = 1301
"""The structure of the attachment is invalid"""

ATTACHMENT_DECODE = 1302
"""The attachment can not be decoded"""

SMTP_ERROR = 1303
"""There was an error connecting to or communicating with the SMTP server"""