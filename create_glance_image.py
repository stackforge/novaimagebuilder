#!/usr/bin/python
#
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
def glance_upload(image_filename, creds = {'auth_url': None, 'password': None, 'strategy': 'noauth', 'tenant': None, 'username': None},
                  glance_url = None, token = None, name = 'Factory Test Image', disk_format = 'raw'):

    k = keystone_client.Client(username=creds['username'], password=creds['password'], tenant_name=creds['tenant'], auth_url=creds['auth_url'])

    if (k.authenticate()):
        #Connect to glance to upload the image
        glance = glance_client.Client("1", endpoint=glance_url, token=k.auth_token)
        image_data = open(image_filename, "r")
        image_meta = {'container_format': 'bare',
         'disk_format': disk_format,
         'is_public': True,
         'min_disk': 0,
         'min_ram': 0,
         'name': name,
         'data': image_data,
         'properties': {'distro': 'rhel'}}
        try:
            image = glance.images.create(name=name)
            print "Uploading to Glance"
            image.update(**image_meta)
            return image.id
        except Exception, e:
            raise
    else:
        raise Exception("Unable to authenticate into glance")

def ks_extract_bits(ksfile):
    # I briefly looked at pykickstart but it more or less requires you know the version of the
    # format you wish to use 
    # The approach below actually works as far back as RHEL5 and as recently as F18

    f = open(ksfile)
    lines = f.readlines()
    f.close()

    install_url = None
    console_password = None
    console_command = None
    poweroff = False
    distro = None

    for line in lines:
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

    return (install_url, console_password, console_cmd, poweroff)

def install_extract_bits(install_file, distro):
    if distro == "rpm":
        return ks_extract_bits(install_file)
    elif distro == "ubuntu":
        return preseed_extract_bits(install_file)
    else:
        return (None, None, None, None)

def preseed_extract_bits(preseedfile):

    f = open(preseedfile)
    lines = f.readlines()
    f.close()

    install_url = None
    console_password = None
    console_command = None
    poweroff = False

    for line in lines:

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

    f = open(install_script)
    lines = f.readlines()
    f.close()

    for line in lines:
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


def generate_boot_content(url, dest_dir, distro="rpm"):
    """
    Insert kernel, ramdisk and syslinux.cfg file in dest_dir
    source from url
    """
    # TODO: Add support for something other than rhel5

    if distro == "rpm":
        kernel_url = url + "images/pxeboot/vmlinuz"
        initrd_url = url + "images/pxeboot/initrd.img"
        cmdline = "ks=http://169.254.169.254/latest/user-data"
    elif distro == "ubuntu":
        kernel_url = url + "main/installer-amd64/current/images/netboot/ubuntu-installer/amd64/linux"
        initrd_url = url + "main/installer-amd64/current/images/netboot/ubuntu-installer/amd64/initrd.gz"
        cmdline = "append preseed/url=http://169.254.169.254/latest/user-data vga=788 debian-installer/locale=en_US console-setup/layoutcode=us netcfg/choose_interface=auto keyboard-configuration/layoutcode=us priority=critical --"

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

    print "Instance responding to pings - waiting up to 20 minutes for it to stop"
    # TODO: Automate this using subprocess
    if console_password:
        print "Install script contains a remove console directive with a password"
        print "You should be able to view progress with the following command:"
        print "$",
        print console_command % (instance_ip)
        print "When prompted for a password enter: %s" % (console_password)
        print "Note that it may take a few mintues for the server to become available"
    # Now wait for up to 20 minutes for it to stop ping replies for at least 30 seconds
    misses=0
    for i in range(120):
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
        print "Instance still pinging after 20 seconds - Assuming install failure"
        return

    print "Instance has stopped responding to ping for at least 30 seconds - assuming install is complete"
    return instance



def launch_and_wait(image_id, ks_file, creds, vnc_password):
    nova = nova_client.Client(creds['username'], creds['password'], creds['tenant'],
                              auth_url=creds['auth_url'], insecure=True)
    instance = nova.servers.create(instance_name, image_id, 2, userdata=working_ks, meta={})
    print "Started instance id (%s)" % (instance.id)

    #noping for Folsom - shutoff for newer
    #result = wait_for_shutoff(instance, nova)
    result = wait_for_noping(instance, nova, console_password, console_command)

    if not result:
        raise Exception("Timeout while waiting for install to finish")

    return result

def do_pw_sub(ks_file, admin_password):
    f = open(ks_file, "r")
    working_ks = ""
    for line in f:
        working_ks += Template(line).safe_substitute({ 'adminpw': admin_password })
    f.close()
    return working_ks

