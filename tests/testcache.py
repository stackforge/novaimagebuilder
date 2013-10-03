#!/usr/bin/python
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

import sys
sys.path.append("../novaimagebuilder")
from MockStackEnvironment import MockStackEnvironment as StackEnvironment
from novaimagebuilder.CacheManager import CacheManager
import logging


logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(levelname)s %(name)s thread(%(threadName)s) Message: %(message)s')

class MockOSPlugin(object):
    
    def __init__(self, os_ver_arch = "fedora19-x86_64", wants_iso = True ):
        self.nameverarch = os_ver_arch
        self.wantscdrom = wants_iso

    def os_ver_arch(self):
        return self.nameverarch

    def wants_iso(self):
        return self.wants_iso

print "---- the following should do a glance and cinder upload"

mosp = MockOSPlugin(os_ver_arch = "fedora18-x86_64", wants_iso = False)
mse = StackEnvironment("username","password","tenant","auth_url")
cm = CacheManager(mse)

cm.retrieve_and_cache_object("install-iso", mosp, "http://repos.fedorapeople.org/repos/aeolus/imagefactory/testing/repos/rhel/imagefactory.repo",
                             True)
