Building OS images in NOVA
==========================

This is an early demonstration of a new image building approach for OpenStack.

It is a command line tool that builds working OpenStack images by
running Anaconda or other native installers within Nova.  In its simplest form 
it requires only a kickstart or preseed file as input.  All of the heavy lifting
is done inside of OpenStack instances.

Early discussion of this approach can be found here:

https://wiki.openstack.org/wiki/NovaImageBuilding

It has been developed and tested on RHEL6 and the Folsom OpenStack release installed
using packstack.  However, it should work with newer host OSes and newer OpenStack releases.

To try it out install the requirements listed below then run commands like this:

(substituting the details of your own OpenStack environment where indicated)


#### Create a Fedora 18 JEOS image in glance using a network install

    ./create_image.py --username admin --tenant admin --password password --auth-url http://10.10.10.10:5000/v2.0 \
                      --glance-url http://10.10.10.10:9292/ --root-password myrootpw install_scripts/fedora-18-jeos.ks

#### Create an Ubuntu 12.04 image in glance using a network install

    ./create_image.py --username admin --tenant admin --password password --auth-url http://10.10.10.10:5000/v2.0 \
                      --glance-url http://10.10.10.10:9292/ --root-password myrootpw \
                        install_scripts/ubuntu-12.04-jeos.preseed

#### Create a Fedora 18 JEOS image as a volume snapshot using a network install

    ./create_image.py --username admin --tenant admin --password password --auth-url http://10.10.10.10:5000/v2.0 \
                      --glance-url http://10.10.10.10:9292/ --root-password myrootpw --create-volume \
                        install_scripts/fedora-18-jeos.ks

#### Create a Fedora 18 JEOS image as a volume snapshot using an install DVD pulled from a Fedora mirror

    ./create_image.py --username admin --tenant admin --password password --auth-url http://10.10.10.10:5000/v2.0 \
                      --create-volume --install-media-url \
                        http://mirror.pnl.gov/fedora/linux/releases/18/Fedora/x86_64/iso/Fedora-18-x86_64-DVD.iso \
                      --install-tree-url \
                        http://mirror.pnl.gov/fedora/linux/releases/18/Fedora/x86_64/os/ \
                      --glance-url http://10.10.10.10:9292/ --root-password myrootpw install_scripts/fedora-18-jeos-DVD.ks

#### Create a Fedora 18 JEOS image as a volume snapshot by re-using the DVD volume snapshot created above

    ./create_image.py --username admin --tenant admin --password password --auth-url http://10.10.10.10:5000/v2.0 \
                      --create-volume --install-media-snapshot <SNAPSHOT_ID_REPORTED_ABOVE> \
                      --install-tree-url \
                        http://mirror.pnl.gov/fedora/linux/releases/18/Fedora/x86_64/os/ \
                      --glance-url http://10.10.10.10:9292/ --root-password myrootpw install_scripts/fedora-18-jeos-DVD.ks


### What does this do?

The script generates a small syslinux-based bootable image that is used
to start unattended Anaconda or Ubuntu installations.  It contains only 
the initrd and vmlinuz from the install source and a syslinux.cfg file.
The installer then writes over this minimal image.

The kickstart/preseed files are passed to the installers via OpenStack 
user-data and the appropriate kernel command line parameters in the 
syslinux configuration file.

The script uploads this bootstrapping image to glance, launches it, and
waits for it to shut down.  If shutdown occurs within the timeout period
we assume that the installer has finished and take a snapshot of the current
instance state, which is the completed install.

You can monitor progress via Anaconda's VNC support, which is enabled
in the example kickstarts under the "install_scripts" directory. The 
script reports the instance IP and gives the exact invocation of 
vncviewer that is needed to connect to the install.

You can do something similar with an Ubuntu install using an SSH console.
However, this feature stops the installation and waits for user input so
it is commented out in the example preseed files.  See instructions in
the comments for how to enable this.


### What operating systems can it support?

The install_scripts contains known-working kickstart and preseed files for:

Fedora 18, Fedora 17, RHEL 6.4, RHEL 5.9

Ubuntu 12.10, 12.04 and 10.04

This approach should work as far back as Fedora 10 and RHEL 4 U8 and on
other Linux variants including SLES.


### Volume Based Images

By default the script will build a Glance backed image.  If passed the
--create-volume option it will instead build a volume backed "snapshot"
image.


### ISO Install Media

It also contains initial support for presenting installer ISO images as
a source for installation packages.  This support has only been tested for
Fedora 18 for the moment.  It is somewhat limited because OpenStack currently
only allows these images to be mapped into the instance as "normal"
block devices, rather than CDROMs.  Not all installers can deal with this.

(Note: When using the install media volume feature you must still pass
a "--install-tree-url" option as demonstrated in the examples above.  This
is necessary to allow the script to retrieve the install kernel and ramdisk
without having to pull down a copy of the entire ISO.)

### Requirements

This script has been tested with the following OpenStack client packages:

* python-glanceclient-0.5.1-1.el6.noarch
* python-novaclient-2.10.0-2.el6.noarch
* python-keystoneclient-0.1.3.27-1.el6.noarch
* python-cinderclient-0.2.26-1.el6.noarch

Newer and older versions may work.

It also requires:

* python-libguestfs
* syslinux
* qemu-img

If you want to view ongoing installs over VNC you will need:

* tigervnc


### TODO

Better documentation

Better error detection and reporting

Support for more operating systems.

Support for sourcing install scripts through libosinfo

Support for enhanced block device mapping when it becomes available

Support for direct booting of kernel/ramdisk/cmdline combinations when/if it is added to Nova

Improved detection of install success or failure

Support for caching of self-install images
