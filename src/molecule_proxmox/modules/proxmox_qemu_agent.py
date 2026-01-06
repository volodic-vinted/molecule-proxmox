#!/usr/bin/python

# Copyright (c) 2022, Sine Nomine Associates
# BSD 2-Clause License

ANSIBLE_METADATA = {
    'metadata_version': '1.1.',
    'status': ['preview'],
    'supported_by': 'community',
}

DOCUMENTATION = r"""
---
module: proxmox_qemu_agent

short_description: Query the QEMU guest agent to find the IP addresses
                   of a running vm.

description:
  - Start the vm if it is currently not running and wait until at least
    one non-loopback IP address is detected.

  - Fails when an IP address is not found within the timeout value.

author:
  - Michael Meffie (@meffie)
"""

EXAMPLES = r"""
- name: Start instance
  proxmox_qemu_agent:
    api_host: pve
    api_user: admin
    api_password: ********
    vmid: 100
    timeout: 300
"""

RETURN = r"""
vmid:
  description: vmid of target virtual machine
  returned: always
  type: int
  sample: 100

addresses:
  decription: list of one or more IPv4 addresses
  returned: always
  type: list
  sample: ['192.168.136.123']
"""

import time  # noqa: E402
import syslog  # noqa: E402

from proxmoxer import ProxmoxAPI  # noqa: E402
from proxmoxer.core import ResourceException  # noqa: E402
from ansible.module_utils.basic import AnsibleModule  # noqa: E402


def get_vm(module, proxmox, vmid):
    """
    Look up a vm by id, and fail if not found.
    """
    vm_list = [vm for vm in proxmox.cluster.resources.get(type='vm') if vm['vmid'] == int(vmid)]  # noqa: E501
    if len(vm_list) == 0:
        module.fail_json(vmid=vmid, msg='VM with vmid = %s not found' % vmid)
    if len(vm_list) > 1:
        module.fail_json(vmid=vmid, msg='Multiple VMs with vmid = %s found' % vmid)  # noqa: E501
    return vm_list[0]


def start_vm(module, proxmox, vm):
    """
    Start the vm and wait until the start task completes.
    """
    vmid = vm['vmid']
    proxmox_node = proxmox.nodes(vm['node'])
    timeout = module.params['timeout']

    syslog.syslog('Starting vmid {0}'.format(vmid))
    taskid = proxmox_node.qemu(vm['vmid']).status.start.post()
    while timeout:
        task = proxmox_node.tasks(taskid).status.get()
        if task['status'] == 'stopped' and task['exitstatus'] == 'OK':
            time.sleep(1)  # Delay for API
            return
        timeout = timeout - 1
        if timeout == 0:
            break
        time.sleep(1)
    lastlog = proxmox_node.tasks(taskid).log.get()[:1]
    msg = 'Timeout while starting vmid {0}: {1}'.format(vmid, lastlog)
    syslog.syslog(msg)
    module.fail_json(msg=msg)


def query_vm(module, proxmox, vm):
    """
    Query the QEMU guest agent to get the current IP address(es).
    """
    vmid = vm['vmid']
    proxmox_node = proxmox.nodes(vm['node'])
    timeout = module.params['timeout']

    syslog.syslog('Waiting for vmid {0} IP address'.format(vmid))
    while timeout:
        reply = None
        try:
            reply = proxmox_node.qemu(vmid).agent.get('network-get-interfaces')  # noqa: E501
            if module.params.get('debug', False):
                syslog.syslog('network-get-interfaces reply: {0}'.format(reply))
        except ResourceException as e:
            if e.status_code == 500 and 'VM {0} is not running'.format(vmid) in e.content:  # noqa: 501
                start_vm(module, proxmox, vm)
            elif e.status_code == 500 and 'QEMU guest agent is not running' in e.content:  # noqa: 501
                pass  # Waiting for guest agent to start.
            else:
                module.fail_json(msg=str(e))
        if reply and 'result' in reply:
            addresses = i2a(module, reply['result'])
            if len(addresses) > 0:
                return addresses   # Found at least one address.
        timeout = timeout - 1
        if timeout == 0:
            break
        time.sleep(1)

    msg = 'Timeout while waiting for vmid {0} IP address'.format(vmid)
    syslog.syslog(msg)
    module.fail_json(msg=msg)


