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
import constants as ovnconst
import neutron.ip as ip_utils
import neutron.validation as validate
from handlers.base_handler import ElementNotFoundError
from neutron.mappers.networks import NetworkMapper
from neutron.mappers.subnets import SubnetConfigError
from neutron.mappers.subnets import SubnetMapper
from ovirt_provider_config_common import dhcp_lease_time
from ovirt_provider_config_common import dhcp_server_mac
from ovirt_provider_config_common import dhcp_enable_mtu
from ovirt_provider_config_common import dhcp_mtu
from neutron.api.base import NeutronApiBase


# The resource APIs are mixins of NeutronApi and call each other through
# it, which pylint can not see.
# pylint: disable=no-member


class SubnetsApi(NeutronApiBase):
    """Subnets (OVN DHCP options)."""

    @SubnetMapper.map_to_rest
    def list_subnets(self):
        return self.ovn_north.list_dhcp()

    @SubnetMapper.map_to_rest
    def get_subnet(self, subnet_id):
        return self.ovn_north.get_dhcp(dhcp_id=subnet_id)

    @SubnetMapper.validate_add
    @SubnetMapper.map_from_rest
    def add_subnet(
        self,
        name,
        cidr,
        network_id,
        gateway,
        ip_version,
        dns=None,
        ipv6_address_mode=None,
    ):
        try:
            network = self.ovn_north.get_ls(ls_id=network_id)
        except ElementNotFoundError:
            raise SubnetConfigError(
                'Subnet can not be created, network {}'
                ' does not exist'.format(network_id)
            )

        if self.ovn_north.get_dhcp(ls_id=network_id):
            raise SubnetConfigError(
                'Unable to create more than one subnet'
                ' for network {}'.format(network_id)
            )

        network_mtu = network.external_ids.get(SubnetMapper.OVN_DHCP_MTU)
        external_ids = self.get_subnet_external_ids(
            network_id,
            ip_version,
            name,
            ipv6_address_mode,
            gateway,
            network_mtu or (dhcp_mtu() if dhcp_enable_mtu() else None),
        )
        options = self.get_subnet_options(
            cidr, gateway, network_mtu, dns, ipv6_address_mode
        )

        self.ovn_north.db_set(
            ovnconst.TABLE_LS,
            network_id,
            (ovnconst.ROW_LS_OTHER_CONFIG, self.get_ls_options(cidr)),
        )

        subnet = self.ovn_north.add_dhcp_options(cidr, external_ids)
        self.ovn_north.set_dhcp_options_options_column(subnet.uuid, options)

        for port in network.ports:
            if self._is_port_address_value_static(port.type):
                continue
            self.get_update_port_addr_command(
                port, network_id=network_id
            ).execute()

        return self.get_subnet(subnet.uuid)

    @staticmethod
    def get_ls_options(cidr):
        network = IPNetwork(cidr)
        if network.version == SubnetMapper.IP_VERSION_4:
            options = {NetworkMapper.OVN_SUBNET: cidr}
        else:
            options = {NetworkMapper.OVN_IPV6_PREFIX: str(network[0])}
        return options

    @staticmethod
    def get_subnet_options(
        cidr, gateway, network_mtu, dns, ipv6_address_mode=None
    ):
        network = IPNetwork(cidr)
        if network.version == SubnetMapper.IP_VERSION_4:
            options = {
                SubnetMapper.OVN_DHCP_SERVER_ID: cidr.split('/', 1)[0],
                SubnetMapper.OVN_DHCP_SERVER_MAC: dhcp_server_mac(),
                SubnetMapper.OVN_DHCP_LEASE_TIME: dhcp_lease_time(),
            }
            if gateway:
                options[SubnetMapper.OVN_GATEWAY] = gateway
            if network_mtu:
                options[SubnetMapper.OVN_DHCP_MTU] = network_mtu
            elif dhcp_enable_mtu():
                options[SubnetMapper.OVN_DHCP_MTU] = dhcp_mtu()
        else:
            options = {SubnetMapper.OVN_DHCP_SERVER_ID: dhcp_server_mac()}
            if ipv6_address_mode == SubnetMapper.IPV6_ADDRESS_MODE_STATELESS:
                options[SubnetMapper.OVN_DHCPV6_STATELESS] = "true"
        if dns:
            options[SubnetMapper.OVN_DNS_SERVER] = dns
        return options

    @staticmethod
    def get_subnet_external_ids(
        network_id, ip_version, name, ipv6_address_mode, gateway, mtu
    ):
        external_ids = {
            SubnetMapper.OVN_NETWORK_ID: network_id,
            SubnetMapper.OVN_IP_VERSION: str(ip_version),
        }
        if name:
            external_ids[SubnetMapper.OVN_NAME] = name
        if ipv6_address_mode:
            external_ids[SubnetMapper.OVN_IPV6_ADDRESS_MODE] = (
                ipv6_address_mode
            )
            external_ids[SubnetMapper.OVN_DHCP_MTU] = mtu
        if ip_version == SubnetMapper.IP_VERSION_6 and gateway:
            external_ids[SubnetMapper.OVN_GATEWAY] = gateway
        return external_ids

    @SubnetMapper.validate_update
    @SubnetMapper.map_from_rest
    def update_subnet(
        self,
        subnet_id,
        name=None,
        gateway=None,
        dns=None,
    ):
        subnet = self.ovn_north.get_dhcp(dhcp_id=subnet_id)
        self.ovn_north.create_ovn_update_command(
            ovnconst.TABLE_DHCP_Options, subnet_id
        ).add(
            ovnconst.ROW_DHCP_EXTERNAL_IDS, {SubnetMapper.OVN_NAME: name}, name
        ).add(
            (
                ovnconst.ROW_DHCP_OPTIONS
                if ip_utils.is_subnet_ipv4(subnet)
                else ovnconst.ROW_DHCP_EXTERNAL_IDS
            ),
            {SubnetMapper.OVN_GATEWAY: gateway},
            gateway,
        ).add(
            ovnconst.ROW_DHCP_OPTIONS, {SubnetMapper.OVN_DNS_SERVER: dns}, dns
        ).add(
            ovnconst.ROW_DHCP_OPTIONS,
            {SubnetMapper.OVN_DHCP_LEASE_TIME: dhcp_lease_time()},
        ).add(
            ovnconst.ROW_DHCP_OPTIONS,
            {SubnetMapper.OVN_DHCP_SERVER_MAC: dhcp_server_mac()},
        ).execute()

        return self.get_subnet(subnet_id)

    def delete_subnet(self, subnet_id):
        subnet = self.ovn_north.get_dhcp(dhcp_id=subnet_id)
        validate.subnet_not_connected_to_router(
            self._get_subnet_gateway_router_id(subnet), subnet_id
        )
        network_id = subnet.external_ids.get(SubnetMapper.OVN_NETWORK_ID)
        network = self.ovn_north.get_ls(ls_id=network_id)
        self.ovn_north.remove_dhcp_options(subnet_id)
        for port in network.ports:
            if self._is_port_address_value_static(port.type):
                continue
            self.get_update_port_addr_command(
                port, network_id=network_id
            ).execute()
