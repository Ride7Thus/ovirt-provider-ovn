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
import constants as ovnconst
from ovirt_provider_config_common import dhcp_mtu
from ovirt_provider_config_common import tenant_id
from ovirt_provider_config_common import max_allowed_mtu
from neutron.mappers.base import Mapper
from neutron.mappers.base import RestDataError


Network = namedtuple('Network', ['ls', 'localnet_lsp'])


class NetworkMapper(Mapper):
    # The names of properties received/sent in a REST request
    REST_MTU = 'mtu'
    REST_NETWORK_ID = 'id'
    REST_NETWORK_NAME = 'name'
    REST_STATUS = 'status'
    REST_PROVIDER_NETWORK_TYPE = 'provider:network_type'
    REST_PROVIDER_PHYSICAL_NETWORK = 'provider:physical_network'
    REST_PROVIDER_SEGMENTATION_ID = 'provider:segmentation_id'
    REST_PORT_SECURITY_ENABLED = 'port_security_enabled'

    OVN_MTU = 'mtu'
    OVN_NETWORK_NAME = 'ovirt_network_name'
    OVN_NETWORK_PORT_SECURITY = 'ovirt_port_security'
    NETWORK_TYPE_FLAT = 'flat'
    NETWORK_TYPE_VLAN = 'vlan'

    OVN_SUBNET = 'subnet'
    OVN_IPV6_PREFIX = 'ipv6_prefix'

    NETWORK_STATUS_ACTIVE = 'ACTIVE'

    @staticmethod
    def rest2row(wrapped_self, func, rest_network_data, network_id):
        network_name = rest_network_data.get(NetworkMapper.REST_NETWORK_NAME)
        provider_physical_network = rest_network_data.get(
            NetworkMapper.REST_PROVIDER_PHYSICAL_NETWORK
        )
        provider_segmentation_id = rest_network_data.get(
            NetworkMapper.REST_PROVIDER_SEGMENTATION_ID
        )
        mtu = rest_network_data.get(NetworkMapper.REST_MTU)
        port_security = rest_network_data.get(
            NetworkMapper.REST_PORT_SECURITY_ENABLED
        )
        if network_id:
            return func(
                wrapped_self,
                network_id,
                name=network_name,
                localnet=provider_physical_network,
                vlan=provider_segmentation_id,
                mtu=mtu,
                port_security_enabled=port_security,
            )
        return func(
            wrapped_self,
            name=network_name,
            localnet=provider_physical_network,
            vlan=provider_segmentation_id,
            mtu=mtu,
            port_security_enabled=port_security,
        )

    @staticmethod
    def row2rest(network):
        if not network:
            return {}
        ls, localnet_lsp = network.ls, network.localnet_lsp
        network_name = ls.external_ids.get(NetworkMapper.OVN_NETWORK_NAME)
        result = {
            NetworkMapper.REST_NETWORK_ID: str(ls.uuid),
            NetworkMapper.REST_NETWORK_NAME: network_name or ls.name,
            NetworkMapper.REST_TENANT_ID: tenant_id(),
            NetworkMapper.REST_STATUS: NetworkMapper.NETWORK_STATUS_ACTIVE,
            NetworkMapper.REST_PORT_SECURITY_ENABLED: Mapper._str2bool(
                str(
                    ls.external_ids.get(
                        NetworkMapper.OVN_NETWORK_PORT_SECURITY, False
                    )
                )
            ),
        }
        result[NetworkMapper.REST_MTU] = int(
            ls.external_ids.get(NetworkMapper.OVN_MTU, dhcp_mtu())
        )
        result.update(NetworkMapper._row2rest_localnet(localnet_lsp))
        return result

    @staticmethod
    def _row2rest_localnet(localnet_lsp):
        if not localnet_lsp:
            return {}
        result = {
            NetworkMapper.REST_PROVIDER_PHYSICAL_NETWORK: localnet_lsp.options.get(  # noqa: E501
                ovnconst.LSP_OPTION_NETWORK_NAME
            )
        }
        ovn_vlan = localnet_lsp.tag
        if ovn_vlan:
            result[NetworkMapper.REST_PROVIDER_SEGMENTATION_ID] = int(
                ovn_vlan[0]
            )
            result[NetworkMapper.REST_PROVIDER_NETWORK_TYPE] = (
                NetworkMapper.NETWORK_TYPE_VLAN
            )
        else:
            result[NetworkMapper.REST_PROVIDER_NETWORK_TYPE] = (
                NetworkMapper.NETWORK_TYPE_FLAT
            )
        return result

    @staticmethod
    def validate_add_rest_input(rest_data):
        NetworkMapper._validate_rest_input(rest_data)

    @staticmethod
    def validate_update_rest_input(rest_data):
        NetworkMapper._validate_rest_input(rest_data, check_name=False)

    @staticmethod
    def _validate_rest_input(rest_data, check_name=True):
        if check_name and NetworkMapper.REST_NETWORK_NAME not in rest_data:
            raise NetworkNameRequiredDataError()
        Mapper._boolean_or_exception(
            NetworkMapper.REST_PORT_SECURITY_ENABLED,
            rest_data.get(NetworkMapper.REST_PORT_SECURITY_ENABLED, False),
        )
        NetworkMapper._validate_rest_input_provider_network(rest_data)
        NetworkMapper._validate_rest_input_max_mtu(
            rest_data.get(NetworkMapper.REST_MTU)
        )

    @staticmethod
    def _validate_rest_input_provider_network(rest_data):
        network_type = rest_data.get(NetworkMapper.REST_PROVIDER_NETWORK_TYPE)
        if not network_type:
            if NetworkMapper.REST_PROVIDER_PHYSICAL_NETWORK in rest_data:
                raise PhysicalNetworkProviderDataError(
                    'provider:physical_network cannot be used without a '
                    'specified provider:network_type'
                )
            elif NetworkMapper.REST_PROVIDER_SEGMENTATION_ID in rest_data:
                raise PhysicalNetworkProviderDataError(
                    'provider:segmentation_id cannot be used without a '
                    'specified provider:network_type'
                )
        elif network_type == NetworkMapper.NETWORK_TYPE_FLAT:
            if NetworkMapper.REST_PROVIDER_PHYSICAL_NETWORK not in rest_data:
                raise PhysicalNetworkProviderDataError(
                    'provider:physical_network is mandatory for network type '
                    'flat'
                )
            elif NetworkMapper.REST_PROVIDER_SEGMENTATION_ID in rest_data:
                raise PhysicalNetworkProviderDataError(
                    'provider:segmentation_id can only be used with network '
                    'type vlan'
                )
        elif network_type == NetworkMapper.NETWORK_TYPE_VLAN:
            if NetworkMapper.REST_PROVIDER_SEGMENTATION_ID not in rest_data:
                raise PhysicalNetworkProviderDataError(
                    'provider:segmentation_id is mandatory for network type '
                    'vlan'
                )
            elif NetworkMapper.REST_PROVIDER_PHYSICAL_NETWORK not in rest_data:
                raise PhysicalNetworkProviderDataError(
                    'provider:physical_network is mandatory for network type '
                    'vlan'
                )
        else:
            raise PhysicalNetworkProviderDataError(
                'provider:network_type [{}] is not supported'.format(
                    network_type
                )
            )

    @staticmethod
    def _validate_rest_input_max_mtu(mtu):
        configured_max_mtu = max_allowed_mtu()
        if configured_max_mtu != 0 and mtu > configured_max_mtu:
            raise InvalidMtuDataError(
                'Requested MTU is too big, maximum is {max_mtu}'.format(
                    max_mtu=configured_max_mtu
                )
            )


class NetworkNameRequiredDataError(RestDataError):
    message = 'Network name is a required parameter'

    def __init__(self):
        super(NetworkNameRequiredDataError, self).__init__(self.message)


class InvalidMtuDataError(RestDataError):
    pass


class PhysicalNetworkProviderDataError(RestDataError):
    pass
