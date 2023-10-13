from setuptools import setup

with open('README.md', 'r') as oF:
	long_description=oF.read()

setup(
	name='mouth-oc',
	version='2.0.0',
	description='Mouth contains a service to run outgoing communications like email and sms messages',
	long_description=long_description,
	long_description_content_type='text/markdown',
	url='https://ouroboroscoding.com/body/mouth',
	project_urls={
		'Documentation': 'https://ouroboroscoding.com/body/mouth',
		'Source': 'https://github.com/ouroboroscoding/mouth',
		'Tracker': 'https://github.com/ouroboroscoding/mouth/issues'
	},
	keywords=['rest', 'microservices', 'email', 'sms', 'communications'],
	author='Chris Nasr - Ouroboros Coding Inc.',
	author_email='chris@ouroboroscoding.com',
	license='Custom',
	packages=['mouth', 'mouth.records'],
	package_data={'mouth': [
		'definitions/*.json',
		'upgrades/*'
	]},
	python_requires='>=3.10',
	install_requires=[
		'body-oc>=2.0.0,<2.1',
		'brain-oc>=2.0.0,<2.1',
		'twilio==7.16.1',
		'upgrade-oc>=1.0.0,<1.1'
	],
	entry_points={
		'console_scripts': ['mouth=mouth.__main__:main']
	},
	zip_safe=True
)