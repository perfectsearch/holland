%if 0%{?rhel} < 6
%global __python /usr/bin/python2.6
%global __os_install_post %{__python26_os_install_post}
%endif

%{!?python_sitelib: %global python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}

%bcond_without  tests
%bcond_without  sphinxdocs
%bcond_without  lvm
%bcond_without  mysql
%bcond_with     mongodb
%bcond_without  pgsql 

Name:           holland
Version:        2.0.2
Release:        1%{?dist}
Summary:        Holland backup manager

Group:          Applications/Archiving
License:        BSD
URL:            http://hollandbackup.org
Source0:        %{name}-%{version}.tar.gz
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)

BuildArch:      noarch
%if 0%{?rhel} < 6
BuildRequires:  python26-devel
BuildRequires:  python26-setuptools
Requires:       python26-argparse
Requires:       python26-sqlalchemy
Requires:       python26-setuptools
%else
BuildRequires:  python-devel
BuildRequires:  python-setuptools
Requires:       python-argparse
Requires:       python-sqlalchemy
Requires:       python-setuptools
%endif

# compatibility with 1.0.X - holland-common has been absorbed into holland
Provides:       holland-common = %{version}-%{release}
Obsoletes:      holland-common < 2.0

%description
A pluggable backup manager which provides highly configurable database
backups for various open-source database products.

%if %{with mysql}
%package mysql
Summary:        MySQL backup plugins for holland
License:        GPLv2
Group:          Applications/Archiving
# holland 2.0 obsoletes holland 1.0.x
# obsolete old holland-mysqldump and holland-xtrabackup packages
Provides:       holland-mysqldump = %{version}-%{release}
Obsoletes:      holland-mysqldump < 2.0
Provides:       holland-xtrabackup = %{version}-%{release}
Obsoletes:      holland-xtrabackup < 2.0
Requires:       %{name} = %{version}-%{release}
%if 0%{?rhel} < 6
Requires:       python26-mysqldb
Requires:       python26-jinja2
Requires:       python26-sqlalchemy
%else
Requires:       MySQL-python
Requires:       python-jinja2
Requires:       python-sqlalchemy
%endif

%description mysql
The holland-mysql package contains multiple backup strategies for MySQL
These include:
* mysqldump backups
* xtrabackup
%endif

%if %{with pgsql}
%package pgsql 
Summary:        PostgreSQL backup plugins for holland
License:        GPLv2
Group:          Applications/Archiving
Provides:       holland-pgdump = %{version}-%{release}
Obsoletes:      holland-pgdump < 2.0
Requires:       %{name} = %{version}-%{release}
Requires:       python-psycopg2

%description pgsql 
The holland-pgsql package contains support for backing up Postgres
databases.
These include:
* pgdump backups
%endif

%if %{with lvm}
%package lvm
Summary:        LVM backup plugins for holland
License:        GPLv2
Group:          Applications/Archiving
Requires:       lvm2
Requires:       %{name} = %{version}-%{release}

%description lvm
The holland-lvm package provides generic support for LVM2 snapshot backups.
%endif

%if %{with lvm} && %{with mysql}
%package mysql-lvm
Summary:        MySQL+LVM backup plugins for holland
License:        GPLv2
Group:          Applications/Archiving
Requires:       %{name} = %{version}-%{release}
Requires:       holland-lvm = %{version}-%{release}
Requires:       holland-mysql = %{version}-%{release}
# replace 1.0.X holland-mysqllvm packages
Provides:       holland-mysqllvm = %{version}-%{release}
Obsoletes:      holland-mysqllvm < 2.0

%description mysql-lvm
This holland-mysql-lvm package provides support for MySQL database backups
using LVM2 snapshots.  There are multiple strategies that are provided by
this package including:
    * mysql-lvm - file level backups from an LVM2 snapshot
    * mylvmdump - mysqldump backups from mysqld running on an LVM2 snapshot
%endif


%if %{with mongodb}
%package mongodb
Summary:        Mongodb backup plugins for holland
License:        GPLv2
Group:          Applications/Archiving
Requires:       %{name} = %{version}-%{release}
Requires:       pymongo

%description mongodb
The holland-mongodb package provides support for backing up MongoDB databases
using a variety of backup strategies, including:

* mongodump
* LVM snapshots of non-journalled Mongo instances
%endif

%prep
%setup -q


%build

find . -type f -name setup.py | xargs sed -i '/namespace_packages/d'

%{__python} setup.py build

%if %{with mysql}
# mysql
cd plugins/mysql
%{__python} setup.py build
cd -
%endif

%if %{with pgsql}
# postgresql
cd plugins/pgsql
%{__python} setup.py build
cd -
%endif

%if %{with lvm}
# lvm
cd plugins/lvm
%{__python} setup.py build
cd -
%endif

