# we don't do the condition check as per FPG because we are targeting
# el4 also... which doesn't support it
%{!?python_sitelib: %global python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())")}

Summary:        Holland LVM snapshot backup for Perfect Search appliances
Name:           %{psprefix}-%{psname}
Version:        %{psversion}
Release:        %{psrelease}
Vendor:         Perfect Search Corporation
License:        Proprietary
URL:            https://software.perfectsearchcorp.com
Group:          Development/Libraries
BuildArch:      noarch
BuildRoot:      %{psbuildroot}
Prefix:         /opt/search/%{psapplianceversion}

Requires:       search-%{psapplianceversion},holland-mysqldump,holland-mysqllvm,holland-common,lvm2,tar

# In some distros rpmbuild utility handles existance of arch-dependent libraries as errors.
# We allways provide packages with full library set so we have to prevent this behavior.
%define _binaries_in_noarch_packages_terminate_build 0
# For some reason in some distros sysconfidir (/etc) points to %{_prefix}/etc. Fix it.
%define _sysconfdir /etc
%define _initrddir /etc/rc.d/init.d
%define init %{prefix}/init/%{psname}

%build
%{__python} setup.py build

%install
rm -rf %{buildroot}
%{__mkdir} -p %{buildroot}
%{__python} setup.py install -O1 --skip-build --root %{buildroot}
install -m 0640 config/build/test.conf %{buildroot}%{_sysconfdir}/holland/providers/

%clean
rm -rf %{buildroot}

%post

%preun

%description
This set of plugins allows holland to perform LVM snapshot backups of Search Server's data and various config files and generate a gzipped tar archive of the raw data files.

%files
%defattr(644,root,root,755)
%{prefix}/webapp/extensions/%{psname}/*
%defattr(-,root,root,-)
%{python_sitelib}/holland/backup/perfectsearch*_lvm/
%{python_sitelib}/holland.backup.perfectsearch*_lvm/