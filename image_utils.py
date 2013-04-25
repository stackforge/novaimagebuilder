#!/usr/bin/python
#
#   Copyright 2013 Red Hat, Inc.
#   Portions Copyright (C) 2010,2011,2012  Chris Lalancette <clalance@redhat.com>
#   Portions Copyright (C) 2012,2013  Chris Lalancette <clalancette@gmail.com>
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

import os
import os.path
import sys
import guestfs
import pycurl
import shutil
import subprocess
import argparse
import re
from string import Template
from tempfile import mkdtemp, NamedTemporaryFile, TemporaryFile
from glanceclient import client as glance_client
from cinderclient import client as cinder_client
from keystoneclient.v2_0 import client as keystone_client
from novaclient.v1_1 import client as nova_client
from time import sleep, gmtime, strftime
from ping import do_one


### Utility functions borrowed from Oz and lightly modified
def executable_exists(program):
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


def subprocess_check_output(*popenargs, **kwargs):
    """
    Function to call a subprocess and gather the output.
    Addresses a lack of check_output() prior to Python 2.7
    """
    if 'stdout' in kwargs:
        raise ValueError('stdout argument not allowed, it will be overridden.')
    if 'stderr' in kwargs:
        raise ValueError('stderr argument not allowed, it will be overridden.')

    executable_exists(popenargs[0][0])

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


def http_download_file(url, filename):
    """
    Function to download a file from url to filename
    """

    def _data(buf):
        """
        Function that is called back from the pycurl perform() method to
        actually write data to disk.
        """
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
### End of borrowed Oz functions


### Borrowed from Image Factory OpenStack plugin
def glance_upload(image_filename = None, image_url = None, creds = {'auth_url': None, 'password': None, 'strategy': 'noauth', 'tenant': None, 'username': None},
                  glance_url = None, token = None, name = 'Factory Test Image', disk_format = 'raw'):

    k = keystone_client.Client(username=creds['username'], password=creds['password'], tenant_name=creds['tenant'], auth_url=creds['auth_url'])

    if (k.authenticate()):
        #Connect to glance to upload the image
        glance = glance_client.Client("1", endpoint=glance_url, token=k.auth_token)
        image_meta = {'container_format': 'bare',
         'disk_format': disk_format,
         'is_public': True,
         'min_disk': 0,
         'min_ram': 0,
         'name': name,
         'properties': {'distro': 'rhel'}}
        try:
            image = glance.images.create(name=name)
            if image_filename:
                image_data = open(image_filename, "r")
                image_meta['data'] = image_data
                print "Uploading to Glance"
                image.update(**image_meta)
            elif image_url:
                image_meta['copy_from'] = image_url
                image.update(**image_meta)
                print "Waiting for Glance to finish creating image from URL: %s" % (image_url)
                while (image.status != 'active'):
                    if image.status == 'killed':
                        raise Exception("Glance error while waiting for image to generate from URL")
                    print '.',
                    sys.stdout.flush()
                    sleep(10)
                    image=glance.images.get(image.id)
            return image
        except Exception, e:
            raise
    else:
        raise Exception("Unable to authenticate into glance")

def volume_from_image(image_id, creds, glance_url, volume_size = None):
    k = keystone_client.Client(username=creds['username'], password=creds['password'], tenant_name=creds['tenant'], auth_url=creds['auth_url'])
    if not k.authenticate():
        raise Exception("Could not authenticate into keystone")

    glance = glance_client.Client("1", endpoint=glance_url, token=k.auth_token)
    cinder = cinder_client.Client('1', creds['username'], creds['password'], creds['tenant'], creds['auth_url'])
    try:
        image = glance.images.get(image_id)
    except:
        raise Exception("Could not find Glance image with id" % (image_id))
   
    # Unclear if this is strictly needed
    # If size is not explicitly set then set it based on the image size
    # TODO: Check if we even have to set a size when pulling from an image 
    if not volume_size:
        # Gigabytes rounded up
        volume_size = int(image.size/(1024*1024*1024)+1)

    print "Starting asyncronous copying to Cinder"
    volume = cinder.volumes.create(volume_size, display_name=image.name, imageRef=image.id)
    while (volume.status != 'available'):
        print "Waiting for volume to be ready ... current status (%s)" % (volume.status)
        sleep(5)
        volume = cinder.volumes.get(volume.id)
        if (volume.status == 'error'):
            raise Exception('Error converting image to volume')
    return volume

