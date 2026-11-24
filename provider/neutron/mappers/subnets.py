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

from netaddr import IPNetwork
import neutron.ip as ip_utils
from ovirt_provider_config_common import dhcp_ipv6_address_mode
from ovirt_provider_config_common import tenant_id
from handlers.base_handler import BadRequestError
from neutron.mappers.base import Mapper
from neutron.mappers.base import UnsupportedDataValueError


class SubnetMapper(Mapper):
    REST_SUBNET_ID = 'id'
    REST_SUBNET_NAME = 'name'
    REST_SUBNET_CIDR = 'cidr'
    REST_SUBNET_NETWORK_ID = 'network_id'
    REST_SUBNET_DNS_NAMESERVERS = 'dns_nameservers'
    REST_SUBNET_GATEWAY_IP = 'gateway_ip'
    REST_SUBNET_ENABLE_DHCP = 'enable_dhcp'
    REST_SUBNET_IP_VERSION = 'ip_version'
    REST_SUBNET_ALLOCATION_POOLS = 'allocation_pools'
    REST_SUBNET_ALLOCATION_POOLS_START = 'start'
    REST_SUBNET_ALLOCATION_POOLS_STOP = 'end'
    REST_SUBNET_IPV6_ADDRESS_MODE = 'ipv6_address_mode'
    REST_SUBNET_TAGS = "tags"
    REST_SUBNET_SERVICE_TYPES = "service_types"
    REST_SUBNET_HOST_ROUTES = "host_routes"

    # REST layout: https://docs.openstack.org/api-ref/network/v2/#subnets

    OVN_NAME = 'ovirt_name'
    OVN_NETWORK_ID = 'ovirt_network_id'
    OVN_DNS_SERVER = 'dns_server'
    OVN_GATEWAY = 'router'
    OVN_DHCP_SERVER_ID = 'server_id'
    OVN_DHCP_SERVER_MAC = 'server_mac'
    OVN_DHCP_LEASE_TIME = 'lease_time'
    OVN_DHCP_MTU = 'mtu'
    OVN_DHCPV6_STATEFUL = 'dhcpv6_stateful'
    OVN_DHCPV6_STATELESS = 'dhcpv6_stateless'
    OVN_GATEWAY_ROUTER_ID = 'gateway_router'
    OVN_IP_VERSION = 'ip_version'
    OVN_IPV6_ADDRESS_MODE = 'ovirt_ipv6_address_mode'

    IP_VERSION_4 = 4
    IP_VERSION_6 = 6
    ALLOWED_IP_VERSIONS = [IP_VERSION_4, IP_VERSION_6]

    IPV6_ADDRESS_MODE_STATEFUL = 'dhcpv6-stateful'
    IPV6_ADDRESS_MODE_STATELESS = 'dhcpv6-stateless'

    rest_ipv6_address_mode = {
        OVN_DHCPV6_STATEFUL: IPV6_ADDRESS_MODE_STATEFUL,
        OVN_DHCPV6_STATELESS: IPV6_ADDRESS_MODE_STATELESS,
    }

    ovn_ipv6_address_mode = {v: k for k, v in rest_ipv6_address_mode.items()}

    # allow raw OVN values on OpenStack API for backward compatibility
    ovn_ipv6_address_mode.update(
        {
            OVN_DHCPV6_STATEFUL: OVN_DHCPV6_STATEFUL,
            OVN_DHCPV6_STATELESS: OVN_DHCPV6_STATELESS,
        }
    )

    ALLOWED_IPV6_ADDRESS_MODES = sorted(list(ovn_ipv6_address_mode.keys()))

    _optional_update_data = {
        REST_SUBNET_NAME,
        REST_SUBNET_ENABLE_DHCP,
        REST_SUBNET_DNS_NAMESERVERS,
        REST_SUBNET_ALLOCATION_POOLS,
        REST_SUBNET_GATEWAY_IP,
    }

    @staticmethod
    def rest2row(wrapped_self, func, rest_data, subnet_id):
        name = rest_data.get(SubnetMapper.REST_SUBNET_NAME)
        cidr = rest_data.get(SubnetMapper.REST_SUBNET_CIDR)
        network_id = rest_data.get(SubnetMapper.REST_SUBNET_NETWORK_ID)
        dnses = rest_data.get(SubnetMapper.REST_SUBNET_DNS_NAMESERVERS)
        gateway = rest_data.get(SubnetMapper.REST_SUBNET_GATEWAY_IP)
        ip_version = rest_data.get(SubnetMapper.REST_SUBNET_IP_VERSION)
        ipv6_address_mode = SubnetMapper.ovn_ipv6_address_mode.get(
            rest_data.get(
                SubnetMapper.REST_SUBNET_IPV6_ADDRESS_MODE,
                dhcp_ipv6_address_mode() if ip_version == 6 else None,
            )
        )

        if dnses:
            if len(dnses) > 1:
                dns = '{' + ','.join(dnses) + '}'
            else:
                dns = dnses[0]
        else:
            dns = None

        if subnet_id:
            return func(
                wrapped_self,
                subnet_id=subnet_id,
                name=name,
                gateway=gateway,
                dns=dns,
            )
        else:
            return func(
                wrapped_self,
                name=name,
                cidr=cidr,
                network_id=network_id,
                gateway=gateway,
                dns=dns,
                ip_version=ip_version,
                ipv6_address_mode=ipv6_address_mode,
            )

    @staticmethod
    def _dns_to_rest(dns_value):
        """
        OVN keeps a single dns server as 'ip' and several as '{ip1, ip2}'.
        """
        if not dns_value:
            return []
        return [
            dns.strip()
            for dns in dns_value.strip().strip('{}').split(',')
            if dns.strip()
        ]

    @staticmethod
    def row2rest(row):
        if not row:
            return {}
        options = row.options
        external_ids = row.external_ids
        ipv4 = ip_utils.is_subnet_ipv4(row)
        result = {
            SubnetMapper.REST_SUBNET_ID: str(row.uuid),
            SubnetMapper.REST_SUBNET_CIDR: row.cidr,
            SubnetMapper.REST_SUBNET_NETWORK_ID: external_ids[
                SubnetMapper.OVN_NETWORK_ID
            ],
            SubnetMapper.REST_SUBNET_IP_VERSION: ip_utils.get_subnet_ip_version(  # noqa: E501
                row
            ),
            SubnetMapper.REST_TENANT_ID: tenant_id(),
            SubnetMapper.REST_SUBNET_ENABLE_DHCP: True,
            SubnetMapper.REST_SUBNET_ALLOCATION_POOLS: [
                SubnetMapper.get_allocation_pool(row.cidr),
            ],
            SubnetMapper.REST_SUBNET_DNS_NAMESERVERS: (
                SubnetMapper._dns_to_rest(
                    options.get(SubnetMapper.OVN_DNS_SERVER)
                )
            ),
            SubnetMapper.REST_SUBNET_TAGS: [],
            SubnetMapper.REST_SUBNET_SERVICE_TYPES: [],
            SubnetMapper.REST_SUBNET_HOST_ROUTES: [],
        }
        if SubnetMapper.OVN_NAME in external_ids:
            result[SubnetMapper.REST_SUBNET_NAME] = external_ids[
                SubnetMapper.OVN_NAME
            ]
        if ipv4 and SubnetMapper.OVN_GATEWAY in options:
            result[SubnetMapper.REST_SUBNET_GATEWAY_IP] = options[
                SubnetMapper.OVN_GATEWAY
            ]
        elif not ipv4 and SubnetMapper.OVN_GATEWAY in external_ids:
            result[SubnetMapper.REST_SUBNET_GATEWAY_IP] = external_ids[
                SubnetMapper.OVN_GATEWAY
            ]
        if SubnetMapper.OVN_IPV6_ADDRESS_MODE in external_ids:
            result[SubnetMapper.REST_SUBNET_IPV6_ADDRESS_MODE] = (
                SubnetMapper.rest_ipv6_address_mode[
                    external_ids[SubnetMapper.OVN_IPV6_ADDRESS_MODE]
                ]
            )

        return result

    @staticmethod
    def get_allocation_pool(cidr):
        ip_network = IPNetwork(cidr)
        if ip_network.size > 2:
            return {
                SubnetMapper.REST_SUBNET_ALLOCATION_POOLS_START: str(
                    ip_network[2]
                ),
                SubnetMapper.REST_SUBNET_ALLOCATION_POOLS_STOP: str(
                    ip_network[-1]
                ),
            }

    @staticmethod
    def validate_add_rest_input(rest_data):
        SubnetMapper._validate_common(rest_data)
        if SubnetMapper.REST_SUBNET_IP_VERSION not in rest_data:
            raise BadRequestError('Missing \'ip_version\' attribute')
        ip_version = rest_data[SubnetMapper.REST_SUBNET_IP_VERSION]
        if (
            ip_version != SubnetMapper.IP_VERSION_6
            and SubnetMapper.REST_SUBNET_IPV6_ADDRESS_MODE in rest_data
        ):
            raise BadRequestError(
                'The \'{}\' parameter can only be used when \'ip_version\' '
                '== 6'.format(SubnetMapper.REST_SUBNET_IPV6_ADDRESS_MODE)
            )
        cidr = rest_data.get(SubnetMapper.REST_SUBNET_CIDR)
        SubnetMapper._validate_ip_version_consistency(
            ip_version,
            cidr=cidr,
            gateway=rest_data.get(SubnetMapper.REST_SUBNET_GATEWAY_IP),
        )
        if (
            ip_version == SubnetMapper.IP_VERSION_6
            and rest_data.get(
                SubnetMapper.REST_SUBNET_IPV6_ADDRESS_MODE,
                dhcp_ipv6_address_mode(),
            )
            != SubnetMapper.IPV6_ADDRESS_MODE_STATEFUL
        ):
            SubnetMapper._validate_stateless_address_mode(cidr)

    @classmethod
    def validate_update_rest_input(cls, rest_data):
        cls.validate_keys(
            set(rest_data.keys()), set(), cls._optional_update_data
        )
        SubnetMapper._validate_common(rest_data)

    @staticmethod
    def _validate_ip_version_consistency(ip_version, cidr, gateway):
        if ip_version not in SubnetMapper.ALLOWED_IP_VERSIONS:
            raise BadRequestError('\'ip_version\' must be either 4 or 6')
        cidr_ip_version = IPNetwork(cidr).version
        gateway_ip_version = IPNetwork(gateway).version if gateway else None
        if (
            len(
                {ip_version, cidr_ip_version, gateway_ip_version or ip_version}
            )
            != 1
        ):
            raise BadRequestError(
                'The provided ip_version [{ip}] does not match the supplied '
                'cidr={cidr} or gateway={gateway}'.format(
                    ip=ip_version, cidr=cidr, gateway=gateway
                )
            )

    @staticmethod
    def _validate_stateless_address_mode(cidr):
        if int(ip_utils.get_mask_from_cidr(cidr)) != 64:
            raise BadRequestError(
                'Invalid CIDR {} for IPv6 address mode. '
                'OVN uses the EUI-64 address format, '
                'which requires the prefix to be /64'.format(cidr)
            )

    @staticmethod
    def _validate_common(rest_data):
        if (
            SubnetMapper.REST_SUBNET_ENABLE_DHCP in rest_data
            and not rest_data[SubnetMapper.REST_SUBNET_ENABLE_DHCP]
        ):
            raise UnsupportedDataValueError(
                SubnetMapper.REST_SUBNET_ENABLE_DHCP, False
            )
        if (
            SubnetMapper.REST_SUBNET_IPV6_ADDRESS_MODE in rest_data
            and rest_data.get(SubnetMapper.REST_SUBNET_IPV6_ADDRESS_MODE)
            not in SubnetMapper.ALLOWED_IPV6_ADDRESS_MODES
        ):
            raise UnsupportedDataValueError(
                SubnetMapper.REST_SUBNET_IPV6_ADDRESS_MODE,
                rest_data.get(SubnetMapper.REST_SUBNET_IPV6_ADDRESS_MODE),
                SubnetMapper.ALLOWED_IPV6_ADDRESS_MODES,
            )


class SubnetConfigError(BadRequestError):
    pass
