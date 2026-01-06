#  Copyright (c) 2022 Sine Nomine Associates
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to
#  deal in the Software without restriction, including without limitation the
#  rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
#  sell copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in
#  all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#  DEALINGS IN THE SOFTWARE.

import os

from molecule import logger
from molecule import util
from molecule.api import Driver


LOG = logger.get_logger(__name__)


class Proxmox(Driver):
    """
    The class responsible for managing instances with Proxmox.

    .. code-block:: yaml

        driver:
          name: proxmox
        platforms:
          - name: instance
            template: generic-centos-8
            memory: 1024
            cpus: 1

    .. code-block:: bash

        $ pip install molecule-proxmox

    """  # noqa

    def __init__(self, config=None):
        super(Proxmox, self).__init__(config)
        self._name = "molecule-proxmox"
        library_path = os.environ.get("ANSIBLE_LIBRARY", "")
        if library_path:
            library_path = self.modules_dir() + ":" + library_path
        else:
            library_path = self.modules_dir()
        os.environ["ANSIBLE_LIBRARY"] = library_path

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value

    @property
    def login_cmd_template(self):
        """Return login command template based on instance OS type."""
        instance_name = self._get_target_instance_name()

        if instance_name:
            try:
                instance_config = self._get_instance_config(instance_name)
                os_type = instance_config.get("os_type", "linux").lower()

                if os_type == "windows":
                    LOG.info('Opening RDP connection to Windows instance')
                    rdp_launcher = os.path.join(os.path.dirname(__file__), "rdp_launcher.py")
                    return "python3 " + rdp_launcher + " {address} {user} {rdp_port} {password}"
            except (StopIteration, IOError, KeyError):
                # If cannot determine os - fall back to ssh
                pass

        connection_options = " ".join(self.ssh_connection_options)
        LOG.debug('Using SSH login command template')
        return (
            "ssh {{address}} "
            "-l {{user}} "
            "-p {{port}} "
            "-i {{identity_file}} "
            "{}"
        ).format(connection_options)

    def _get_target_instance_name(self):
        """Extract the target instance name from molecule command args."""
        # The instance name is typically passed as a positional argument to 'molecule login'
        if hasattr(self._config, 'command_args') and self._config.command_args:
            # Try to get the host/instance argument
            host = self._config.command_args.get('host')
            if host:
                return host

        # Also check subcommand for older molecule versions
        if hasattr(self._config, 'subcommand'):
            return getattr(self._config, 'subcommand', None)

        return None

    @property
    def default_safe_files(self):
        return []

    @property
    def default_ssh_connection_options(self):
        return self._get_ssh_connection_options()

    def login_options(self, instance_name):
        d = {"instance": instance_name}
        instance_config = self._get_instance_config(instance_name)

        # Ensure rdp_port exists for Windows instances (backward compatibility)
        if instance_config.get("os_type") == "windows" and "rdp_port" not in instance_config:
            instance_config["rdp_port"] = 3389

        # Ensure password exists for Windows instances (may be None/empty)
        if instance_config.get("os_type") == "windows" and "password" not in instance_config:
            instance_config["password"] = ""

        return util.merge_dicts(d, instance_config)

    def ansible_connection_options(self, instance_name):
        try:
            d = self._get_instance_config(instance_name)
            os_type = d.get("os_type", "linux")

            if os_type == "windows":
                return {
                    "ansible_user": d["user"],
                    "ansible_host": d["address"],
                    "ansible_port": d["port"],
                    "ansible_password": d.get("password"),
                    "connection": "winrm",
                    "ansible_winrm_transport": d.get("winrm_transport", "ntlm"),
                    "ansible_winrm_server_cert_validation": d.get("winrm_cert_validation", "ignore"),
                }
            else:
                return {
                    "ansible_user": d["user"],
                    "ansible_host": d["address"],
                    "ansible_port": d["port"],
                    "ansible_private_key_file": d["identity_file"],
                    "connection": "ssh",
                    "ansible_ssh_common_args": " ".join(self.ssh_connection_options),  # noqa: E501
                }
        except StopIteration:
            return {}
        except IOError:
            # Instance has yet to be provisioned, therefore the
            # instance_config is not on disk.
            return {}

    def _get_instance_config(self, instance_name):
        instance_config_dict = util.safe_load_file(self._config.driver.instance_config)  # noqa: E501
        return next(
            item for item in instance_config_dict if item["instance"] == instance_name   # noqa: E501
        )

    def sanity_checks(self):
        pass

    def template_dir(self):
        """Return path to its own cookiecutterm templates. It is used by init
        command in order to figure out where to load the templates from.
        """
        return os.path.join(os.path.dirname(__file__), "cookiecutter")

    def modules_dir(self):
        return os.path.join(os.path.dirname(__file__), "modules")
