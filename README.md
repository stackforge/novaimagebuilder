image-building-poc
==================

This is a very early demonstration of doing native OS installs inside of Nova.

To try it out

1) Install the requirements listed below
2) Replace all <FIXME> lines in glance_install.sh with the details of your OpenStack setup
3) Uncomment and edit the <FIXME> lines in the *.ks files to set your own root password and VNC password.

Then run:

./glance_install.sh fedora-18.ks

If all goes well, this will install Fedora 18 entirely within a Nova container using
the well known network install sources found in the kickstart file.

You can edit the details of the kickstart file as you wish.  The only requirement
at the moment is that the install must be "url" based.

It has only been run against the packstack Folsom distribution running on RHEL6.

Packstack details:

https://wiki.openstack.org/wiki/Packstack

It should work on newer OpenStack releases and more recent OSes including Fedora 17 and 18

It requires the following OpenStack packages (tested version listed):

python-glanceclient-0.5.1-1.el6.noarch
python-novaclient-2.10.0-2.el6.noarch
python-keystoneclient-0.1.3.27-1.el6.noarch

These are automatically installed when using Packstack

It also requires:

syslinux
qemu-img

And benefits from having "vncviewer" from the tigervnc package.



