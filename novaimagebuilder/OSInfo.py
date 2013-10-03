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
from gi.repository import Libosinfo as osinfo
from gi.repository import Gio


class OSInfo(object):
    """
    OSInfo offers convenience methods for getting information out of libosinfo

    @param path: Path (str) to the libosinfo data to use. Defaults to /usr/share/libosinfo/db
    """

    def __init__(self, path='/usr/share/libosinfo/db'):
        super(OSInfo, self).__init__()
        self.log = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))
        loader = osinfo.Loader()
        loader.process_path(path)
        self.db = loader.get_db()

    def os_id_for_shortid(self, shortid):
        """
        Get the full libosinfo OS id for a given shortid.

        @param shortid: The short form id for an OS record in libosinfo. (Ex. fedora18)
        @return: The id for an OS record in libosinfo. (Ex. http://fedoraproject.org/fedora/18)
        """
        for an_os in self.db.get_os_list().get_elements():
            if an_os.get_short_id() == shortid:
                return an_os.get_id()

    def os_for_shortid(self, shortid):
        """
        Given the shortid for an OS, get a dictionary of information about that OS.

        Items in 'media_list' are libosinfo Media objects. Useful methods on these objects include:
            get_url() - URL str to the media
            get_initrd_path() - Path str to the initrd image within the install tree for Linux installers
            get_kernel_path() - Path str to the kernel within the install tree for Linux installers
            get_volume_id() - A regular expression for matching the volume ID of an ISO9660 image
            get_installer() - Does the media provide an installer for the OS (True or False)
            get_installer_redoots() - The number of reboots required to complete an installation
            get_live() - Can an OS be booted directly from this media without installation (True or False)

        Items in the 'tree_list' are libosinfo Tree objects. Useful methods on these objects include:
            get_url() - URL str to the install tree
            get_boot_iso_path() - Path str to the boot image iso in the install tree
            get_initrd_path() - Path str to the initrd image within the install tree for Linux trees
            get_kernel_path() - Path str to the kernel within the install tree for Linux trees

        Items in the 'minimum_resources' and 'recommended_resources' lists are libosinfo Resources objects. Useful
        methods on these objects include:
            get_cpu() - The CPU frequency in Hz or -1 if a value is not available
            get_n_cpus() - The number of CPUs or -1 if a value is not available
            get_ram() - The amount of RAM in bytes or -1 if a value is not available
            get_storage() - The amount of storage in bytes or -1 if a value is not available

        Further documentation on the libosinfo API should be found at http://libosinfo.org/api/

        @param shortid: A str id for an OS such as rhel5
        @return: dict with keys:
            name (str)
            version (str)
            distro (str)
            family (str)
            shortid (str)
            id (str)
            media_list (list of libosinfo.Media objects)
            tree_list (list of libosinfo.Tree objects)
            minimum_resources (list of libosinfo.Resources objects)
            recommended_resources (list of libosinfo.Resources objects)
        """
        os = self.db.get_os(self.os_id_for_shortid(shortid))

        if os:
            return {'name': os.get_name(),
                    'version': os.get_version(),
                    'distro': os.get_distro(),
                    'family': os.get_family(),
                    'shortid': os.get_short_id(),
                    'id': os.get_id(),
                    'media_list': os.get_media_list().get_elements(),
                    'tree_list': os.get_tree_list().get_elements(),
                    'minimum_resources': os.get_minimum_resources().get_elements(),
                    'recommended_resources': os.get_recommended_resources().get_elements()}
        else:
            return None

    def os_for_iso(self, iso):
        """
        Given an install ISO, get information about the OS.

        *** THIS IS ONLY PARTIALLY IMPLEMENTED, USE AT YOUR OWN RISK ***

        @param iso: URL of an install iso
        @return: dict with keys:
            name
            version
            distro
            family
            shortid
            id
            media_list
            tree_list
            minimum_resources
            recommended_resources
        """
        # TODO: Figure out the correct way to implement / use this method
        media = osinfo.Media().create_from_location(iso)
        return self.os_for_shortid(media.get_os().get_shortid())

    def os_for_tree(self, tree):
        """
        Given an install tree, get information about the OS.

        *** THIS IS ONLY PARTIALLY IMPLEMENTED, USE AT YOUR OWN RISK ***

        @param tree: URL of an install tree
        @return: dict with keys:
            name
            version
            distro
            family
            shortid
            id
            media_list
            tree_list
            minimum_resources
            recommended_resources
        """
        # TODO: Figure out the correct way to implement / use this method
        install_tree = osinfo.Media().create_from_location(tree)
        return self.os_for_shortid(install_tree.get_os().get_shortid())

    def install_script(self, osid, configuration, profile='jeos'):
        """
        Get an install script for a given OS.

        @param osid: Either the shortid or id for an OS (str)
        @param configuration: A dict of install script customizations with the following keys:
            admin_password (required)
            arch (required)
            license (optional, default: None)
            target_disk (optional, default: None)
            script_disk (optional, default: None)
            preinstall_disk (optional, default: None)
            postinstall_disk (optional, default: None)
            signed_drivers (optional, default: True)
            keyboard (optional, default: 'en_US')
            language (optional, default: 'en_US')
            timezone (optional, default: 'America/New_York')
        @param profile: The profile of the install. (str) 'jeos', 'desktop', etc
        @return: install script as a str
        """
        if not osid.startswith('http'):
            osid = self.os_id_for_shortid(osid)

        os = self.db.get_os(osid)

        if os:
            script = None

            # TODO: This seems to be broken. Need to file a bug.
            #script = os.find_install_script(profile)
            # TODO: remove this once find_install_script() is fixed
            script_list = os.get_install_script_list().get_elements()
            for a_script in script_list:
                if a_script.get_profile() == profile:
                    script = a_script

            config = osinfo.InstallConfig()
            config.set_admin_password(configuration['admin_password'])
            config.set_hardware_arch(configuration['arch'])
            if configuration.get('license'):
                config.set_reg_product_key(configuration['license'])
            if configuration.get('target_disk'):
                config.set_target_disk(configuration['target_disk'])
            if configuration.get('script_disk'):
                config.set_script_disk(configuration['script_disk'])
            if configuration.get('preinstall_disk'):
                config.set_pre_install_drivers_disk(configuration['preinstall_disk'])
            if configuration.get('postinstall_disk'):
                config.set_post_install_drivers_disk(configuration['postinstall_disk'])
            if configuration.get('signed_drivers'):
                config.set_driver_signing(configuration['signed_drivers'])
            if configuration.get('keyboard'):
                config.set_l10n_keyboard(configuration['keyboard'])
            if configuration.get('language'):
                config.set_l10n_language(configuration['language'])
            if configuration.get('timezone'):
                config.set_l10n_timezone(configuration['timezone'])

            return script.generate(os, config, Gio.Cancellable())

        else:
            return None


    def os_ids(self, distros=None):
        """
        List the operating systems available from libosinfo.

        @param distros: A dict with keys being distro names and the values being the lowest version to list.
            Ex. {'fedora': 17, 'rhel': 5, 'ubuntu':12, 'win':6}
        @return: A dict with keys being OS shortid and values being OS name
        """
        os_dict = {}
        for os in self.db.get_os_list().get_elements():
            if distros:
                distro = os.get_distro()
                version = int(os.get_version().split('.')[0])  # Just compare major versions, ie 2 instead of 2.2.8
                for a_distro in distros:
                    if a_distro == distro and version >= distros[a_distro]:
                        os_dict[os.get_short_id()] = os.get_name()
            else:
               os_dict[os.get_short_id()] = os.get_name()

        return os_dict