def i2a(module, interfaces):
    """
    Extract the non-loopback IPv4 addresses from
    network-get-interfaces results.

    Example:

        reply = {'results': [
          {
            'name': 'ens18',
            'hardware-address': '6e:25:bb:c7:4b:76',
            'ip-addresses': [
              {
                'ip-address-type': 'ipv4',
                'ip-address': '192.168.136.176',
                ...
              },
              {
                'ip-address-type': 'ipv6',
                'ip-address': 'fe80::6c25:bbff:fec7:4b76',
                ...
              }
            ]
            ...
          },
          {
            'name': 'lo',
            'hardware-address': '00:00:00:00:00:00',
        ...
        }

        i2a(module, reply['results'])
        ['192.168.136.176']

    """
    addrs = []
    module.warn("====== TEMPORARY MESSAGE ======")
    for interface in interfaces:
        interface_name = interface.get('name', '')

        # Skip obvious loopback interfaces by name
        if interface_name.lower() in ['lo', 'loopback']:
            continue

        if 'ip-addresses' in interface:
            for ip_address in interface['ip-addresses']:
                atype = ip_address.get('ip-address-type', '')
                aip = ip_address.get('ip-address', '')

                if aip and atype == 'ipv4':
                    # Filter loopback and APIPA addresses
                    if aip.startswith('127.') or aip.startswith('169.254.'):
                        syslog.syslog('Skipping loopback/APIPA address {0} on {1}'.format(aip, interface_name))
                        continue

                    syslog.syslog('Found IPv4 address {0} on interface {1}'.format(aip, interface_name))
                    addrs.append(aip)

    def priority(ip):
        """
        Prioritize private IP addresses.
        Priority order:
        0 - Class A private (10.0.0.0/8)
        1 - Class C private (192.168.0.0/16)
        2 - Class B private (172.16.0.0/12)
        3 - Public IPs
        """
        if ip.startswith('10.'):
            return 0
        elif ip.startswith('192.168.'):
            return 1
        elif ip.startswith('172.'):
            parts = ip.split('.')
            if len(parts) >= 2 and 16 <= int(parts[1]) <= 31:
                return 2
        return 3

    addrs.sort(key=priority)

    if addrs:
        syslog.syslog('Detected IP addresses (sorted by priority): {0}'.format(addrs))
    else:
        syslog.syslog('No valid IPv4 addresses detected')

    return addrs


def run_module():
    """
    Lookup the IP addresses on a running vm with the qemu guest agent.
    Since the guest may still be booting and acquiring an address with
    DHCP, retry until we find at least one address, or timeout.
    """
    result = dict(
        changed=False,
        vmid=0,
        addresses=[],
    )
    module = AnsibleModule(
        argument_spec=dict(
            api_host=dict(type='str', required=True),
            api_port=dict(type='int', default=None),
            api_user=dict(type='str', required=True),
            api_password=dict(type='str', no_log=True),
            api_token_id=dict(type='str', no_log=True),
            api_token_secret=dict(type='str', no_log=True),
            validate_certs=dict(type='bool', default=False),
            vmid=dict(type='int', required=True),
            timeout=dict(type='int', default=300),
            debug=dict(type='bool', default=False),
        ),
        required_together=[('api_token_id', 'api_token_secret')],
        required_one_of=[('api_password', 'api_token_id')],
    )
    api_host = module.params['api_host']
    api_port = module.params['api_port']
    validate_certs = module.params['validate_certs']
    api_user = module.params['api_user']
    api_password = module.params['api_password']
    api_token_id = module.params['api_token_id']
    api_token_secret = module.params['api_token_secret']
    vmid = module.params['vmid']

    auth_args = {'user': api_user}
    if not (api_token_id and api_token_secret):
        auth_args['password'] = api_password
    else:
        auth_args['token_name'] = api_token_id
        auth_args['token_value'] = api_token_secret

    # API Login
    proxmox = ProxmoxAPI(
        api_host,
        port=api_port,
        verify_ssl=validate_certs,
        **auth_args)

    # Lookup the vm by id.
    time.sleep(1)    # Delay for API since we just cloned this instance.
    vm = get_vm(module, proxmox, vmid)

    # Wait for at least one IP address.
    addresses = query_vm(module, proxmox, vm)
    result['vmid'] = vmid
    result['addresses'] = addresses

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