def snapshot_from_volume(volume_id, creds):
    cinder = cinder_client.Client('1', creds['username'], creds['password'], creds['tenant'], creds['auth_url'])
    volume = volume=cinder.volumes.get(volume_id)
    snapshot = cinder.volume_snapshots.create(volume.id,False,volume.display_name,volume.display_description)
    while (snapshot.status != 'available'):
        print "Waiting for snapshot to be ready ... current status (%s)" % (snapshot.status)
        sleep(5)
        snapshot = cinder.volume_snapshots.get(snapshot.id)
        if snapshot.status == 'error':
            raise Exception('Error while taking volume snapshot')
    return snapshot                   

def volume_from_snapshot(snapshot_id, creds):
    cinder = cinder_client.Client('1', creds['username'], creds['password'], creds['tenant'], creds['auth_url'])
    snapshot = cinder.volume_snapshots.get(snapshot_id)
    volume = cinder.volumes.create(size=None, snapshot_id=snapshot_id, display_name=snapshot.display_name,
                                   display_description=snapshot.display_description)
    while (volume.status != 'available'):
        print "Waiting for volume to be ready ... current status (%s)" % (volume.status)
        sleep(5)
        volume = cinder.volumes.get(volume.id)
        if volume.status == 'error':
            raise Exception('Error while taking volume snapshot')
    return volume

def ks_extract_bits(ksfile):
    # I briefly looked at pykickstart but it more or less requires you know the version of the
    # format you wish to use 
    # The approach below actually works as far back as RHEL5 and as recently as F18

    install_url = None
    console_password = None
    console_command = None
    poweroff = False
    distro = None

    for line in ksfile.splitlines():
        # Install URL lines look like this
        # url --url=http://download.devel.redhat.com/released/RHEL-5-Server/U9/x86_64/os/
        m = re.match("url.*--url=(\S+)", line)
        if m and len(m.groups()) == 1:
            install_url = m.group(1)
            continue

        # VNC console lines look like this
        # Inisist on a password being set
        # vnc --password=vncpasswd    
        m = re.match("vnc.*--password=(\S+)", line)
        if m and len(m.groups()) == 1:
            console_password = m.group(1)
            console_command = "vncviewer %s:1"
            continue

        # SSH console lines look like this
        # Inisist on a password being set
        # ssh --password=sshpasswd    
        m = re.match("ssh.*--password=(\S+)", line)
        if m and len(m.groups()) == 1:
            console_password = m.group(1)
            console_command = "ssh root@%s"
            continue

        # We require a poweroff after install to detect completion - look for the line
        if re.match("poweroff", line):
            poweroff=True
            continue

    return (install_url, console_password, console_command, poweroff)

def install_extract_bits(install_file, distro):
    if distro == "rpm":
        return ks_extract_bits(install_file)
    elif distro == "ubuntu":
        return preseed_extract_bits(install_file)
    else:
        return (None, None, None, None)

def preseed_extract_bits(preseedfile):

    install_url = None
    console_password = None
    console_command = None
    poweroff = False

    for line in preseedfile.splitlines():

        # Network console lines look like this:
        # d-i network-console/password password r00tme
        m = re.match("d-i\s+network-console/password\s+password\s+(\S+)", line)
        if m and len(m.groups()) == 1:
            console_password = m.group(1)
            console_command = "ssh installer@%s\nNote that you MUST connect to this session for the install to continue\nPlease do so now\n"
            continue

        # Preseeds do not need to contain any explicit pointers to network install sources
        # Users can specify the install-url on the cmd line or provide a hint in a
        # comment line that looks like this:
        # "#ubuntu_baseurl=http://us.archive.ubuntu.com/ubuntu/dists/precise/"
        m = re.match("#ubuntu_baseurl=(\S+)", line)
        if m and len(m.groups()) == 1:
            install_url = m.group(1)

        # A preseed poweroff directive looks like this:
        # d-i debian-installer/exit/poweroff boolean true
        if re.match("d-i\s+debian-installer/exit/poweroff\s+boolean\s+true", line):
            poweroff=True
            continue
  
    return (install_url, console_password, console_command, poweroff)


def detect_distro(install_script):

    for line in install_script.splitlines():
        if re.match("d-i\s+debian-installer", line):
            return "ubuntu"
        elif re.match("%packages", line):
            return "rpm"

    return None


