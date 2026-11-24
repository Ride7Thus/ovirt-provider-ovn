# Copyright 2017-2021 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license

from __future__ import absolute_import

from collections import namedtuple
from netaddr import AddrFormatError
from netaddr import EUI
import neutron.ip as ip_utils
from ovirt_provider_config_common import tenant_id
from neutron.mappers.base import Mapper
from neutron.mappers.base import RestDataError
from neutron.mappers.security_groups import SecurityGroupMapper


NetworkPort = namedtuple('NetworkPort', ['lsp', 'ls', 'dhcp_options', 'lrp'])


class PortMapper(Mapper):
    # The names of properties received/sent in a REST request
    REST_PORT_ID = 'id'
    REST_PORT_NETWORK_ID = 'network_id'
    REST_PORT_NAME = 'name'
    REST_PORT_MAC_ADDRESS = 'mac_address'
    REST_PORT_ADMIN_STATE_UP = 'admin_state_up'
    REST_PORT_DEVICE_ID = 'device_id'
    REST_PORT_DEVICE_OWNER = 'device_owner'
    REST_PORT_SECURITY_GROUPS = 'security_groups'
    REST_PORT_SECURITY_ENABLED = 'port_security_enabled'
    REST_PORT_FIXED_IPS = 'fixed_ips'
    REST_PORT_SUBNET_ID = 'subnet_id'
    REST_PORT_IP_ADDRESS = 'ip_address'
    REST_PORT_BINDING_HOST = 'binding:host_id'

    OVN_DEVICE_ID = 'ovirt_device_id'
    OVN_NIC_NAME = 'ovirt_nic_name'
    OVN_DEVICE_OWNER = 'ovirt_device_owner'
    OVN_REQUESTED_CHASSIS = 'requested-chassis'
    OVN_SECURITY_GROUPS = 'ovirt_security_groups'
    DEVICE_OWNER_ROUTER = 'network:router_interface'
    DEVICE_OWNER_ROUTER_GATEWAY = 'network:router_gateway'

    @staticmethod
    def rest2row(wrapped_self, func, rest_data, port_id):
        network_id = rest_data.get(PortMapper.REST_PORT_NETWORK_ID)
        name = rest_data.get(PortMapper.REST_PORT_NAME)
        mac = rest_data.get(PortMapper.REST_PORT_MAC_ADDRESS)
        is_enabled = rest_data.get(PortMapper.REST_PORT_ADMIN_STATE_UP)
        device_id = rest_data.get(PortMapper.REST_PORT_DEVICE_ID)
        device_owner = rest_data.get(PortMapper.REST_PORT_DEVICE_OWNER)
        fixed_ips = rest_data.get(PortMapper.REST_PORT_FIXED_IPS)
        binding_host = rest_data.get(PortMapper.REST_PORT_BINDING_HOST)
        port_security = rest_data.get(PortMapper.REST_PORT_SECURITY_ENABLED)
        security_groups = rest_data.get(PortMapper.REST_PORT_SECURITY_GROUPS)

        if port_id:
            return func(
                wrapped_self,
                port_id=port_id,
                network_id=network_id,
                name=name,
                mac=mac,
                is_enabled=is_enabled,
                device_id=device_id,
                device_owner=device_owner,
                fixed_ips=fixed_ips,
                binding_host=binding_host,
                port_security=port_security,
                security_groups=security_groups,
            )
        else:
            return func(
                wrapped_self,
                network_id=network_id,
                name=name or '',
                mac=mac,
                is_enabled=is_enabled,
                device_id=device_id,
                device_owner=device_owner,
                fixed_ips=fixed_ips,
                binding_host=binding_host,
                port_security=port_security,
                security_groups=security_groups,
            )

    @staticmethod
    def row2rest(row):
        """
        Maps the db rows (lsp, ls) to a Json representation of a port.
        The 'admin_state_up' property of the lsp is the product of
        two values:
        - lsp.up - managed internally by OVN, True only if
        set explicitly to [True]
        - lsp.enabled - set by the user, True if empty (None) or
        set to [True]
        """
        if not row:
            return {}
        lsp, ls, dhcp_options, lrp = row
        rest_data = {
            PortMapper.REST_PORT_ID: lsp.name,
            PortMapper.REST_PORT_NAME: lsp.external_ids[
                PortMapper.OVN_NIC_NAME
            ],
            PortMapper.REST_PORT_NETWORK_ID: str(ls.uuid),
            PortMapper.REST_PORT_SECURITY_GROUPS: PortMapper._map_sec_group_names(  # noqa: E501
                lsp.external_ids.get(
                    PortMapper.OVN_SECURITY_GROUPS, ''
                ).split()
            ),
            PortMapper.REST_PORT_SECURITY_ENABLED: PortMapper.is_port_security_enabled(  # noqa: E501
                lsp
            ),
            PortMapper.REST_TENANT_ID: tenant_id(),
            PortMapper.REST_PORT_FIXED_IPS: PortMapper.get_fixed_ips(
                lsp, dhcp_options, lrp
            ),
            PortMapper.REST_PORT_ADMIN_STATE_UP: bool(
                (lsp.up and lsp.up[0]) and (not lsp.enabled or lsp.enabled[0])
            ),
        }
        if PortMapper.OVN_DEVICE_ID in lsp.external_ids:
            rest_data[PortMapper.REST_PORT_DEVICE_ID] = str(
                lsp.external_ids[PortMapper.OVN_DEVICE_ID]
            )
        if PortMapper.OVN_DEVICE_OWNER in lsp.external_ids:
            rest_data[PortMapper.REST_PORT_DEVICE_OWNER] = lsp.external_ids[
                PortMapper.OVN_DEVICE_OWNER
            ]
        if lsp.addresses:
            mac = lsp.addresses[0].split(' ')[0]
            rest_data[PortMapper.REST_PORT_MAC_ADDRESS] = mac
        if lsp.options and PortMapper.OVN_REQUESTED_CHASSIS in lsp.options:
            binding_host = lsp.options[PortMapper.OVN_REQUESTED_CHASSIS]
            rest_data[PortMapper.REST_PORT_BINDING_HOST] = binding_host
        return rest_data

    @staticmethod
    def is_port_security_enabled(lsp):
        return len(lsp.port_security) > 0 if lsp else False

    @staticmethod
    def get_fixed_ips(lsp, dhcp_options, lrp):
        ip_address = ip_utils.get_port_ip(lsp, lrp)
        if ip_address:
            return [
                {
                    PortMapper.REST_PORT_IP_ADDRESS: ip_address,
                    PortMapper.REST_PORT_SUBNET_ID: (
                        str(dhcp_options.uuid) if dhcp_options else None
                    ),
                }
            ]

        return []

    @staticmethod
    def validate_add_rest_input(rest_data):
        if PortMapper.REST_PORT_NETWORK_ID not in rest_data:
            raise NetworkIdRequiredForPortDataError()
        PortMapper._validate_common(rest_data)

    @staticmethod
    def validate_update_rest_input(rest_data):
        PortMapper._validate_common(rest_data)

    @staticmethod
    def _map_sec_group_names(group_names):
        return [
            SecurityGroupMapper._extract_security_group_id(group_name)
            for group_name in group_names
        ]

    @staticmethod
    def _validate_common(rest_data):
        Mapper._boolean_or_exception(
            PortMapper.REST_PORT_ADMIN_STATE_UP,
            rest_data.get(PortMapper.REST_PORT_ADMIN_STATE_UP, False),
        )
        Mapper._boolean_or_exception(
            PortMapper.REST_PORT_SECURITY_ENABLED,
            rest_data.get(PortMapper.REST_PORT_SECURITY_ENABLED, False),
        )
        rest_mac = rest_data.get(PortMapper.REST_PORT_MAC_ADDRESS)
        if rest_mac:
            try:
                EUI(rest_mac)
            except AddrFormatError:
                raise RestDataError(
                    'Invalid input for mac_address. Reason: \'{}\' is not a '
                    'valid MAC address.'.format(rest_mac)
                )
        fixed_ips = rest_data.get(PortMapper.REST_PORT_FIXED_IPS)
        if fixed_ips:
            if type(fixed_ips) is not list:
                raise RestDataError(
                    '{type} must be of type: list'.format(
                        type=PortMapper.REST_PORT_FIXED_IPS
                    )
                )
            if len(fixed_ips) > 1:
                raise RestDataError(
                    'Specifying more then one {type} value is not allowed'.format(  # noqa: E501
                        type=PortMapper.REST_PORT_FIXED_IPS
                    )
                )
            if type(fixed_ips[0]) is not dict:
                raise RestDataError(
                    '{type} must be a dictionary containing {ip_addr} and '
                    '{subnet_id}'.format(
                        type=PortMapper.REST_PORT_FIXED_IPS,
                        ip_addr=PortMapper.REST_PORT_IP_ADDRESS,
                        subnet_id=PortMapper.REST_PORT_SUBNET_ID,
                    )
                )
            if (
                PortMapper.REST_PORT_IP_ADDRESS not in fixed_ips[0]
                and PortMapper.REST_PORT_SUBNET_ID not in fixed_ips[0]
            ):
                raise RestDataError(
                    '{type} must contain at least the {ip_addr} or the '
                    '{subnet_id} element'.format(
                        type=PortMapper.REST_PORT_FIXED_IPS,
                        ip_addr=PortMapper.REST_PORT_IP_ADDRESS,
                        subnet_id=PortMapper.REST_PORT_SUBNET_ID,
                    )
                )
            ip_addr = fixed_ips[0].get(PortMapper.REST_PORT_IP_ADDRESS)
            if (
                ip_addr is not None
                and ip_utils.get_ip_version(ip_addr) is None
            ):
                raise RestDataError('Invalid IP address: {}'.format(ip_addr))


class NetworkIdRequiredForPortDataError(RestDataError):
    message = 'Network_id is a required parameter'

    def __init__(self):
        super(NetworkIdRequiredForPortDataError, self).__init__(self.message)


class PortDeviceIdRequiredDataError(RestDataError):
    message = 'Port device id must be specified to create a port'

    def __init__(self):
        super(PortDeviceIdRequiredDataError, self).__init__(self.message)


class PortSecurityNotSupportedDataError(RestDataError):
    message = 'Port port_security_enabled is not supported'

    def __init__(self):
        super(PortSecurityNotSupportedDataError, self).__init__(self.message)
