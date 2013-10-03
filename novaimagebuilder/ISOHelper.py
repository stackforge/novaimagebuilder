# Copyright (C) 2010,2011  Chris Lalancette <clalance@redhat.com>
# Copyright (C) 2012,2013  Chris Lalancette <clalancette@gmail.com>
# Copyright (C) 2013 Ian McLeod <imcleod@redhat.com>

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation;
# version 2.1 of the License.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
import struct
import shutil
import os
import guestfs
import logging
import tempfile
import subprocess
import stat

class ISOHelper():
    """
    Class for assisting with the respin of install ISOs.
    At present the only purpose for this class is to allow the injection of a custom
    autounattend.xml file to Windows install isos.
    
    This class is largely derived from the Guest.py, Windows.py and ozutil.py files
    from the Oz project by Chris Lalancette:

    https://github.com/clalancette/oz
    """

    def __init__(self, original_iso, arch):
        self.log = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))
        self.orig_iso = original_iso
        self.arch = arch
        self.winarch = arch
        if self.winarch == "x86_64":
            self.winarch = "amd64"
        self.iso_contents = tempfile.mkdtemp()


    def _validate_primary_volume_descriptor(self, cdfd):
        """
        Method to extract the primary volume descriptor from a CD.
        """
        # check out the primary volume descriptor to make sure it is sane
        cdfd.seek(16*2048)
        fmt = "=B5sBB32s32sQLL32sHHHH"
        (desc_type, identifier, version, unused1, system_identifier, volume_identifier, unused2, space_size_le, space_size_be, unused3, set_size_le, set_size_be, seqnum_le, seqnum_be) = struct.unpack(fmt, cdfd.read(struct.calcsize(fmt)))

        if desc_type != 0x1:
            raise Exception("Invalid primary volume descriptor")
        if identifier != "CD001":
            raise Exception("invalid CD isoIdentification")
        if unused1 != 0x0:
            raise Exception("data in unused field")
        if unused2 != 0x0:
            raise Exception("data in 2nd unused field")

    def _geteltorito(self, outfile):
        """
        Method to extract the El-Torito boot sector off of a CD and write it
        to a file.
        """
        if outfile is None:
            raise Exception("output file is None")

        cdfd = open(self.orig_iso, "r")

        self._validate_primary_volume_descriptor(cdfd)

        # the 17th sector contains the boot specification and the offset of the
        # boot sector
        cdfd.seek(17*2048)

        # NOTE: With "native" alignment (the default for struct), there is
        # some padding that happens that causes the unpacking to fail.
        # Instead we force "standard" alignment, which has no padding
        fmt = "=B5sB23s41sI"
        (boot, isoIdent, version, toritoSpec, unused, bootP) = struct.unpack(fmt,
                                                                             cdfd.read(struct.calcsize(fmt)))
        if boot != 0x0:
            raise Exception("invalid CD boot sector")
        if isoIdent != "CD001":
            raise Exception("invalid CD isoIdentification")
        if version != 0x1:
            raise Exception("invalid CD version")
        if toritoSpec != "EL TORITO SPECIFICATION":
            raise Exception("invalid CD torito specification")

        # OK, this looks like a bootable CD.  Seek to the boot sector, and
        # look for the header, 0x55, and 0xaa in the first 32 bytes
        cdfd.seek(bootP*2048)
        fmt = "=BBH24sHBB"
        bootdata = cdfd.read(struct.calcsize(fmt))
        (header, platform, unused, manu, unused2, five, aa) = struct.unpack(fmt,
                                                                            bootdata)
        if header != 0x1:
            raise Exception("invalid CD boot sector header")
        if platform != 0x0 and platform != 0x1 and platform != 0x2:
            raise Exception("invalid CD boot sector platform")
        if unused != 0x0:
            raise Exception("invalid CD unused boot sector field")
        if five != 0x55 or aa != 0xaa:
            raise Exception("invalid CD boot sector footer")

        def _checksum(data):
            """
            Method to compute the checksum on the ISO.  Note that this is *not*
            a 1's complement checksum; when an addition overflows, the carry
            bit is discarded, not added to the end.
            """
            s = 0
            for i in range(0, len(data), 2):
                w = ord(data[i]) + (ord(data[i+1]) << 8)
                s = (s + w) & 0xffff
            return s

        csum = _checksum(bootdata)
        if csum != 0:
            raise Exception("invalid CD checksum: expected 0, saw %d" % (csum))

        # OK, everything so far has checked out.  Read the default/initial
        # boot entry
        cdfd.seek(bootP*2048+32)
        fmt = "=BBHBBHIB"
        (boot, media, loadsegment, systemtype, unused, scount, imgstart, unused2) = struct.unpack(fmt, cdfd.read(struct.calcsize(fmt)))

        if boot != 0x88:
            raise Exception("invalid CD initial boot indicator")
        if unused != 0x0 or unused2 != 0x0:
            raise Exception("invalid CD initial boot unused field")

        if media == 0 or media == 4:
            count = scount
        elif media == 1:
            # 1.2MB floppy in sectors
            count = 1200*1024/512
        elif media == 2:
            # 1.44MB floppy in sectors
            count = 1440*1024/512
        elif media == 3:
            # 2.88MB floppy in sectors
            count = 2880*1024/512
        else:
            raise Exception("invalid CD media type")

        # finally, seek to "imgstart", and read "count" sectors, which
        # contains the boot image
        cdfd.seek(imgstart*2048)

        # The eltorito specification section 2.5 says:
        #
        # Sector Count. This is the number of virtual/emulated sectors the
        # system will store at Load Segment during the initial boot
        # procedure.
        #
        # and then Section 1.5 says:
        #
        # Virtual Disk - A series of sectors on the CD which INT 13 presents
        # to the system as a drive with 200 byte virtual sectors. There
        # are 4 virtual sectors found in each sector on a CD.
        #
        # (note that the bytes above are in hex).  So we read count*512
        eltoritodata = cdfd.read(count*512)
        cdfd.close()

        out = open(outfile, "w")
        out.write(eltoritodata)
        out.close()

    def _generate_new_iso_win_v5(self, output_iso):
        """
        Method to create a new ISO based on the modified CD/DVD.
        For Windows versions based on kernel 5.x (2000, XP, and 2003).
        """
        self.log.debug("Recreating El Torito boot sector")
        os.mkdir(os.path.join(self.iso_contents, "cdboot"))
        self._geteltorito(os.path.join(self.iso_contents, "cdboot", "boot.bin"))

        self.log.debug("Generating new ISO")
        self.subprocess_check_output(["genisoimage",
                                      "-b", "cdboot/boot.bin",
                                      "-no-emul-boot", "-boot-load-seg",
                                      "1984", "-boot-load-size", "4",
                                      "-iso-level", "2", "-J", "-l", "-D",
                                      "-N", "-joliet-long",
                                      "-relaxed-filenames", "-v", "-v",
                                      "-V", "Custom",
                                      "-o", output_iso,
                                      self.iso_contents])

    def _modify_iso_win_v5(self, install_script):
        """
        Method to copy a Windows v5 install script into the appropriate location
        """
        self.log.debug("Copying in Windows v5 winnt.sif file")
        outname = os.path.join(self.iso_contents, self.winarch, "winnt.sif")
        shutil.copy(install_script, outname)

    def _generate_new_iso_win_v6(self, output_iso):
        """
        Method to create a new Windows v6 ISO based on the modified CD/DVD.
        """
        self.log.debug("Recreating El Torito boot sector")
        os.mkdir(os.path.join(self.iso_contents, "cdboot"))
        self._geteltorito(os.path.join(self.iso_contents, "cdboot", "boot.bin"))

        self.log.debug("Generating new ISO")
        # NOTE: Windows 2008 is very picky about which arguments to genisoimage
        # will generate a bootable CD, so modify these at your own risk
        self.subprocess_check_output(["genisoimage",
                                      "-b", "cdboot/boot.bin",
                                      "-no-emul-boot", "-c", "BOOT.CAT",
                                      "-iso-level", "2", "-J", "-l", "-D",
                                      "-N", "-joliet-long",
                                      "-relaxed-filenames", "-v", "-v",
                                      "-V", "Custom", "-udf",
                                      "-o", output_iso,
                                      self.iso_contents])

    def _install_script_win_v6(self, install_script):
        """
        Method to copy a Windows v6 install script into the appropriate location
        """
        self.log.debug("Copying in Windows v6 autounattend.xml file")
        outname = os.path.join(self.iso_contents, "autounattend.xml")
        shutil.copy(install_script, outname)

    def _copy_iso(self):
        """
        Method to copy the data out of an ISO onto the local filesystem.
        """
        self.log.info("Copying ISO contents for modification")
        try:
            shutil.rmtree(self.iso_contents)
        except OSError as err:
            if err.errno != errno.ENOENT:
                raise
        os.makedirs(self.iso_contents)

        self.log.info("Setting up guestfs handle")
        gfs = guestfs.GuestFS()
        self.log.debug("Adding ISO image %s" % (self.orig_iso))
        gfs.add_drive_opts(self.orig_iso, readonly=1, format='raw')
        self.log.debug("Launching guestfs")
        gfs.launch()
        try:
            self.log.debug("Mounting ISO")
            gfs.mount_options('ro', "/dev/sda", "/")

            self.log.debug("Checking if there is enough space on the filesystem")
            isostat = gfs.statvfs("/")
            outputstat = os.statvfs(self.iso_contents)
            if (outputstat.f_bsize*outputstat.f_bavail) < (isostat['blocks']*isostat['bsize']):
                raise Exception("Not enough room on %s to extract install media" % (self.iso_contents))

            self.log.debug("Extracting ISO contents")
            current = os.getcwd()
            os.chdir(self.iso_contents)
            try:
                rd, wr = os.pipe()

                try:
                    # NOTE: it is very, very important that we use temporary
                    # files for collecting stdout and stderr here.  There is a
                    # nasty bug in python subprocess; if your process produces
                    # more than 64k of data on an fd that is using
                    # subprocess.PIPE, the whole thing will hang. To avoid
                    # this, we use temporary fds to capture the data
                    stdouttmp = tempfile.TemporaryFile()
                    stderrtmp = tempfile.TemporaryFile()

                    try:
                        tar = subprocess.Popen(["tar", "-x", "-v"], stdin=rd,
                                               stdout=stdouttmp,
                                               stderr=stderrtmp)
                        try:
                            gfs.tar_out("/", "/dev/fd/%d" % wr)
                        except:
                            # we need this here if gfs.tar_out throws an
                            # exception.  In that case, we need to manually
                            # kill off the tar process and re-raise the
                            # exception, otherwise we hang forever
                            tar.kill()
                            raise

                        # FIXME: we really should check tar.poll() here to get
                        # the return code, and print out stdout and stderr if
                        # we fail.  This will make debugging problems easier
                    finally:
                        stdouttmp.close()
                        stderrtmp.close()
                finally:
                    os.close(rd)
                    os.close(wr)

                # since we extracted from an ISO, there are no write bits
                # on any of the directories.  Fix that here
                for dirpath, dirnames, filenames in os.walk(self.iso_contents):
                    st = os.stat(dirpath)
                    os.chmod(dirpath, st.st_mode|stat.S_IWUSR)
                    for name in filenames:
                        fullpath = os.path.join(dirpath, name)
                        try:
                            # if there are broken symlinks in the ISO,
                            # then the below might fail.  This probably
                            # isn't fatal, so just allow it and go on
                            st = os.stat(fullpath)
                            os.chmod(fullpath, st.st_mode|stat.S_IWUSR)
                        except OSError as err:
                            if err.errno != errno.ENOENT:
                                raise
            finally:
                os.chdir(current)
        finally:
            gfs.sync()
            gfs.umount_all()
            gfs.kill_subprocess()

    def _cleanup_iso(self):
        """
        Method to cleanup the local ISO contents.
        """
        self.log.info("Cleaning up old ISO data")
        # if we are running as non-root, then there might be some files left
        # around that are not writable, which means that the rmtree below would
        # fail.  Recurse into the iso_contents tree, doing a chmod +w on
        # every file and directory to make sure the rmtree succeeds
        for dirpath, dirnames, filenames in os.walk(self.iso_contents):
            os.chmod(dirpath, stat.S_IWUSR|stat.S_IXUSR|stat.S_IRUSR)
            for name in filenames:
                try:
                    # if there are broken symlinks in the ISO,
                    # then the below might fail.  This probably
                    # isn't fatal, so just allow it and go on
                    os.chmod(os.path.join(dirpath, name), stat.S_IRUSR|stat.S_IWUSR)
                except OSError as err:
                    if err.errno != errno.ENOENT:
                        raise

        self.rmtree_and_sync(self.iso_contents)


    def rmtree_and_sync(self, directory):
	"""
	Function to remove a directory tree and do an fsync afterwards.  Because
	the removal of the directory tree can cause a lot of metadata updates, it
	can cause a lot of disk activity.  By doing the fsync, we ensure that any
	metadata updates caused by us will not cause subsequent steps to fail.  This
	cannot help if the system is otherwise very busy, but it does ensure that
	the problem is not self-inflicted.
	"""
	shutil.rmtree(directory)
	fd = os.open(os.path.dirname(directory), os.O_RDONLY)
	try:
	    os.fsync(fd)
	finally:
            os.close(fd)

    def subprocess_check_output(self, *popenargs, **kwargs):
	"""
	Function to call a subprocess and gather the output.
	"""
	if 'stdout' in kwargs:
	    raise ValueError('stdout argument not allowed, it will be overridden.')
	if 'stderr' in kwargs:
	    raise ValueError('stderr argument not allowed, it will be overridden.')

	self.executable_exists(popenargs[0][0])

	# NOTE: it is very, very important that we use temporary files for
	# collecting stdout and stderr here.  There is a nasty bug in python
	# subprocess; if your process produces more than 64k of data on an fd that
	# is using subprocess.PIPE, the whole thing will hang. To avoid this, we
	# use temporary fds to capture the data
	stdouttmp = tempfile.TemporaryFile()
	stderrtmp = tempfile.TemporaryFile()

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
	    raise SubprocessException("'%s' failed(%d): %s" % (cmd, retcode, stderr), retcode)
        return (stdout, stderr, retcode)

    def executable_exists(self, program):
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