%if %{with lvm} && %{with mysql}
# mysql-lvm
cd plugins/mysql-lvm
%{__python} setup.py build
cd -
%endif

%if %{with mongodb}
# mongodb
cd plugins/mongodb
%{__python} setup.py build
cd -
%endif


%install
rm -rf %{buildroot}

# holland-core
%{__python} setup.py install -O1 --skip-build --root %{buildroot}
%{__mkdir_p} %{buildroot}%{_sysconfdir}/holland/backupsets
%{__mkdir_p} %{buildroot}%{_localstatedir}/lib/holland
%{__mkdir_p} %{buildroot}%{_localstatedir}/spool/holland
%{__mkdir_p} %{buildroot}%{_var}/log/holland
install -m 0644 config/holland.conf %{buildroot}%{_sysconfdir}/holland/

%if %{with mysql}
# holland-mysql
cd plugins/mysql
%{__python} setup.py install -O1 --skip-build --root %{buildroot}
cd -
%endif

%if %{with pgsql}
# holland-pgsql
cd plugins/pgsql
%{__python} setup.py install -O1 --skip-build --root %{buildroot}
cd -
%endif

%if %{with lvm}
# holland-lvm
cd plugins/lvm
%{__python} setup.py install -O1 --skip-build --root %{buildroot}
cd -
%endif

%if %{with lvm} && %{with mysql}
# holland-mysql-lvm
cd plugins/mysql-lvm
%{__python} setup.py install -O1 --skip-build --root %{buildroot}
cd -
%endif

%if %{with mongodb}
# holland-mongodb
cd plugins/mongodb
%{__python} setup.py install -O1 --skip-build --root %{buildroot}
cd -
%endif
 
%clean
rm -rf %{buildroot}


%files
%doc README.rst
# be careful not to own everything under holland/
%dir %{python_sitelib}/%{name}
%{python_sitelib}/%{name}/core
%{python_sitelib}/%{name}/cli
%{python_sitelib}/%{name}/version.py*
%{python_sitelib}/%{name}/__init__.py*
%{python_sitelib}/%{name}-%{version}-py*.egg-info
%{_bindir}/holland
%dir %{_sysconfdir}/holland
%dir %{_sysconfdir}/holland/backupsets/
%dir %{_localstatedir}/log/holland/
%attr(0770,root,root) %dir %{_localstatedir}/lib/holland/
%attr(0770,root,root) %dir %{_localstatedir}/spool/holland/
%config(noreplace) %{_sysconfdir}/holland/holland.conf

%if %{with mysql}
%files mysql
%doc plugins/mysql/{README,LICENSE}
%{python_sitelib}/%{name}/mysql/__init__.py*
%{python_sitelib}/%{name}/mysql/client.py*
%{python_sitelib}/%{name}/mysql/pathinfo.py*
%{python_sitelib}/%{name}/mysql/schema.py*
%{python_sitelib}/%{name}/mysql/server.py*
%{python_sitelib}/%{name}/mysql/util.py*
%{python_sitelib}/%{name}/mysql/templates/
%{python_sitelib}/%{name}/mysql/delphini/
%{python_sitelib}/%{name}/mysql/mysqldump/
%{python_sitelib}/%{name}/mysql/xtrabackup/


%{python_sitelib}/%{name}.mysql-%{version}-py*.egg-info
%endif

%if %{with lvm} && %{with mysql}
%files mysql-lvm
%doc plugins/mysql-lvm/{README,LICENSE}
%{python_sitelib}/%{name}/mysql/lvm/
%{python_sitelib}/%{name}.mysql.lvm-%{version}-py*.egg-info
%endif

%if %{with pgsql}
%files pgsql
%doc plugins/pgsql/{README,LICENSE}
%{python_sitelib}/%{name}/pgsql/
%{python_sitelib}/%{name}.pgsql-%{version}-py*.egg-info
%endif

%if %{with lvm}
%files lvm
%doc plugins/lvm/{README,LICENSE}
%{python_sitelib}/%{name}/lvm/
%{python_sitelib}/%{name}.lvm-%{version}-py*.egg-info
%endif

%if %{with mongodb}
%files mongodb
%doc plugins/mongodb/{README,LICENSE}
%{python_sitelib}/%{name}/mongodb/
%{python_sitelib}/%{name}.mongodb-%{version}-py*.egg-info
%endif

%changelog
* Mon Jan 27 2014 Andrew Garner <andrew.garner@rackspace.com> - 2.0.2-1
- New release

* Sun Nov 24 2013 Andrew Garner <andrew.garner@rackspace.com> - 2.0.1-1
- New release

* Mon Aug 05 2013 Andrew Garner <andrew.garner@rackspace.com> - 2.0.0-1
- Initial specfile for holland 2.0.0
