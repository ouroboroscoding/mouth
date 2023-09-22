from setuptools import setup

with open('README.md', 'r') as oF:
	long_description=oF.read()

setup(
	name='Mouth-OC',
	version='1.0.5',
	description='Mouth contains a service to run outgoing communications like email and sms messages',
	long_description=long_description,
	long_description_content_type='text/markdown',
	url='https://ouroboroscoding.com/body/mouth',
	project_urls={
		'Documentation': 'https://ouroboroscoding.com/body/mouth',
		'Source': 'https://github.com/ouroboroscoding/mouth',
		'Tracker': 'https://github.com/ouroboroscoding/mouth/issues'
	},
	keywords=['rest','microservices'],
	author='Chris Nasr - Ouroboros Coding Inc.',
	author_email='chris@ouroboroscoding.com',
	license='Custom',
	packages=['mouth'],
	package_data={'mouth': ['definitions/*.json']},
	python_requires='>=3.10',
	install_requires=[
		'Rest-OC>=1.1.1',
		'Body-OC>=1.0.1',
		'Brain-OC>=1.1.6',
		'twilio==7.16.1'
	],
	entry_points={
		'console_scripts': ['mouth=mouth.__main__:cli']
	},
	zip_safe=True
)