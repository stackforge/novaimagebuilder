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
sys.path.append("../")
import MockStackEnvironment
sys.modules['StackEnvironment'] = sys.modules.pop('MockStackEnvironment')
sys.modules['StackEnvironment'].StackEnvironment = sys.modules['StackEnvironment'].MockStackEnvironment
import StackEnvironment
import novaimagebuilder.CacheManager
novaimagebuilder.CacheManager.StackEnvironment = StackEnvironment
import logging
import threading
import multiprocessing



logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(levelname)s %(name)s thread(%(threadName)s) Message: %(message)s')

se = StackEnvironment.StackEnvironment()

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
#mse = StackEnvironment("username","password","tenant","auth_url")
mse = StackEnvironment.StackEnvironment()
cm = novaimagebuilder.CacheManager.CacheManager()

# Create our bogus entry in the cache index and set it to 0
cm.lock_and_get_index()
cm._set_index_value("testobjOS", "testobjname", "testloc", "0")
cm.write_index_and_unlock()

class UpdateThread():
    def __call__(self):
        #print "about to run 20 updates"
        for i in range(0,20):
            cm.lock_and_get_index()
            #print "--------- three lines below"
            #print "In the lock - 1 next line should always show value"
            value = cm._get_index_value("testobjOS", "testobjname", "testloc")
            #print "In the lock - 2 value %s" % (value)
            newvalue = int(value) + 1
            cm._set_index_value("testobjOS", "testobjname", "testloc", str(newvalue))
            #print "In the lock - 3 did update - leaving"
            #print "--------- three lines above"
            cm.write_index_and_unlock()

class MultiThreadProcess():
    def __call__(self):
        #print "Here I run 20 threads"
        threads = [ ]
        for i in range (0,20):
            thread = threading.Thread(group=None, target=UpdateThread())
            threads.append(thread)
            thread.run()

# Fork 20 copies of myself
processes = [ ]
for i in range(0,20):
    proc = multiprocessing.Process(group=None, target=MultiThreadProcess())
    processes.append(proc)
    proc.start()
for proc in processes:
    proc.join()

cm.lock_and_get_index()
value = cm._get_index_value("testobjOS", "testobjname", "testloc")
cm.unlock_index()
print "Final value should be 8000 and is %s" % (value)

# Have each process create 20 threads

# Have each 


#cm.retrieve_and_cache_object("install-iso2", mosp, "http://repos.fedorapeople.org/repos/aeolus/imagefactory/testing/repos/rhel/imagefactory.repo",
#                             True)
