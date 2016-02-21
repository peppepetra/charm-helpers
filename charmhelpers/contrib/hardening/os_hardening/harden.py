# Copyright 2016 Canonical Limited.
#
# This file is part of charm-helpers.
#
# charm-helpers is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version 3 as
# published by the Free Software Foundation.
#
# charm-helpers is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with charm-helpers.  If not, see <http://www.gnu.org/licenses/>.

import os
import platform
import re
import subprocess
import yaml

from charmhelpers.contrib.hardening import templating
from charmhelpers.contrib.hardening.utils import (
    ensure_permissions,
)
from charmhelpers.core.hookenv import config
from charmhelpers.fetch import (
    apt_install,
    apt_purge,
)

OS_TEMPLATES = os.path.join(os.path.dirname(__file__), 'templates')


def get_defaults():
    defaults = os.path.join(os.path.dirname(__file__),
                            'defaults/main.yaml')
    return yaml.safe_load(open(defaults))


class PAMContext(object):

    def __init__(self, pam_name):
        self.pam_name = pam_name

    def __call__(self):
        ctxt = {}
        defaults = get_defaults()

        # Always remove?
        apt_purge('libpam-ccreds')

        if self.pam_name == 'passwdqc':
            if defaults.get('auth_pam_passwdqc_enable'):
                apt_purge('libpam-cracklibtapt')
                apt_install('libpam-passwdqc')
                ctxt['auth_pam_passwdqc_options'] = \
                    defaults.get('auth_pam_passwdqc_options')
            else:
                apt_purge('libpam-passwdqc')
        elif self.pam_name == 'tally2':
            ctxt['auth_lockout_time'] = defaults.get('auth_lockout_time')
            if defaults.get('auth_retries'):
                ctxt['auth_retries'] = defaults.get('auth_retries')
                apt_install('libpam-modules')
            else:
                os.remove('/usr/share/pam-configs/tally2')
                # Stop template frombeing written since we want to disable tally2
                ctxt['__disable__'] = True
        else:
            raise Exception("Unrecognised PAM name '%s'" % (self.pam_name))

        return ctxt


class ModulesContext(object):

    def __call__(self):
        with open('/proc/cpuinfo', 'r') as fd:
            cpuinfo = fd.readlines()

        for line in cpuinfo:
            match = re.search(r"^vendor_id\s+:\s+(.+)", line)
            if match:
                vendor = match.group(1)

        if vendor == "GenuineIntel":
            vendor = "intel"
        elif vendor == "AuthenticAMD":
            vendor = "amd"

        defaults = get_defaults()
        ctxt = {'arch': platform.processor(),
                'cpuVendor': vendor,
                'desktop_enable': defaults.get('desktop_enable', False)}

        return ctxt


class LoginContext(object):

    def __call__(self):
        defaults = get_defaults()
        ctxt = {'additional_user_paths':
                defaults.get('env_extra_user_paths'),
                'umask': defaults.get('env_umask'),
                'pwd_max_age': defaults.get('auth_pw_max_age'),
                'pwd_min_age': defaults.get('auth_pw_min_age'),
                'uid_min': defaults.get('auth_uid_min'),
                'sys_uid_min': defaults.get('auth_sys_uid_min'),
                'sys_uid_max': defaults.get('auth_sys_uid_max'),
                'gid_min': defaults.get('auth_gid_min'),
                'sys_gid_min': defaults.get('auth_sys_gid_min'),
                'sys_gid_max': defaults.get('auth_sys_gid_max'),
                'login_retries': defaults.get('auth_retries'),
                'login_timeout': defaults.get('auth_timeout'),
                'chfn_restrict': defaults.get('chfn_restrict'),
                'allow_login_without_home':
                defaults.get('auth_allow_homeless')
                }

        return ctxt


class ProfileContext(object):

    def __call__(self):
        ctxt = {}
        return ctxt


class SecureTTYContext(object):

    def __call__(self):
        defaults = get_defaults()
        ctxt = {'ttys': defaults.get('auth_root_ttys')}
        return ctxt


class SecurityLimitsContext(object):

    def __call__(self):
        defaults = get_defaults()
        ctxt = {'disable_core_dump':
                not defaults.get('enable_core_dump', False)}
        return ctxt


def register_configs():
    configs = templating.HardeningConfigRenderer(templates_dir=OS_TEMPLATES)

    confs = {'/etc/modules':
             {'contexts': [ModulesContext()],
              'service_actions': [],
              'post-hooks': [(ensure_permissions,
                              ('/etc/sysctl.conf', 'root', 0o0440), {}),
                             (ensure_permissions,
                              ('/etc/modules', 'root', 0o0440), {})]},
             '/etc/login.defs':
             {'contexts': [LoginContext()],
              'post-hooks': [(ensure_permissions,
                              ('/etc/login.defs', 'root', 0o0444), {})]
              },
             '/etc/profile.d/pinerolo_profile.sh':
             {'contexts': [ProfileContext()],
              'post-hooks': [(ensure_permissions,
                              ('/etc/profile.d/pinerolo_profile.sh', 0o0755,
                               'root'), {})]
              },
             '/etc/securetty':
             {'contexts': [SecureTTYContext()],
              'post-hooks': [(ensure_permissions,
                              ('/etc/securetty', 0o0400, 'root'), {})]
              },
             '/etc/security/limits.d/10.hardcore.conf':
             {'contexts': [SecurityLimitsContext()],
              'post-hooks': [(ensure_permissions,
                              ('/etc/security/limits.d', 'root', 0o0755), {}),
                             (ensure_permissions,
                              ('/etc/security/limits.d/10.hardcore.conf',
                               'root', 0o0440), {})]},
             '/usr/share/pam-configs/tally2':
             {'contexts': [PAMContext('tally2')],
              'extra_files': '/usr/share/pam-configs/passwdqc',
              'service_actions': [],
              'post-hooks': [(ensure_permissions,
                              ('/usr/share/pam-configs/tally2', 'root',
                               0o0640), {}),
                             (subprocess.check_output,
                              (['pam-auth-update', '--package']))]},
             '/usr/share/pam-configs/passwdqc':
             {'contexts': [PAMContext('passwdqc')],
              'service_actions': [],
              'post-hooks': [(ensure_permissions,
                              ('/usr/share/pam-configs/passwdqc', 'root',
                               0o0640), {}),
                             (subprocess.check_output,
                              (['pam-auth-update', '--package']))]}
             }

    for conf in confs:
        configs.register(conf, confs[conf])

    return configs


# Run on import
if config('harden'):
    OS_CONFIGS = register_configs()
    OS_CONFIGS.write_all()


def harden_os(f):
    OS_CONFIGS.write_all()

    def _harden_os(*args, **kwargs):
        return f(*args, **kwargs)

    return _harden_os
