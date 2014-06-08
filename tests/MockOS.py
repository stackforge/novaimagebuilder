# coding=utf-8

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

import logging
from MockStackEnvironment import MockStackEnvironment
from MockCacheManager import MockCacheManager


class MockOS(object):
    def __init__(self, osinfo_dict, install_type, install_media_location, install_config, install_script=None):
        self.log = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))
        self.status = 'RUNNING'  # Possible return values: INPROGRESS, FAILED, COMPLETE
        self.env = MockStackEnvironment()
        self.cache = MockCacheManager()
        self.osinfo_dict = osinfo_dict
        self.install_type = install_type
        self.install_media_location = install_media_location
        self.install_config = install_config
        self.install_script = install_script
        self.iso_content_flag = False
        self.iso_content_dict = {}
        self.url_content_dict = {}

    def os_ver_arch(self):
        return self.osinfo_dict['shortid'] + "-" + self.install_config['arch']

    def prepare_install_instance(self):
        pass

    def start_install_instance(self):
        pass

    def update_status(self):
        return self.status

    def wants_iso_content(self):
        return self.iso_content_flag

    def iso_content_dict(self):
        return self.iso_content_dict

    def url_content_dict(self):
        return self.url_content_dict

    def abort(self):
        pass

    def cleanup(self):
        pass