def generate_blank_syslinux():
    # Generate syslinux.qcow2 in working directory if it isn't already there
    if os.path.isfile("./syslinux.qcow2"):
        print "Found a syslinux.qcow2 image in the working directory - using it"
        return

    print "Generating an empty bootable syslinux image as ./syslinux.qcow2"
    raw_fs_image = NamedTemporaryFile(delete=False)
    raw_image_name = raw_fs_image.name
    try:
        output_image_name = "./syslinux.qcow2"

        # 200 MB sparse file
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
        g.sync()
        g.close()

        # Install syslinux - this is the ugly root-requiring part
        gotloop = False
        for n in range(4):
            # If this has a nonzero return code we will take the exception
            (stdout, stderr, retcode) = subprocess_check_output(["losetup","-f"])
            loopdev = stdout.rstrip()
            # Race - Try it a few times and then give up
            try:
                subprocess_check_output(["losetup",loopdev,raw_image_name])
            except:
                sleep(1)
                continue
            gotloop = True
            break

        if not gotloop:
            raise Exception("Failed to setup loopback")

        loopbase = os.path.basename(loopdev)

        try:
            subprocess_check_output(["kpartx","-a",loopdev])
            # On RHEL6 there seems to be a short delay before the mappings actually show up
            sleep(5)
            subprocess_check_output(["syslinux", "/dev/mapper/%sp1" % (loopbase)])
            subprocess_check_output(["kpartx", "-d", loopdev])
            subprocess_check_output(["losetup", "-d", loopdev])
        except:
            print "Exception while executing syslinux install commands."
            raise

        try:
            subprocess_check_output(["qemu-img","convert","-c","-O","qcow2",raw_image_name,output_image_name])
        except:
            print "Exception while converting image to qcow2"

    finally:
        pass
        # Leave a mess for debugging for now
        #os.remove(raw_image_name)


def generate_boot_content(url, dest_dir, distro, create_volume):
    """
    Insert kernel, ramdisk and syslinux.cfg file in dest_dir
    source from url
    """
    # TODO: Add support for something other than rhel5

    if distro == "rpm":
        kernel_url = url + "images/pxeboot/vmlinuz"
        initrd_url = url + "images/pxeboot/initrd.img"
        if create_volume:
            # NOTE: RHEL5 and other older Anaconda versions do not support specifying the CDROM device - use with caution
            cmdline = "ks=http://169.254.169.254/latest/user-data repo=cdrom:/dev/vdb"
        else:
            cmdline = "ks=http://169.254.169.254/latest/user-data"
    elif distro == "ubuntu":
        kernel_url = url + "main/installer-amd64/current/images/netboot/ubuntu-installer/amd64/linux"
        initrd_url = url + "main/installer-amd64/current/images/netboot/ubuntu-installer/amd64/initrd.gz"
        cmdline = "append preseed/url=http://169.254.169.254/latest/user-data debian-installer/locale=en_US console-setup/layoutcode=us netcfg/choose_interface=auto keyboard-configuration/layoutcode=us priority=critical --"

    kernel_dest = os.path.join(dest_dir,"vmlinuz")
    http_download_file(kernel_url, kernel_dest)

    initrd_dest = os.path.join(dest_dir,"initrd.img")
    http_download_file(initrd_url, initrd_dest)

    syslinux_conf="""default customhd
timeout 30
prompt 1
label customhd
  kernel vmlinuz
  append initrd=initrd.img %s
""" % (cmdline)
    
    f = open(os.path.join(dest_dir, "syslinux.cfg"),"w")
    f.write(syslinux_conf)
    f.close()


def copy_content_to_image(contentdir, target_image):
    g = guestfs.GuestFS()
    g.add_drive(target_image)
    g.launch()
    g.mount_options ("", "/dev/sda1", "/")
    for filename in os.listdir(contentdir):
        g.upload(os.path.join(contentdir,filename),"/" + filename)
    g.sync()
    g.close()

def wait_for_shutoff(instance, nova):
    for i in range(1200):
        status = nova.servers.get(instance.id).status
        if status == "SHUTOFF":
            print "Instance has entered SHUTOFF state"
            return instance
        if i % 10 == 0:
            print "Waiting for instance status SHUTOFF - current status (%s): %d/1200" % (status, i)
        sleep(1)

