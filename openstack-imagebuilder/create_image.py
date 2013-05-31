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
import sys
import shutil
from tempfile import mkdtemp

import argparse

from image_utils import *


def get_cli_arguments():
    parser = argparse.ArgumentParser(description='Launch and snapshot a kickstart install using syslinux and Glance')
    ospar = parser.add_argument_group('OpenStack Enviornment')
    ospar.add_argument('--auth-url', dest='auth_url', required=True, help='URL for keystone authorization')
    ospar.add_argument('--username', dest='username', required=True, help='username for keystone authorization')
    ospar.add_argument('--tenant', dest='tenant', required=True, help='tenant for keystone authorization')
    ospar.add_argument('--password', dest='password', required=True, help='password for keystone authorization')
    ospar.add_argument('--glance-url', dest='glance_url', required=True, help='URL for glance service')
    install_media_desc="""When one of these arguments is given the install environment will contain a second
    block device.  The image presented on this device can come from a URL, a file or
    a pre-existing volume snapshot.  You may only use one of these options at a time
    and you can only use them in conjunction with the 'create-volume' option."""
    install_media = parser.add_argument_group('Install Media', install_media_desc)
    install_media.add_argument('--install-media-url', dest='install_media_url',
                                help='Add an install media device using content at this URL')
    install_media.add_argument('--install-media-file', dest='install_media_file',
                                help='Add an install media device using this file as a media image')
    install_media.add_argument('--install-media-snapshot', dest='install_media_snapshot',
                                help='Add an install media device by creating a volume from this snapshot id')
    instpar = parser.add_argument_group('Installation Parameters')
    instpar.add_argument('--root-password', dest='admin_password', required=True,
                    help='root password for the resulting image - also used for optional remote access during install')
    instpar.add_argument('--create-volume', dest='create_volume', action='store_true', default=False,
                            help='Create a volume snapshot instead of the default Glance snapshot (optional)')
    instpar.add_argument('--install-volume-size', dest='install_volume_size', default=10,
                            help='Size of the install destination volume in GB (default: 10)')
    instpar.add_argument('--install-tree-url', dest='install_tree_url',
                             help='URL for preferred network install tree (optional)')
    instpar.add_argument('--distro', dest='distro', help='distro - must be "rpm" or "ubuntu" (optional)')
    instpar.add_argument('--image-name', dest='image_name', help='name to assign newly created image (optional)')
    instpar.add_argument('--leave-mess', dest='leave_mess', action='store_true', default=False,
                        help='Do not clean up local or remote artifacts when finished or when an error is encountered')
    parser.add_argument('ks_file', help='kickstart/install-script file to use for install')
    return parser.parse_args()

