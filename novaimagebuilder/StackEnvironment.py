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

from keystoneclient.v2_0 import client as keystone_client
from novaclient.v1_1 import client as nova_client
from glanceclient import client as glance_client
from cinderclient import client as cinder_client
from Singleton import Singleton
from time import sleep
from novaclient.v1_1.contrib.list_extensions import ListExtManager
import os
from NovaInstance import NovaInstance
import logging


class StackEnvironment(Singleton):

    """
    StackEnvironment
    """

    def _singleton_init(self):
        super(StackEnvironment, self)._singleton_init()
        self.log = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))
        # We want the following environment variables set: OS_USERNAME, OS_PASSWORD, OS_TENANT, OS_AUTH_URL
        try:
            username = os.environ['OS_USERNAME']
            password = os.environ['OS_PASSWORD']
            tenant = os.environ['OS_TENANT_NAME']
            auth_url = os.environ['OS_AUTH_URL']
        except Exception, e:
            raise Exception("Unable to retrieve auth info from environment \
                    variables. exception: %s" % e.message)

        try:
            self.keystone = keystone_client.Client(username=username,
                    password=password, tenant_name=tenant, auth_url=auth_url)
            self.keystone.authenticate()
        except Exception, e:
            raise Exception('Error authenticating with keystone. Original \
                    exception: %s' % e.message)
        try:
            self.nova = nova_client.Client(username, password, tenant,
                    auth_url=auth_url, insecure=True)
        except Exception, e:
            raise Exception('Error connecting to Nova.  Nova is required for \
                    building images. Original exception: %s' % e.message)
        try:
            glance_url = self.keystone.service_catalog.get_endpoints()['image'][0]['adminURL']
            self.glance = glance_client.Client('1', endpoint=glance_url,
                    token=self.keystone.auth_token)
        except Exception, e:
            raise Exception('Error connecting to glance. Glance is required for\
                    building images. Original exception: %s' % e.message)
        
        try:
            self.cinder = cinder_client.Client('1', username, password, tenant,
                    auth_url)
        except:
            self.cinder = None

    @property
    def keystone_server(self):
        """


        @return: keystone client
        """
        return self.keystone

    @property
    def glance_server(self):
        """


        @return: glance client
        """
        return self.glance

    @property
    def cinder_server(self):
        """


        @return: cinder client or None
        """
        return self.cinder

    def upload_image_to_glance(self, name, local_path=None, location=None, format='raw', min_disk=0, min_ram=0,
                               container_format='bare', is_public=True, properties={}):
        """

        @param name: human readable name for image in glance
        @param local_path: path to an image file 
        @param location: URL for image file
        @param format: 'raw', 'vhd', 'vmdk', 'vdi', 'iso', 'qcow2', 'aki',
        'ari', 'ami'
        @param min_disk: integer of minimum disk size in GB that a nova instance
        needs to launch using this image
        @param min_ram: integer of minimum amount of RAM in GB that a nova
        instance needs to launch using this image
        @param container_format: currently not used by OpenStack components, so
        'bare' is a good default
        @param is_public: boolean to mark an image as being publically
        available
        @param properties: dictionary where keys are property names such as
        ramdisk_id and kernel_id and values are the property values
        @return: glance image id @raise Exception:
        """
        image_meta = {'container_format': container_format, 'disk_format':
                format, 'is_public': is_public, 'min_disk': min_disk, 'min_ram':
                min_ram, 'name': name, 'properties': properties}
        try:
            image_meta['data'] = open(local_path, "r")
        except Exception, e:
            if location:
                image_meta['location'] = location
            else:
                raise e
        
        image = self.glance.images.create(name=name)
        self.log.debug("Started uploading to Glance")
        image.update(**image_meta)
        while image.status != 'active':
            image = self.glance.images.get(image.id)
            if image.status == 'error':
                raise Exception('Error uploading image to Glance.')
            sleep(1)
        self.log.debug("Finished uploading to Glance")
        return image.id

    def upload_volume_to_cinder(self, name, volume_size=None, local_path=None,
            location=None, format='raw', container_format='bare',
            is_public=True, keep_image=True):
        """

        @param name: human readable name for volume in cinder
        @param volume_size: integer size in GB of volume
        @param local_path: path to an image file 
        @param location: URL to an image file
        @param format: 'raw', 'vhd', 'vmdk', 'vdi', 'iso', 'qcow2', 'aki',
        'ari', 'ami'
        @param container_format: currently not used by OpenStack components, so
        'bare' is a good default
        @param is_public: boolean to mark an image as being publically
        available
        @param keep_image: currently not implemented
        @return: tuple (glance image id, cinder volume id)
        """
        image_id = self.upload_image_to_glance(name, local_path=local_path,
                location=location, format=format, is_public=is_public)
        volume_id = self._migrate_from_glance_to_cinder(image_id, volume_size)
        if not keep_image:
            #TODO: spawn a thread to delete image after volume is created
            return volume_id
        return (image_id, volume_id)

    def create_volume_from_image(self, image_id, volume_size=None):
        """

        @param image_id: uuid of glance image
        @param volume_size: integer size in GB of volume to be created
        @return: cinder volume id
        """
        return self._migrate_from_glance_to_cinder(image_id, volume_size)

    def delete_image(self, image_id):
        """

        @param image_id: glance image id
        """
        self.glance.images.get(image_id).delete()

    def delete_volume(self, volume_id):
        """

        @param volume_id: cinder volume id
        """
        self.cinder.volumes.get(volume_id).delete()

    def _migrate_from_glance_to_cinder(self, image_id, volume_size):
        image = self.glance.images.get(image_id)
        if not volume_size:
        # Gigabytes rounded up
            volume_size = int(image.size/(1024*1024*1024)+1)

        self.log.debug("Started copying to Cinder")
        volume = self.cinder.volumes.create(volume_size,
                display_name=image.name, imageRef=image.id)
        while volume.status != 'available':
            volume = self.cinder.volumes.get(volume.id)
            if volume.status == 'error':
                volume.delete()
                raise Exception('Error occured copying glance image %s to \
                volume %s' % (image_id, volume.id))
            sleep(1)
        self.log.debug("Finished copying to Cinder")
        return volume.id

    def get_volume_status(self, volume_id):
        """

        @param volume_id: cinder volume id
        @return: 'active', 'error', 'saving', 'deleted' (possibly more states
        exist, but dkliban could not find documentation where they are all
        listed)
        """
        volume = self.cinder.volumes.get(volume_id)
        return volume.status
    
    def get_image_status(self, image_id):
        """

        @param image_id: glance image id
        @return: 'queued', 'saving', 'active', 'killed', 'deleted', or
        'pending_delete'
        """
        image = self.glance.images.get(image_id)
        return image.status

    def _create_blank_image(self, size):
        rc = os.system("qemu-img create -f qcow2 blank_image.tmp %dG" % size)
        if rc == 0:
            return
        else:
            raise Exception("Unable to create blank image")


    def _remove_blank_image(self):
        rc = os.system("rm blank_image.tmp")
        if rc == 0:
            return
        else:
            raise Exception("Unable to create blank image")

    def launch_instance(self, root_disk=None, install_iso=None, 
            secondary_iso=None, floppy=None, aki=None, ari=None, cmdline=None,
            userdata=None):
        """

        @param root_disk: tuple where first element is 'blank', 'cinder', or
        'glance' and second element is size, or cinder volume id, or glance
        image id.
        @param install_iso: install media represented by tuple where first
        element is 'cinder' or 'glance'  and second element is cinder volume id
        or glance image id. 
        @param secondary_iso: media containing extra drivers  represented by
        tuple where first element is 'cinder' or 'glance'  and second element is
        cinder volume id or glance image id.
        @param floppy: media to be mounted as a floppy represented by tuple
        where first element is  'cinder' or 'glance'  and second element is
        cinder volume id or glance image id.
        @param aki: glance image id for kernel
        @param ari: glance image id for ramdisk
        @param cmdline: string command line argument for anaconda
        @param userdata: string containing kickstart file or preseed file
        @return: NovaInstance launched @raise Exception:
        """
        if root_disk:
            #if root disk needs to be created
            if root_disk[0] == 'blank':
                root_disk_size = root_disk[1]
                #Create a blank qcow2 image and uploads it
                self._create_blank_image(root_disk_size)
                if aki and ari and cmdline:
                    root_disk_properties = {'kernel_id': aki, 
                            'ramdisk_id': ari, 'command_line': cmdline}
                else:
                    root_disk_properties = {}
                root_disk_image_id = self.upload_image_to_glance(
                        'blank %dG disk' % root_disk_size, 
                        local_path='./blank_image.tmp', format='qcow2',
                        properties=root_disk_properties)
                self._remove_blank_image()
            elif root_disk[0] == 'glance':
                root_disk_image_id = root_disk[1]
            else:
                raise Exception("Boot disk must be of type 'blank' or 'glance'")

        if install_iso:
            if install_iso[0] == 'cinder':
                install_iso_id = install_iso[1]
            elif install_iso[0] == 'glance':
                install_iso_id = self.create_volume_from_image(install_iso[1])
            else:
                raise Exception("Install ISO must be of type 'cinder' or \
                        'glance'")
        if secondary_iso:
            if secondary_iso[0] == 'cinder':
                secondary_iso_id = secondary_iso[1]
            elif secondary_iso[0] == 'glance':
                secondary_iso_id = self.create_volume_from_image(secondary_iso_id)
            else:
                raise Exception("Secondary ISO must be of type 'cinder' or\
                        'glance'")
        if floppy:
            if floppy[0] == 'cinder':
                floppy_id = floppy[1]
            elif floppy[0] == 'glance':
                floppy_id = self.create_volume_from_image(floppy[1])
            else:
                raise Exception("Floppy must be of type 'cinder' or 'glance'")

        # if direct boot is not available (Havana):
        if not self.is_direct_boot():
            instance = None
            # 0 crdom drives are needed
            if not install_iso and not secondary_iso and not floppy:
                instance = self._launch_network_install(root_disk_image_id,
                        userdata)
            # 1 cdrom drive is needed
            elif install_iso and not secondary_iso and not floppy:
                instance = self._launch_single_cdrom_install(root_disk_image_id,
                        userdata, install_iso_id)
            # 2 cdrom drives are needed
            elif install_iso and secondary_iso and not floppy:
                instance = self._launch_instance_with_dual_cdrom(root_disk_image_id,
                        install_iso_id, secondary_iso_id)
            if instance:
                return NovaInstance(instance, self)

        #blank root disk with ISO, ISO2 and Floppy - Windows
        if install_iso and secondary_iso and floppy:

            instance = self._launch_windows_install(root_disk_image_id,
                    install_iso_id, secondary_iso_id, floppy_id)
            return NovaInstance(instance, self)

        #blank root disk with aki, ari and cmdline. install iso is optional.
        if aki and ari and cmdline and userdata:
          
            instance = self._launch_direct_boot(root_disk_image_id, userdata,
                    install_iso=install_iso_id)
            return NovaInstance(instance, self)

    def _launch_network_install(self, root_disk, userdata):
        #TODO: check the kickstart file in userdata for sanity
        self.log.debug("Starting instance for network install")
        image = self.glance.images.get(root_disk)
        instance = self.nova.servers.create("Install from network", image, "2",
                userdata=userdata)
        return instance

    def _launch_single_cdrom_install(self, root_disk, userdata, install_iso):
        image = self.glance.images.get(root_disk)
        self.log.debug("Starting instance for single cdrom install")
        if install_iso:
            if self.is_cdrom():
                block_device_mapping_v2 = [
                     {"source_type": "volume",
                     "destination_type": "volume",
                     "uuid": install_iso,
                     "boot_index": "1",
                     "device_type": "cdrom",
                     "disk_bus": "ide",
                    },
                    ]
                instance = self.nova.servers.create("Install with single cdrom",
                        image, "2",
                        block_device_mapping_v2=block_device_mapping_v2,
                        userdata=userdata)
                return instance
            else:
                #TODO: use BDM mappings from grizzly to launch instance
                pass
        else:
            raise Exception("Install ISO image id is required for single cdrom\
                    drive installations.")

    def _launch_instance_with_dual_cdrom(self, root_disk, install_iso,
            secondary_iso):

        block_device_mapping_v2 = [
                     {"source_type": "volume",
                     "destination_type": "volume",
                     "uuid": install_iso,
                     "boot_index": "1",
                     "device_type": "cdrom",
                     "disk_bus": "ide",
                    },
                    {"source_type": "volume",
                     "destination_type": "volume",
                     "uuid": secondary_iso,
                     "boot_index": "2",
                     "device_type": "cdrom",
                     "disk_bus": "ide",
                    },
                    ]

        image = self.glance.images.get(root_disk)
        instance = self.nova.servers.create("Install with dual cdroms", image, "2",
                meta={}, block_device_mapping_v2=block_device_mapping_v2)
        return instance

    def _launch_direct_boot(self, root_disk, userdata, install_iso=None):
        image = self.glance.images.get(root_disk)
        if install_iso:
            #assume that install iso is already a cinder volume
            block_device_mapping_v2 = [
                     {"source_type": "volume",
                     "destination_type": "volume",
                     "uuid": install_iso,
                     "boot_index": "1",
                     "device_type": "cdrom",
                     "disk_bus": "ide",
                    },
                    ]
        else:
           #must be a network install
           block_device_mapping_v2 = None
        instance = self.nova.servers.create("direct-boot-linux", image, "2",
                block_device_mapping_v2=block_device_mapping_v2,
                userdata=userdata)
        return instance
    
    def _launch_windows_install(self, root_disk, install_cdrom, drivers_cdrom,
            autounattend_floppy):

        block_device_mapping_v2 = [
                     {"source_type": "volume",
                     "destination_type": "volume",
                     "uuid": install_cdrom,
                     "boot_index": "1",
                     "device_type": "cdrom",
                     "disk_bus": "ide",
                    },
                    {"source_type": "volume",
                     "destination_type": "volume",
                     "uuid": drivers_cdrom,
                     "boot_index": "3",
                     "device_type": "cdrom",
                     "disk_bus": "ide",
                    },
                    {"source_type": "volume",
                     "destination_type": "volume",
                     "uuid": autounattend_floppy,
                     "boot_index": "2",
                     "device_type": "floppy",
                    },
                    ]

        image = self.glance.images.get(root_disk)
        instance = self.nova.servers.create("windows-volume-backed", image, "2",
                meta={}, block_device_mapping_v2=block_device_mapping_v2)
        return instance

    def is_cinder(self):
        """
        Checks if cinder is available.

        @return: True if cinder service is available
        """
        if not self.cinder:
            return False
        else:
            return True

    def is_cdrom(self):
        """
        Checks if nova allows mapping a volume as cdrom drive.
        This is only available starting with Havana

        @return: True if volume can be attached as cdrom
        """
        nova_extension_manager = ListExtManager(self.nova)
        for ext in nova_extension_manager.show_all():
            if ext.name == "VolumeAttachmentUpdate" and ext.is_loaded():
                return True
        return False

    def is_floppy(self):
        #TODO: check if floppy is available.  
        """
        Checks if nova allows mapping a volume as a floppy drive.
        This will not be available until Icehouse

        @return: Currently this always returns True.  
        """
        return False

    def is_direct_boot(self):
        #TODO: check if direct boot is available
        """
        Checks if nova allows booting an instance with a command line argument
        This will not be available until Icehouse

        @return: Currently this always returns False
        """
        return False