def wait_for_noping(instance, nova, console_password, console_command):
    # pre-grizzly releases are slow to notice an instance is shut off - see thread:
    # http://lists.openstack.org/pipermail/openstack-dev/2013-January/004501.html
    #
    # This is an imperfect workaround using pings

    from ping import do_one
    print "Warning - using ping to monitor progress - this is a crude shutdown detection scheme"

    # It is unclear where in the instance lifecycle this first becomes available
    # Just try for a few minutes then give up
    instance_ip = None
    for i in range(18):
        try:
            instance = nova.servers.get(instance.id)
            print "Instance status: %s" % (instance.status)
            # First IP for the first key returned in the networks dict
            instance_ip = instance.networks[instance.networks.keys()[0]][0]
            break
        except:
            sleep(10)
            pass

    if not instance_ip:
        raise Exception("Unable to determine instance IP after 3 minutes")

    print "Using instance ip: %s" % (instance_ip)
    print "Waiting 3 minutes for instance to respond to pings"
    # First wait up to 3 minutes for ping to _start_ replying
    started = False
    for i in range(18):
        print '.',
        sys.stdout.flush()
        if do_one(instance_ip, 10):
            started = True
            break
    print ''

    if not started:
        raise Exception("Instance at IP (%s) failed to start after 3 minutes." % (instance_ip) )

    print "Instance responding to pings - waiting up to 40 minutes for it to stop"
    # TODO: Automate this using subprocess
    if console_password:
        print "Install script contains a remove console directive with a password"
        print "You should be able to view progress with the following command:"
        print "$",
        print console_command % (instance_ip)
        print "password: %s" % (console_password)
        print
        print "Note that it may take a few mintues for the server to become available"
    misses=0
    for i in range(240):
        print '.',
        sys.stdout.flush()
        if do_one(instance_ip, 10):
            misses=0
            sleep(10)
        else:
            print '-',
            sys.stdout.flush()
            misses += 1
            if misses == 4:
                break
    print ''

    if misses != 4:
        print "Instance still pinging after 40 minutes - Assuming install failure"
        return

    print "Instance has stopped responding to ping for at least 30 seconds - assuming install is complete"
    return instance


def launch_and_wait(image, image_volume, install_media_volume, working_ks, instance_name, creds, console_password, console_command):
    if install_media_volume and image_volume:
        block_device_mapping = {'vda': image_volume.id + ":::0", 'vdb': install_media_volume.id + ":::0"}
    elif image_volume:
        block_device_mapping = {'vda': image_volume.id + ":::0" }
    else:
        block_device_mapping = None

    nova = nova_client.Client(creds['username'], creds['password'], creds['tenant'],
                              auth_url=creds['auth_url'], insecure=True)
    instance = nova.servers.create(instance_name, image.id, 2, userdata=working_ks, meta={},
                                   block_device_mapping = block_device_mapping)
    print "Started instance id (%s)" % (instance.id)

    #noping for Folsom - shutoff for newer
    #result = wait_for_shutoff(instance, nova)
    result = wait_for_noping(instance, nova, console_password, console_command)

    if not result:
        raise Exception("Timeout while waiting for install to finish")

    return result


def terminate_instance(instance_id, creds):
    nova = nova_client.Client(creds['username'], creds['password'], creds['tenant'],
                              auth_url=creds['auth_url'], insecure=True)
    instance = nova.servers.get(instance_id)
    instance.delete()
    print "Waiting for instance id (%s) to be terminated/delete" % (instance_id)
    while True:
        print "Current instance status: %s" % (instance.status)
        sleep(2)
        try:
            instance = nova.servers.get(instance_id)
        except Exception as e:
            print "Got exception (%s) assuming deletion complete" % (e)
            break

def wait_for_glance_snapshot(image_id, creds, glance_url):
    k = keystone_client.Client(username=creds['username'], password=creds['password'], tenant_name=creds['tenant'], auth_url=creds['auth_url'])
    if not k.authenticate():
        raise Exception("Unable to authenticate into Keystone")

    glance = glance_client.Client("1", endpoint=glance_url, token=k.auth_token)
    image = glance.images.get(image_id)
    print "Waiting for glance image id (%s) to become active" % (image_id)
    while True:
        print "Current image status: %s" % (image.status)
        sleep(2)
        image = glance.images.get(image.id)
        if image.status == "error":
            raise Exception("Image entered error status while waiting for completion")
        elif image.status == 'active':
            break

def do_pw_sub(ks_file, admin_password):
    f = open(ks_file, "r")
    working_ks = ""
    for line in f:
        working_ks += Template(line).safe_substitute({ 'adminpw': admin_password })
    f.close()
    return working_ks

def add_install_media_url(ks_string, install_media_url):
    return "url --url=%s\n%s" % (install_media_url, ks_string)

def add_power_off(ks_string):
    return "%s\n%s" % (ks_string[:-6], "poweroff\n%end")