def create_image(args):
    # This is a string
    working_kickstart = do_pw_sub(args.ks_file, args.admin_password)

    distro = detect_distro(working_kickstart)
    if args.distro:
        # Allow the command line distro to override our guess above
        distro = args.distro

    (install_tree_url, console_password, console_command, poweroff) = install_extract_bits(working_kickstart, distro)
    if args.install_tree_url:
        # Allow the specified tree to override anything extracted above
        install_tree_url = args.install_tree_url

    if args.image_name:
        image_name = args.image_name
    else:
        image_name = "Image from ks file: %s - Date: %s" % (os.path.basename(args.ks_file), strftime("%a, %d %b %Y %H:%M:%S +0000", gmtime()))

    # Let's be nice and report as many error conditions as we can before exiting
    error = False

    if (args.install_media_url or args.install_media_file or args.install_media_snapshot) and not args.create_volume:
        print "ERROR: You can only use install media when creating a volume snapshot image using the --create-volume option."
        error = True

    if (args.install_media_url and args.install_media_file) or (args.install_media_file and args.install_media_snapshot) or \
       (args.install_media_url and args.install_media_snapshot):
        print "ERROR: You may only specify a single install media source"
        error = True

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

    # We start creating artifacts here - cleanup in finally
    modified_image = None # filename
    tmp_content_dir = None # directory
    install_image = None # Nova image object
    install_media_volume=None # cinder volume object
    install_media_snapshot_id=None # UUID string
    installed_instance = None # Nova instance object
    finished = False # silly marker
    retcode = 0

    try:
        # Artifact of borrowing factory code - pass this as a dict
        creds = { 'username': args.username, 'tenant': args.tenant, 'password': args.password, 'auth_url': args.auth_url }

        # Generate "blank" syslinux bootable mini-image
        # This is the only step that strictly requires root access due to the need
        # for a loopback mount to install the bootloader
        generate_blank_syslinux()

        # Take a copy of it
        if args.create_volume:
            disk_format = 'raw'
            modified_image = "./syslinux_modified_%s.raw" % os.getpid()
            try:
                subprocess_check_output(["qemu-img","convert","-O","raw","./syslinux.qcow2",modified_image])
            except:
                print "Exception while converting image to raw"
                raise
        else:
            disk_format = 'qcow2'
            modified_image = "./syslinux_modified_%s.qcow2" % os.getpid()
            shutil.copy("./syslinux.qcow2",modified_image)

        # Generate the content to put into the image
        tmp_content_dir = mkdtemp()
        print "Collecting boot content for auto-install image"
        generate_boot_content(install_tree_url, tmp_content_dir, distro, args.create_volume)

        # Copy in the kernel, initrd and conf files into the blank boot stub using libguestfs
        print "Copying boot content into a bootable syslinux image"
        copy_content_to_image(tmp_content_dir, modified_image)

        # Upload the resulting image to glance
        print "Uploading image to glance"
        install_image = glance_upload(image_filename = modified_image, image_url = None, creds = creds, glance_url = args.glance_url,
                              name = "INSTALL for: %s" % (image_name), disk_format=disk_format)

        print "Uploaded successfully as glance image (%s)" % (install_image.id)

        install_volume=None
        # TODO: Make volume size configurable
        if args.create_volume:
            print "Converting Glance install image to a Cinder volume"
            install_volume = volume_from_image(install_image.id, creds, args.glance_url, volume_size = args.install_volume_size)


        if args.install_media_url or args.install_media_file:
            if args.install_media_url:
                print "Generating Glance image from URL: %s" % (args.install_media_url)
                install_media_image = glance_upload(image_filename = None, image_url = args.install_media_url,
                    creds = creds, glance_url = args.glance_url, name = "FromURL: %s" % (args.install_media_url),
                    disk_format='raw')
            else:
                print "Generating Glance image from file: %s" % (args.install_media_file)
                install_media_image = glance_upload(image_filename = args.install_media_file, image_url = None,
                    creds = creds, glance_url = args.glance_url, name = os.path.basename(args.install_media_file),
                    disk_format='raw')

            print "Generating volume from image (%s)" % (install_media_image.id)
            install_media_volume = volume_from_image(install_media_image.id, creds, args.glance_url)
            print "Generating snapshot of volume (%s) to allow install media reuse" % (install_media_volume.id)
            install_media_snapshot = snapshot_from_volume(install_media_volume.id, creds)
            install_media_snapshot_id = install_media_snapshot.id
            print "#### Future installs can reference this snapshot with the following argument:"
            print "    --install-media-snapshot %s" % install_media_snapshot_id
        elif args.install_media_snapshot:
            print "Generating working volume from snapshot (%s)" % (args.install_media_snapshot)
            install_media_snapshot_id = args.install_media_snapshot
            install_media_volume = volume_from_snapshot(args.install_media_snapshot, creds)

        # Launch the image with the provided ks.cfg as the user data
        # Optionally - spawn a vncviewer to watch the install graphically
        # Poll on image status until it is SHUTDOWN or timeout
        print "Launching install image"
        installed_instance = launch_and_wait(install_image, install_volume, install_media_volume, working_kickstart,
                                             os.path.basename(args.ks_file), creds, console_password, console_command)

        # Take a snapshot of the now safely shutdown image
        # For volume snapshots we must terminate the instance first then snapshot
        # For glance/image snapshots we must _not_ terminate the instance until the snapshot is complete
        print "Taking snapshot of completed install"
        if args.create_volume:
            print "Terminating instance (%s) in preparation for taking a snapshot of the root volume" % (installed_instance.id)
            terminate_instance(installed_instance.id, creds)
            installed_instance = None
            finished_image_snapshot = snapshot_from_volume(install_volume.id, creds)
            print "Volume-based image available from snapshot ID: %s" % (finished_image_snapshot.id)
            print "Finished snapshot name is: %s" % (finished_image_snapshot.display_name)
            finished = True
        else:
            finished_image_id = installed_instance.create_image(image_name)
            print "Waiting for glance image snapshot to complete"
            wait_for_glance_snapshot(finished_image_id, creds, args.glance_url)
            print "Terminating instance (%s) now that snapshot is complete" % (installed_instance.id)
            terminate_instance(installed_instance.id, creds)
            installed_instance = None
            print "Finished image snapshot ID is: %s" % (finished_image_id)
            print "Finished image name is: %s" % (image_name)
            finished = True

    except Exception as e:
        print "Uncaught exception encountered during install"
        print str(e)
        retcode = 1

    finally:
        if args.leave_mess:
            print "Leaving a mess - this includes local files, local dirs, remote images, remote volumes and remote snapshots"
            sys.exit(retcode)

        print "Cleaning up"

        try:
            if tmp_content_dir:
                print "Removing boot content dir"
                shutil.rmtree(tmp_content_dir)

            if modified_image:
                print "Removing install image %s" % (modified_image)
                #TODO:Note that thie is actually cacheable on a per-os-version basis
                os.remove(modified_image)

            if installed_instance:
                # Note that under normal operation this is terminated when completing the snapshot process
                print "Terminating install instance (%s)" % (installed_instance.id)
                terminate_instance(installed_instance.id, creds)

            if install_image:
                print "Deleting Glance image (%s) used to launch install" % (install_image.id)
                install_image.delete()

            if install_media_volume:
                print "Removing working volume containing install media"
                print "Snapshot (%s) remains available for future use" % (install_media_snapshot_id)
                install_media_volume.delete()
        except:
            print "WARNING: Exception while attempting to clean up - we may have left a mess"
            retcode = 1

        # For usability - reprint the most important bits from above as the last output
        if finished:
            print "FINISHED!"
            print
            print "Image Details:"
            if args.create_volume:
                print "Volume snapshot name: %s" % (finished_image_snapshot.display_name)
                print "ID: %s" % (finished_image_snapshot.id)
            else:
                print "Glance image name: %s" % (image_name)
                print "ID: %s" % (finished_image_id)

        sys.exit(retcode)

if __name__ == '__main__':
    create_image(get_cli_arguments())