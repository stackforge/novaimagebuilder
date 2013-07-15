from distutils.core import setup, Command
from distutils.command.sdist import sdist as _sdist
import subprocess
import time

VERSION = '0.0.1'
RELEASE = '0'

setup(name='imagebuilder',
      version=VERSION,
      description='Nova native image building tool',
      author='Ian McLeod',
      author_email='imcleod@redhat.com',
      license='ASL 2.0',
      url='',
      package_dir={'imagebuilder': 'imagebuilder'},
      packages=['imagebuilder', 'imagebuilder.openstack', 'imagebuilder.openstack.common',
                'imagebuilder.api', 'imagebuilder.api.controllers',
                'imagebuilder.api.controllers.osib', 'imagebuilder.api.controllers.osib.v1'],
      scripts=['create_image', 'imagebuilder-api'],
      )