parser = argparse.ArgumentParser(description='Launch and snapshot a kickstart install using syslinux and Glance')
parser.add_argument('--auth-url', dest='auth_url', required=True,
                    help='URL for keystone authorization')
parser.add_argument('--username', dest='username', required=True,
                    help='username for keystone authorization')
parser.add_argument('--tenant', dest='tenant', required=True,
                    help='tenant for keystone authorization')
parser.add_argument('--password', dest='password', required=True,
                    help='password for keystone authorization')
parser.add_argument('--glance-url', dest='glance_url', required=True,
                    help='URL for glance service')
parser.add_argument('--admin-password', dest='admin_password', required=True,
                    help='administrator password - also used for optional remote access during install')
parser.add_argument('--install-tree-url', dest='install_tree_url',
                    help='URL for preferred network install tree (optional)')
parser.add_argument('--distro', dest='distro',
                    help='distro - must be "rpm" or "ubuntu (optional)"')
parser.add_argument('--image-name', dest='image_name',
                    help='name to assign newly created image (optional)')
parser.add_argument('ks_file',
                    help='kickstart/install-script file to use for install')
args = parser.parse_args()

# This is a string
working_kickstart = do_pw_sub(args.ks_file, args.admin_password)

distro = detect_distro(args.ks_file)
if args.distro:
    # Allow the command line distro to override our guess above
    distro = args.distro

(install_tree_url, console_password, console_command, poweroff) = install_extract_bits(args.ks_file, distro)
if args.install_tree_url:
    # Allow the specified tree to override anything extracted above
    install_tree_url = args.install_tree_url

if args.image_name:
    image_name = args.image_name
else:
    image_name = "Image from ks file: %s - Date: %s" % (os.path.basename(args.ks_file), strftime("%a, %d %b %Y %H:%M:%S +0000", gmtime()))

# Let's be nice and report as many error conditions as we can before exiting
error = False

if not install_tree_url:
    print "ERROR: no install tree URL specified and could not extract one from the kickstart/install-script"
    error =  True

if not distro:
    print "ERROR: no distro specified and could not guess based on the kickstart/install-script"
    error = True

if not poweroff:
    if distro == "rpm":
        print "ERROR: supplied kickstart file must contain a 'poweroff' line"
    elif distro == "ubuntu":
        print "ERROR: supplied preseed must contain a 'd-i debian-installer/exit/poweroff boolean true' line"
    error = True

if error:
    sys.exit(1)

# Artifact of borrowing factory code - pass this as a dict
creds = { 'username': args.username, 'tenant': args.tenant, 'password': args.password, 'auth_url': args.auth_url }

# Generate "blank" syslinux bootable mini-image
# This is the only step that strictly requires root access due to the need
# for a loopback mount to install the bootloader
generate_blank_syslinux()

# Take a copy of it
modified_image = "./syslinux_modified_%s.qcow2" % os.getpid()
shutil.copy("./syslinux.qcow2",modified_image)

# Generate the content to put into the image
tmp_content_dir = mkdtemp()
print "Collecting boot content for auto-install image"
generate_boot_content(install_tree_url, tmp_content_dir, distro)

# Copy in the kernel, initrd and conf files into the blank boot stub using libguestfs
print "Copying boot content into a bootable syslinux image"
copy_content_to_image(tmp_content_dir, modified_image)

# Upload the resulting image to glance
print "Uploading image to glance"
image_id = glance_upload(modified_image, creds = creds, glance_url = args.glance_url, 
                         name = "INSTALL for: %s" % (image_name), disk_format='qcow2')

print "Uploaded successfully as glance image (%s)" % (image_id)
# Launch the image with the provided ks.cfg as the user data
# Optionally - spawn a vncviewer to watch the install graphically
# Poll on image status until it is SHUTDOWN or timeout
print "Launching install image"
installed_instance = launch_and_wait(image_id, working_kickstart, os.path.basename(args.ks_file), creds, console_password, console_command)

# Take a snapshot of the now safely shutdown image
print "Taking snapshot of completed install"
finished_image_id = installed_instance.create_image(image_name)

print "Finished image snapshot ID is: %s" % (finished_image_id)
print "Finished image name is: %s" % (image_name)
#print "Cleaning up"
#print "Removing temp content dir"
#shutil.rmtree(tmp_content_dir)
#print "Removing install image"
##TODO:Note that thie is actually cacheable on a per-os-version basis
#os.remove(modified_image)
