#!/usr/bin/python

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
import json
import os.path
import pycurl
import guestfs
from Singleton import Singleton
from StackEnvironment import StackEnvironment


class CacheManager(Singleton):
    """
    Class to manage the retrieval and storage of install source objects
    Typically the source for these objects are ISO images or install trees
    accessible via HTTP.  Content is moved into glance and optionally cinder.
    Some smaller pieces of content are also cached locally

    Currently items are keyed by os, version, arch and can have arbitrary
    names.  The name install_iso is special.  OS plugins are allowed to
    access a local copy before it is sent to glance, even if that local copy
    will eventually be deleted.
    """

    # TODO: Currently assumes the target environment is static - allow this to change
    # TODO: Sane handling of a pending cache item
    # TODO: Configurable
    CACHE_ROOT = "/var/lib/novaimagebuilder/"
    #INDEX_LOCK = lock()
    INDEX_FILE = "_cache_index"

    def _singleton_init(self):
        self.env = StackEnvironment()
        self.log = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))
        self.index_filename = self.CACHE_ROOT + self.INDEX_FILE
        if not os.path.isfile(self.index_filename):
            self.log.debug("Creating cache index file (%s)" % self.index_filename)
            # TODO: somehow prevent a race here
            index_file = open(self.index_filename, 'w')
            json.dump({ } , index_file)
            index_file.close()
        # This should be None except when we are actively working on it and hold a lock
        self.index = None

    def lock_and_get_index(self):
        """
        Obtain an exclusive lock on the cache index and then load it into the
        "index" instance variable.  Tasks done while holding this lock should be
        very brief and non-blocking.  Calls to this should be followed by either
        write_index_and_unlock() or unlock_index() depending upon whether or not the
        index has been modified.
        """

        #self.INDEX_LOCK.acquire()
        index_file = open(self.index_filename)
        self.index = json.load(index_file)
        index_file.close()

    def write_index_and_unlock(self):
        """
        Write contents of self.index back to the persistent file and then unlock it
        """

        index_file = open(self.index_filename, 'w')
        json.dump(self.index , index_file)
        index_file.close()
        self.index = None
        #self.INDEX_LOCK.release()

    def unlock_index(self):
        """
        Release the cache index lock without updating the persistent file
        """

        self.index = None
        #self.INDEX_LOCK.release()

    # INDEX looks like
    #
    # { "fedora-19-x86_64": { "install_iso":        { "local": "/blah", "glance": "UUID", "cinder": "UUID" },
    #                         "install_iso_kernel": { "local"

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
            self.index[os_ver_arch] = {}

        if not name in self.index[os_ver_arch]:
            self.index[os_ver_arch][name] = {}

        # If the specific location is not specified, assume value is the entire dict
        if not location:
            if type(value) is not dict:
                raise Exception("When setting a value without a location, the value must be a dict")
            self.index[os_ver_arch][name] = value
            return

        self.index[os_ver_arch][name][location] = value

    def retrieve_and_cache_object(self, object_type, os_plugin, source_url, save_local):
        """
        Download a file from a URL and store it in the cache.  Uses the object_type and
        data from the OS delegate/plugin to index the file correctly.  Also treats the
        object type "install-iso" as a special case, downloading it locally and then allowing
        the OS delegate to request individual files from within the ISO for extraction and
        caching.  This is used to efficiently retrieve the kernel and ramdisk from Linux
        install ISOs.

        @param object_type: A string indicating the type of object being retrieved
        @param os_plugin: Instance of the delegate for the OS associated with the download
        @param source_url: Location from which to retrieve the object/file
        @param save_local: bool indicating whether a local copy of the object should be saved
        @return dict containing the various cached locations of the file
           local: Local path to file
           glance: Glance object UUID
           cinder: Cinder object UUID
        """

        self.lock_and_get_index()
        existing_cache = self._get_index_value(os_plugin.os_ver_arch(), object_type, None)
        if existing_cache:
            self.log.debug("Found object in cache")
            self.unlock_index()
            return existing_cache
            # TODO: special case when object is ISO and sub-artifacts are not cached

        # The object is not yet in the cache
        # TODO: Some mechanism to indicate that retrieval is in progress
        #       additional calls to get the same object should block until this is done
        self.unlock_index()
        self.log.debug("Object not in cache")

        # TODO: If not save_local and the plugin doesn't need the iso, direct download in glance
        object_name = os_plugin.os_ver_arch() + "-" + object_type
        local_object_filename = self.CACHE_ROOT + object_name
        if not os.path.isfile(local_object_filename):
            self._http_download_file(source_url, local_object_filename)
        else:
            self.log.warning("Local file (%s) is already present - assuming it is valid" % local_object_filename)

        if object_type == "install-iso" and os_plugin.wants_iso_content():
            self.log.debug("The plugin wants to do something with the ISO - extracting stuff now")
            icd = os_plugin.iso_content_dict()
            if icd:
                self.log.debug("Launching guestfs")
                g = guestfs.GuestFS()
                g.add_drive_ro(local_object_filename)
                g.launch()
                g.mount_options ("", "/dev/sda", "/")
                for nested_obj_type in icd.keys():
                    nested_obj_name = os_plugin.os_ver_arch() + "-" + nested_obj_type
                    nested_object_filename = self.CACHE_ROOT + nested_obj_name
                    self.log.debug("Downloading ISO file (%s) to local file (%s)" % (icd[nested_obj_type],
                                                                                     nested_object_filename))
                    g.download(icd[nested_obj_type],nested_object_filename)
                    if nested_obj_type == "install-iso-kernel":
                        image_format = "aki"
                    elif nested_obj_type == "install-iso-initrd":
                        image_format = "ari"
                    else:
                        raise Exception("Nested object of unknown type requested")
                    (glance_id, cinder_id) = self._do_remote_uploads(nested_obj_name, nested_object_filename,
                                                                     format=image_format, container_format=image_format,
                                                                     use_cinder = False)
                    locations = {"local": nested_object_filename, "glance": str(glance_id), "cinder": str(cinder_id)}
                    self._do_index_updates(os_plugin.os_ver_arch(), object_type, locations)
                g.shutdown()
                g.close()

        (glance_id, cinder_id) = self._do_remote_uploads(object_name, local_object_filename)
        locations = {"local": local_object_filename, "glance": str(glance_id), "cinder": str(cinder_id)}
        self._do_index_updates(os_plugin.os_ver_arch(), object_type, locations)

        return locations

    def _do_index_updates(self, os_ver_arch, object_type, locations):
        self.lock_and_get_index()
        self._set_index_value(os_ver_arch, object_type, None, locations )
        self.write_index_and_unlock()

    def _do_remote_uploads(self, object_name, local_object_filename, format='raw', container_format='bare',
                           use_cinder=True):
        if self.env.is_cinder() and use_cinder:
            (glance_id, cinder_id) = self.env.upload_volume_to_cinder(object_name, local_path=local_object_filename,
                                                                      format=format, container_format=container_format)
        else:
            cinder_id = None
            glance_id = self.env.upload_image_to_glance(object_name, local_path=local_object_filename,
                                                        format=format, container_format=container_format)
        return (glance_id, cinder_id)

    def _http_download_file(self, url, filename):
        # Function to download a file from url to filename
        # Borrowed and modified from Oz by Chris Lalancette
        # https://github.com/clalancette/oz

        def _data(buf):
            # Function that is called back from the pycurl perform() method to
            # actually write data to disk.
            os.write(fd, buf)

        fd = os.open(filename,os.O_CREAT | os.O_WRONLY | os.O_TRUNC)

        try:
            c = pycurl.Curl()
            c.setopt(c.URL, url)
            c.setopt(c.CONNECTTIMEOUT, 15)
            c.setopt(c.WRITEFUNCTION, _data)
            c.setopt(c.FOLLOWLOCATION, 1)
            c.perform()
            c.close()
        finally:
            os.close(fd)