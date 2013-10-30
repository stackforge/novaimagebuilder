# encoding: utf-8

#   Copyright 2013 Red Hat, Inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

# TODO: add failures

import uuid
import logging
from novaimagebuilder.Singleton import Singleton
from MockNovaInstance import MockNovaInstance


class MockStackEnvironment(Singleton):

    # From http://docs.openstack.org/api/openstack-block-storage/2.0/content/Volumes.html
    # this does not match the docstring in novaimagebuilder.StackEnvironment.get_volume_status()
    VOLUME_STATUS_LIST = ('CREATING',
                          'AVAILABLE',
                          'ATTACHING',
                          'IN-USE',
                          'DELETING',
                          'ERROR',
                          'ERROR_DELETING',
                          'BACKING-UP',
                          'RESTORING-BACKUP',
                          'ERROR_RESTORING')

    # From the docstring in novaimagebuilder.StackEnvironment.get_image_status()
    IMAGE_STATUS_LIST = ('QUEUED', 'SAVING', 'ACTIVE', 'KILLED', 'DELETED', 'PENDING_DELETE')

    def _singleton_init(self):
        super(StackEnvironment, self)._singleton_init()
        self.log = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))
        # Attributes controlling Mock behavior
        self.cinder = False
        self.cdrom = False
        self.floppy = False
        self.direct_boot = False
        self.keystone_srvr = None
        self.glance_srvr = None
        self.cinder_srvr = None
        self.failure = {'status': False, 'timeout': 0}
        self.volume_status_index = 1
        self.image_status_index = 2

    @property
    def keystone_server(self):
        return self.keystone_srvr

    @property
    def glance_server(self):
        return self.glance_srvr

    @property
    def cinder_server(self):
        return self.cinder_srvr

    def is_cinder(self):
        return self.cinder

    def is_cdrom(self):
        return self.cdrom

    def is_floppy(self):
        return self.floppy

    def is_direct_boot(self):
        return self.direct_boot

    def upload_image_to_glance(self, name, local_path=None, location=None, format='raw', min_disk=0, min_ram=0,
                               container_format='bare', is_public=True):
        #self.log.debug("Doing mock glance upload")
        #self.log.debug("File: (%s) - Name (%s) - Format (%s) - Container (%s)" %
        #               (local_path, name, format, container_format))
        return uuid.uuid4()

    def upload_volume_to_cinder(self, name, volume_size=None, local_path=None, location=None, format='raw',
                                container_format='bare', is_public=True, keep_image=True):
        #self.log.debug("Doing mock glance upload and cinder copy")
        #self.log.debug("File: (%s) - Name (%s) - Format (%s) - Container (%s)" %
        #               (local_path, name, format, container_format))
        return uuid.uuid4(), uuid.uuid4()

    def create_volume_from_image(self, image_id, volume_size=None):
        return uuid.uuid4(), uuid.uuid4()

    def delete_image(self, image_id):
        pass

    def delete_volume(self, volume_id):
        pass

    def get_volume_status(self, volume_id):
        return self.VOLUME_STATUS_LIST[self.volume_status_index]

    def get_image_status(self, image_id):
        return self.IMAGE_STATUS_LIST[self.image_status_index]

    def launch_instance(self, root_disk=None, install_iso=None, secondary_iso=None, floppy=None, aki=None, ari=None,
                        cmdline=None, userdata=None):
        return MockNovaInstance(object(), self)
