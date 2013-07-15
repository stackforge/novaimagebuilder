from distutils.core import setup, Command
from distutils.command.sdist import sdist as _sdist
import subprocess
import time

VERSION = '0.0.1'
RELEASE = '0'

# Borrowed from Oz by Chris Lalancette
class sdist(_sdist):
    """ custom sdist command, to prep novaimagebuilder.spec file for inclusion """

    def run(self):
        global VERSION
        global RELEASE

        # Create a development release string for later use
        git_head = subprocess.Popen("git log -1 --pretty=format:%h",
                                    shell=True,
                                    stdout=subprocess.PIPE).communicate()[0].strip()
        date = time.strftime("%Y%m%d%H%M%S", time.gmtime())
        git_release = "%sgit%s" % (date, git_head)

        # Expand macros in oz.spec.in and create oz.spec
        spec_in = open('novaimagebuilder.spec.in', 'r')
        spec = open('novaimagebuilder.spec', 'w')
        for line in spec_in.xreadlines():
            if "@VERSION@" in line:
                line = line.replace("@VERSION@", VERSION)
            elif "@RELEASE@" in line:
                # If development release, include date+githash in %{release}
                if RELEASE.startswith('0'):
                    RELEASE += '.' + git_release
                line = line.replace("@RELEASE@", RELEASE)
            spec.write(line)
        spec_in.close()
        spec.close()

        # Run parent constructor
        _sdist.run(self)


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
      cmdclass={'sdist': sdist}
      )
