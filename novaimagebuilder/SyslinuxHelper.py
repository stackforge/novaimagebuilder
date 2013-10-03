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
from tempfile import NamedTemporaryFile, TemporaryFile, mkdtemp
import guestfs
import shutil
import os
import subprocess
from StackEnvironment import StackEnvironment

class SyslinuxHelper:

    def __init__(self):
        self.log = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))
        self.env = StackEnvironment()

    def create_syslinux_stub(self, image_name, cmdline, kernel_filename, ramdisk_filename):
        """

        @param cmdline: kernel command line
        @param kernel_filename: path to kernel file 
        @param ramdisk_filename: path to ramdisk file
        @return glance image id
        """

        raw_fs_image = NamedTemporaryFile(delete=False)
        raw_image_name = raw_fs_image.name
        tmp_content_dir = None
        glance_image_id = None
        try:
            qcow2_image_name = "%s.qcow2" % raw_image_name

            # 200 MB sparse file
            self.log.debug("Creating sparse 200 MB file")
            outsize = 1024 * 1024 * 200
            raw_fs_image.truncate(outsize)
            raw_fs_image.close()

            # Partition, format and add DOS MBR
            g = guestfs.GuestFS()
            g.add_drive(raw_image_name)
            g.launch()
            g.part_disk("/dev/sda","msdos")
            g.part_set_mbr_id("/dev/sda",1,0xb)
            g.mkfs("vfat", "/dev/sda1")
            g.part_set_bootable("/dev/sda", 1, 1)
            dosmbr = open("/usr/share/syslinux/mbr.bin").read()
            ws = g.pwrite_device("/dev/sda", dosmbr, 0)
            if ws != len(dosmbr):
                raise Exception("Failed to write entire MBR")
            # Install syslinux
            g.syslinux("/dev/sda1")

            #Insert kernel, ramdisk and syslinux.cfg file
            tmp_content_dir = mkdtemp()

            kernel_dest = os.path.join(tmp_content_dir,"vmlinuz")
            shutil.copy(kernel_filename, kernel_dest)

            initrd_dest = os.path.join(tmp_content_dir,"initrd.img")
            shutil.copy(ramdisk_filename, initrd_dest)

            syslinux_conf="""default customhd
        timeout 30
        prompt 1
        label customhd
          kernel vmlinuz
          append initrd=initrd.img %s
        """ % (cmdline)
            
            f = open(os.path.join(tmp_content_dir, "syslinux.cfg"),"w")
            f.write(syslinux_conf)
            f.close()

            # copy the tmp content to the image
            g.mount_options ("", "/dev/sda1", "/")
            for filename in os.listdir(tmp_content_dir):
                g.upload(os.path.join(tmp_content_dir,filename),"/" + filename)
            g.sync()
            g.close()
            try:
                self.log.debug("Converting syslinux stub image from raw to qcow2")
                self._subprocess_check_output(["qemu-img","convert","-c","-O","qcow2",raw_image_name, qcow2_image_name])
                self.log.debug("Uploading syslinux qcow2 image to glance")
                glance_image_id = self.env.upload_image_to_glance(image_name, local_path=qcow2_image_name, format='qcow2')
            except Exception, e:
                self.log.debug("Exception while converting syslinux image to qcow2: %s" % e)
                self.log.debug("Uploading syslinux raw image to glance.")
                glance_image_id = self.env.upload_image_to_glance(image_name, local_path=raw_image_name, format='raw')

        finally:
            self.log.debug("Removing temporary file.")
            if os.path.exists(raw_image_name):
                os.remove(raw_image_name)
            if os.path.exists(qcow2_image_name):
                os.remove(qcow2_image_name)
            if tmp_content_dir:
                shutil.rmtree(tmp_content_dir)

        return glance_image_id

    ### Utility functions borrowed from Oz and lightly modified
    def _executable_exists(self, program):
        """
        Function to find out whether an executable exists in the PATH
        of the user.  If so, the absolute path to the executable is returned.
        If not, an exception is raised.
        """
        def is_exe(fpath):
            """
            Helper method to check if a file exists and is executable
            """
            return os.path.exists(fpath) and os.access(fpath, os.X_OK)

        if program is None:
            raise Exception("Invalid program name passed")

        fpath, fname = os.path.split(program)
        if fpath:
            if is_exe(program):
                return program
        else:
            for path in os.environ["PATH"].split(os.pathsep):
                exe_file = os.path.join(path, program)
                if is_exe(exe_file):
                    return exe_file

        raise Exception("Could not find %s" % (program))


    def _subprocess_check_output(self, *popenargs, **kwargs):
        """
        Function to call a subprocess and gather the output.
        Addresses a lack of check_output() prior to Python 2.7
        """
        if 'stdout' in kwargs:
            raise ValueError('stdout argument not allowed, it will be overridden.')
        if 'stderr' in kwargs:
            raise ValueError('stderr argument not allowed, it will be overridden.')

        self._executable_exists(popenargs[0][0])

        # NOTE: it is very, very important that we use temporary files for
        # collecting stdout and stderr here.  There is a nasty bug in python
        # subprocess; if your process produces more than 64k of data on an fd that
        # is using subprocess.PIPE, the whole thing will hang. To avoid this, we
        # use temporary fds to capture the data
        stdouttmp = TemporaryFile()
        stderrtmp = TemporaryFile()

        process = subprocess.Popen(stdout=stdouttmp, stderr=stderrtmp, *popenargs,
                                   **kwargs)
        process.communicate()
        retcode = process.poll()

        stdouttmp.seek(0, 0)
        stdout = stdouttmp.read()
        stdouttmp.close()

        stderrtmp.seek(0, 0)
        stderr = stderrtmp.read()
        stderrtmp.close()

        if retcode:
            cmd = ' '.join(*popenargs)
            raise Exception("'%s' failed(%d): %s" % (cmd, retcode, stderr), retcode)
        return (stdout, stderr, retcode)
