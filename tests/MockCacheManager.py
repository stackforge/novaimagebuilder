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

import logging
import os
import os.path
import uuid
import json
from novaimagebuilder.Singleton import Singleton


class MockCacheManager(Singleton):
    """
    Mock implementation of CacheManager for unit testing.

    * To test against locked or unlocked state, set the attribute 'locked' to True or False.

    * To test with a populated index, set the attribute 'index' to a populated dict.
    """

    CACHE_ROOT = "/tmp/MockCacheManager/"

    def _singleton_init(self, *args, **kwargs):
        self.log = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))
        self.index = {}
        self.inedx_update = {}
        self.locked = False

        if not os.path.exists(self.CACHE_ROOT):
            os.mkdir(self.CACHE_ROOT)

    def lock_and_get_index(self):
        """
        Sets the 'locked' attribute to True.

        """
        if self.locked:
            pass  # Should be throwing an exception
        else:
            self.locked = True

    def write_index_and_unlock(self):
        """
        Updates the 'index' dict with whatever is in 'index_update' and sets 'locked' to False.

        """
        if self.locked:
            if len(self.index_update) > 0:
                self.index.update(self.index_update)
                self.index_update = {}
            self.locked = False
        else:
            pass  # Should throw an exception telling user to lock first

    def unlock_index(self):
        """
        Sets 'index_update' to an empty dict and sets 'locked' to False.

        """
        self.index_update = {}
        self.locked = False

    def retrieve_and_cache_object(self, object_type, os_plugin, source_url, save_local):
        """
        Writes out a mock cache file to '/tmp/MockCacheManager' with the same naming convention used by
        CacheManager.

        @param object_type: A string indicating the type of object being retrieved
        @param os_plugin: Instance of the delegate for the OS associated with the download
        @param source_url: Location from which to retrieve the object/file
        @param save_local: bool indicating whether a local copy of the object should be saved
        @return: dict containing the various cached locations of the file
           local: Local path to file (contents are this dict)
           glance: Glance object UUID (does not correlate to a real Glance object)
           cinder: Cinder object UUID (dose not correlate to a real Cinder object)
        """
        self.lock_and_get_index()
        existing_cache = self._get_index_value(os_plugin.os_ver_arch(), object_type, None)
        if existing_cache:
            self.log.debug("Found object in cache")
            self.unlock_index()
            return existing_cache

        self.unlock_index()
        self.log.debug("Object not in cache")

        object_name = os_plugin.os_ver_arch() + "-" + object_type
        local_object_filename = self.CACHE_ROOT + object_name
        locations = {"local": local_object_filename, "glance": str(uuid.uuid4()), "cinder": str(uuid.uuid4())}

        if not os.path.isfile(local_object_filename):
            object_file = open(local_object_filename, 'w')
            json.dump(locations, object_file)
            object_file.close()
        else:
            self.log.warning("Local file (%s) is already present - assuming it is valid" % local_object_filename)

        self._do_index_updates(os_plugin.os_ver_arch(), object_type, locations)
        return locations

    def _get_index_value(self, os_ver_arch, name, location):
        if self.index is None:
            raise Exception("Attempt made to read index values while a locked index is not present")

        if not os_ver_arch in self.index:
            return None

        if not name in self.index[os_ver_arch]:
            return None

        # If the specific location is not requested, return the whole location dict
        if not location:
            return self.index[os_ver_arch][name]

        if not location in self.index[os_ver_arch][name]:
            return None
        else:
            return self.index[os_ver_arch][name][location]

    def _set_index_value(self, os_ver_arch, name, location, value):
        if self.index is None:
            raise Exception("Attempt made to read index values while a locked index is not present")

        if not os_ver_arch in self.index:
            self.index_update[os_ver_arch] = {}

        if not name in self.index[os_ver_arch]:
            self.index_update[os_ver_arch][name] = {}

        # If the specific location is not specified, assume value is the entire dict
        if not location:
            if type(value) is not dict:
                raise Exception("When setting a value without a location, the value must be a dict")
            self.index_update[os_ver_arch][name] = value
            return

        self.index[os_ver_arch][name][location] = value

    def _do_index_updates(self, os_ver_arch, object_type, locations):
        self.lock_and_get_index()
        self._set_index_value(os_ver_arch, object_type, None, locations )
        self.write_index_and_unlock()