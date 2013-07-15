Summary: Utility for automated installs in Openstack Nova
Name: imagebuilder
Version: 0.0.1
Release: 1
#Version: @VERSION@
#Release: @RELEASE@%{?dist}
License: ASL 2.0
Group: Development/Libraries
URL: https://github.com/stackforge/novaimagebuilder
Source0: imagebuilder-%{version}.tar.gz
BuildArch: noarch
Requires: python >= 2.5
Requires: python-libguestfs >= 1.18
%if 0%{?fedora} >= 17
Requires: libvirt-daemon-kvm
Requires: libvirt-daemon-qemu
Requires: libvirt-daemon-config-network
%else
Requires: libvirt >= 0.9.7
%endif
Requires: python-pycurl
BuildRequires: python

%description
The Nova Image Builder is a tool to launch and monitor native OS installs inside of Nova.

%prep
%setup -q

%build
python setup.py build

%install
python setup.py install --root=$RPM_BUILD_ROOT --skip-build

mkdir -p $RPM_BUILD_ROOT%{_sysconfdir}/novaimagebuilder
cp etc/imagebuilder/imagebuilder.conf $RPM_BUILD_ROOT%{_sysconfdir}/novaimagebuilder

%files
#%doc README COPYING examples docs
%dir %attr(0755, root, root) %{_sysconfdir}/novaimagebuilder/
%config(noreplace) %{_sysconfdir}/novaimagebuilder/imagebuilder.conf
#%dir %attr(0755, root, root) %{_localstatedir}/lib/oz/
%{python_sitelib}/imagebuilder
%{_bindir}/create_image
%{_bindir}/imagebuilder-api
%{python_sitelib}/imagebuilder-*.egg-info

%changelog
