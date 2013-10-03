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

from unittest import TestCase
from novaimagebuilder.OSInfo import OSInfo


class TestOSInfo(TestCase):
    def setUp(self):
        self.osinfo = OSInfo()

    def test_os_id_for_shortid(self):
        os_list = self.osinfo.db.get_os_list().get_elements()
        for os in os_list:
            self.assertEqual(self.osinfo.os_id_for_shortid(os.get_short_id()), os.get_id())

    def test_os_for_shortid(self):
        os = self.osinfo.os_for_shortid('fedora18')
        expected_keys = {'name': str, 'version': str, 'distro': str, 'family': str, 'shortid': str, 'id': str,
                         'media_list': list, 'tree_list': list, 'minimum_resources': list,
                         'recommended_resources': list}

        self.assertIsNotNone(os)
        self.assertIsInstance(os, dict)
        # check that the correct items are in the dict (as defined in OSInfo)
        # and that the values are the correct type
        for key in expected_keys.keys():
            self.assertIn(key, os)
            self.assertIsInstance(os[key], expected_keys[key])

    def test_os_for_iso(self):
        # TODO: implement test
        self.skipTest('%s is only partially implemented and unused.' % __name__)

    def test_os_for_tree(self):
        # TODO: implement test
        self.skipTest('%s is only partially implemented and unused.' % __name__)

    def test_install_script(self):
        config = {'admin_password': 'test_pw',
                  'arch': 'test_arch',
                  'license': 'test_license_key',
                  'target_disk': 'C',
                  'script_disk': 'A',
                  'preinstall_disk': 'test-preinstall',
                  'postinstall_disk': 'test-postinstall',
                  'signed_drivers': False,
                  'keyboard': 'en_TEST',
                  'laguage': 'en_TEST',
                  'timezone': 'America/Chicago'}

        fedora_script = self.osinfo.install_script('fedora18', config)
        windows_script = self.osinfo.install_script('win2k8r2', config)

        # TODO: actually check that config values were set in the script(s)
        self.assertIsNotNone(fedora_script)
        self.assertIsInstance(fedora_script, str)

        self.assertIsNotNone(windows_script)
        self.assertIsInstance(windows_script, str)

        self.assertNotEqual(fedora_script, windows_script)

    def test_os_ids(self):
        all_ids = self.osinfo.os_ids()
        fedora_ids = self.osinfo.os_ids({'fedora': 17})

        self.assertIsNotNone(all_ids)
        self.assertIsNotNone(fedora_ids)
        self.assertIsInstance(all_ids, dict)
        self.assertIsInstance(fedora_ids, dict)
        self.assertLess(len(fedora_ids), len(all_ids))