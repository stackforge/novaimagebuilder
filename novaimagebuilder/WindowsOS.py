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
import guestfs
import uuid
from CacheManager import CacheManager
from ISOHelper import ISOHelper
from BaseOS import BaseOS
from tempfile import NamedTemporaryFile
from shutil import copyfile
from os import remove

class WindowsOS(BaseOS):

    BLANK_FLOPPY = "/usr/share/novaimagebuilder/disk.img"

    def __init__(self, osinfo_dict, install_type, install_media_location, install_config, install_script = None):
        super(WindowsOS, self).__init__(osinfo_dict, install_type, install_media_location, install_config, install_script)

        #TODO: Check for direct boot - for now we are using environments
        #      where we know it is present
        #if not self.env.is_direct_boot():
        #    raise Exception("Direct Boot feature required - Installs using syslinux stub not yet implemented")

        if install_type != "iso":
            raise Exception("Only ISO installs supported for Windows installs")

        if not self.env.is_cdrom():
            raise Exception("ISO installs require a Nova environment that can support CDROM block device mapping")
        

        # TODO: Remove these
        self.install_artifacts = [ ]


    def prepare_install_instance(self):
        """ Method to prepare all necessary local and remote images for an install
            This method may require significant local disk or CPU resource
        """
        # These must be created and cached beforehand
        # TODO: Automate
        driver_locations = self.cache.retrieve_and_cache_object("driver-iso", self, None, True)
        self.driver_iso_volume = driver_locations['cinder']
        iso_locations = self.cache.retrieve_and_cache_object("install-iso",
                self, self.install_media_location, True)
        if self.env.is_floppy():
            self.iso_volume = iso_locations['cinder']
            self._prepare_floppy()
            self.log.debug ("Prepared cinder iso (%s), driver_iso (%s) and\
                    floppy (%s) for install instance" % (self.iso_volume,
                        self.driver_iso_volume, self.floppy_volume))    
        else:
            self._respin_iso(iso_locations['local'], "x86_64")
            self.iso_volume_delete = True


    def start_install_instance(self):
        if self.install_type == "iso":
            self.log.debug("Launching windows install instance")
            if self.env.is_floppy():
                self.install_instance = self.env.launch_instance(root_disk=('blank', 10),
                        install_iso=('cinder', self.iso_volume),
                        secondary_iso=('cinder',self.driver_iso_volume),
                        floppy=('cinder',self.floppy_volume))
            else:
                self.install_instance = self.env.launch_instance(root_disk=('blank', 10), install_iso=('cinder', self.iso_volume), secondary_iso=('cinder', self.driver_iso_volume))
                
    def _respin_iso(self, iso_path, arch):
        try:
            new_install_iso = NamedTemporaryFile(delete=False)
            new_install_iso_name = new_install_iso.name
            new_install_iso.close()
            ih = ISOHelper(iso_path, arch)
            ih._copy_iso()
            ih._install_script_win_v6(self.install_script.name)
            ih._generate_new_iso_win_v6(new_install_iso_name)
            image_name = "install-iso-%s-%s" % (self.osinfo_dict['shortid'],
                    str(uuid.uuid4())[:8])
            self.iso_volume = self.env.upload_volume_to_cinder(image_name,
                    local_path=new_install_iso_name, keep_image=False)
        finally:
            if new_install_iso_name:
                remove(new_install_iso_name)

    def _prepare_floppy(self):
        self.log.debug("Preparing floppy with autounattend.xml")
        unattend_floppy_name = None
        unattend_file = None
        try:
            # Use tempfile to get a known unique temporary location for floppy image copy
            unattend_floppy = NamedTemporaryFile(delete=False)
            unattend_floppy_name = unattend_floppy.name
            unattend_floppy.close()
            copyfile(self.BLANK_FLOPPY, unattend_floppy_name)
            # Create a real file copy of the unattend content for use by guestfs
            unattend_file = NamedTemporaryFile()
            unattend_file.write(self.install_script.read())
            unattend_file.flush()
            # Copy unattend into floppy via guestfs
	    g = guestfs.GuestFS()
	    g.add_drive(unattend_floppy_name)
	    g.launch()
	    g.mount_options ("", "/dev/sda", "/")
	    g.upload(unattend_file.name,"/autounattend.xml")
	    shutdown_result = g.shutdown()
	    g.close()
            # Upload it to glance and copy to cinder
            # Unique-ish name
            image_name = "unattend-floppy-%s-%s" % ( self.osinfo_dict['shortid'], str(uuid.uuid4())[:8] )
            self.floppy_volume = self.env.upload_volume_to_cinder(image_name, local_path=unattend_floppy_name, keep_image = False) 
            self.install_artifacts.append( ('cinder', self.floppy_volume ) )
        finally:
            if unattend_floppy_name:
                remove(unattend_floppy_name)
            if unattend_file:
                unattend_file.close()

    def update_status(self):
        return "RUNNING"

    def wants_iso_content(self):
        return False

    def abort(self):
        pass

    def cleanup(self):
        # TODO: Remove self.install_artifacts
        pass
