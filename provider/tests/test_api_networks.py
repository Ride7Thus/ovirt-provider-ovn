# coding=utf-8
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

import unittest.mock as mock
import constants as ovnconst
from neutron.mappers.networks import Network
from neutron.mappers.networks import NetworkMapper
from neutron.mappers.subnets import SubnetMapper
from neutron.neutron_api import NeutronApi
from ovirt_provider_config_common import dhcp_lease_time
from ovirt_provider_config_common import dhcp_server_mac
from ovntestlib import assert_network_equal
from ovntestlib import assert_subnet_equal
from ovntestlib import NetworkApiInputMaker
from ovntestlib import SubnetApiInputMaker
from ovntestlib import OvnNetworkRow
from ovn_north_data import OvnNorthData
from ovn_north_data import extend_call_by_version


@mock.patch('ovsdbapp.backend.ovs_idl.connection', autospec=False)
class TestNetworksApi(OvnNorthData):
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsListCommand', autospec=False
    )
    def test_get_networks(self, mock_ls_list, mock_connection):
        mock_ls_list.return_value.execute.return_value = OvnNorthData.networks

        ovn_north = NeutronApi()
        result = ovn_north.list_networks()

        assert len(result) == 3
        assert_network_equal(
            result[0], Network(ls=OvnNorthData.NETWORK_10, localnet_lsp=None)
        )
        assert_network_equal(
            result[1], Network(ls=OvnNorthData.NETWORK_11, localnet_lsp=None)
        )
        localnet_network = OvnNorthData.NETWORK_LOCALNET_12
        assert_network_equal(
            result[2],
            Network(
                ls=localnet_network, localnet_lsp=localnet_network.ports[0]
            ),
        )
        assert mock_ls_list.call_count == 1
        assert mock_ls_list.return_value.execute.call_count == 1

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsGetCommand', autospec=False
    )
    def test_get_network(self, mock_ls_get, mock_connection):
        mock_ls_get.return_value.execute.return_value = OvnNorthData.NETWORK_10
        ovn_north = NeutronApi()
        result = ovn_north.get_network(str(OvnNorthData.NETWORK_ID10))

        network = Network(ls=OvnNorthData.NETWORK_10, localnet_lsp=None)
        assert_network_equal(result, network)
        assert mock_ls_get.call_count == 1
        assert mock_ls_get.return_value.execute.call_count == 1
        assert mock_ls_get.mock_calls[0] == mock.call(
            ovn_north.idl, str(OvnNorthData.NETWORK_ID10)
        )

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsGetCommand.execute',
        lambda cmd, check_error: OvnNorthData.NETWORK_10,
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.transaction.Transaction.commit',
        lambda x: None,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsAddCommand', autospec=False
    )
    def test_add_network(self, mock_add_command, mock_connection):
        self._test_add_network(mock_add_command, OvnNorthData.NETWORK_10)

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsGetCommand.execute',
        lambda cmd, check_error: OvnNorthData.NETWORK_UNICODE,
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.transaction.Transaction.commit',
        lambda x: None,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsAddCommand', autospec=False
    )
    def test_add_network_with_unicode_name(
        self, mock_add_command, mock_connection
    ):
        self._test_add_network(mock_add_command, OvnNorthData.NETWORK_UNICODE)

    def _test_add_network(self, mock_add_command, network_row):
        mock_add_command.return_value.execute.return_value = network_row
        ovn_north = NeutronApi()
        rest_data = NetworkApiInputMaker(network_row.name).get()
        result = ovn_north.add_network(rest_data)

        network = Network(ls=network_row, localnet_lsp=None)
        assert_network_equal(result, network)
        assert mock_add_command.call_count == 1
        assert mock_add_command.mock_calls[0] == mock.call(
            ovn_north.idl,
            mock.ANY,
            False,
            external_ids={
                NetworkMapper.OVN_NETWORK_NAME: (network_row.name),
                NetworkMapper.OVN_NETWORK_PORT_SECURITY: 'False',
            },
        )

    @mock.patch(
        'ovsdbapp.backend.ovs_idl.transaction.Transaction.commit',
        lambda x: None,
    )
    @mock.patch('ovsdbapp.schema.ovn_northbound.commands.LsAddCommand')
    @mock.patch('ovsdbapp.schema.ovn_northbound.commands.LsGetCommand')
    @mock.patch('ovsdbapp.schema.ovn_northbound.commands.LspAddCommand')
    @mock.patch('ovsdbapp.backend.ovs_idl.command.DbSetCommand')
    def test_add_localnet_network(
        self,
        mock_db_set_command,
        mock_lsp_add_command,
        mock_ls_get_command,
        mock_ls_add_command,
        mock_connection,
    ):
        mock_ls_get_command.return_value.execute.return_value = (
            OvnNorthData.NETWORK_LOCALNET_12
        )
        mock_ls_add_command.return_value.execute.return_value = (
            OvnNorthData.NETWORK_LOCALNET_12
        )
        ovn_north = NeutronApi()
        rest_data = NetworkApiInputMaker(
            OvnNorthData.NETWORK_NAME12,
            provider_type=NetworkMapper.NETWORK_TYPE_VLAN,
            provider_physical_network=OvnNorthData.LOCALNET_NAME,
            vlan_tag=OvnNorthData.LOCALNET_VLAN,
        ).get()
        result = ovn_north.add_network(rest_data)

        localnet_network = OvnNorthData.NETWORK_LOCALNET_12
        assert_network_equal(
            result,
            Network(
                ls=localnet_network, localnet_lsp=localnet_network.ports[0]
            ),
        )
        assert mock_ls_add_command.call_count == 1
        assert mock_ls_add_command.mock_calls[0] == mock.call(
            ovn_north.idl,
            mock.ANY,
            False,
            external_ids={
                NetworkMapper.OVN_NETWORK_NAME: (OvnNorthData.NETWORK_NAME12),
                NetworkMapper.OVN_NETWORK_PORT_SECURITY: 'False',
            },
        )
        assert mock_lsp_add_command.call_count == 1
        assert mock_lsp_add_command.mock_calls[0] == mock.call(
            ovn_north.idl,
            mock.ANY,
            mock.ANY,
            None,
            None,
            False,
            external_ids={
                'ovirt_nic_name': ovnconst.LOCALNET_SWITCH_PORT_NAME
            },
        )
        assert mock_db_set_command.call_count == 1
        assert mock_ls_get_command.call_count == 1

    @mock.patch(
        'ovsdbapp.backend.ovs_idl.transaction.Transaction.commit',
        lambda x: None,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsGetCommand.'
        'execute',
        lambda cmd, check_error: OvnNorthData.SUBNET_MTU,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsAddCommand.'
        'execute',
        lambda cmd, check_error: OvnNorthData.SUBNET_MTU,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsListCommand.'
        'execute',
        lambda cmd, check_error: [],
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsAddCommand.execute',
        lambda cmd, check_error: OvnNorthData.NETWORK_MTU,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsGetCommand.execute',
        lambda cmd, check_error: OvnNorthData.NETWORK_MTU,
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbSetCommand', autospec=False
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsSetOptionsCommand',
        autospec=False,
    )
    def test_add_network_with_mtu(
        self, mock_setoptions_command, mock_dbset_command, mock_connection
    ):
        ovn_north = NeutronApi()
        network_rest_data = NetworkApiInputMaker(
            OvnNorthData.NETWORK_NAMEMTU, mtu=OvnNorthData.VALUE_NETWORK_MTU
        ).get()
        network_creation_result = ovn_north.add_network(network_rest_data)
        assert_network_equal(
            network_creation_result,
            Network(ls=OvnNorthData.NETWORK_MTU, localnet_lsp=None),
        )

        # create a subnet associated with the above network
        subnet_rest_data = SubnetApiInputMaker(
            OvnNorthData.SUBNET_102.external_ids.get(SubnetMapper.OVN_NAME),
            cidr=OvnNorthData.SUBNET_CIDR,
            network_id=str(OvnNorthData.NETWORK_IDMTU),
            dns_nameservers=['1.1.1.1'],
            gateway_ip='1.1.1.0',
            ip_version=4,
        ).get()

        expected_options_call = mock.call(
            ovn_north.idl,
            OvnNorthData.SUBNET_IDMTU,
            dns_server='1.1.1.1',
            lease_time=dhcp_lease_time(),
            router='1.1.1.0',
            server_id='1.1.1.0',
            server_mac=dhcp_server_mac(),
            mtu=str(OvnNorthData.VALUE_NETWORK_MTU),
        )

        subnet_creation_result = ovn_north.add_subnet(subnet_rest_data)
        assert mock_setoptions_command.call_count == 1
        assert mock_setoptions_command.mock_calls[0] == expected_options_call
        assert mock_dbset_command.call_count == 1
        assert_subnet_equal(subnet_creation_result, OvnNorthData.SUBNET_MTU)

    @mock.patch(
        'ovsdbapp.backend.ovs_idl.transaction.Transaction.commit',
        lambda x: None,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsGetCommand.'
        'execute',
        lambda cmd, check_error: OvnNorthData.SUBNET_MTU,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsAddCommand.'
        'execute',
        lambda cmd, check_error: OvnNorthData.SUBNET_MTU,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsAddCommand.execute',
        lambda cmd, check_error: OvnNorthData.NETWORK_MTU,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsGetCommand.execute',
        lambda cmd, check_error: OvnNorthData.NETWORK_MTU,
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbSetCommand', autospec=False
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsSetOptionsCommand',
        autospec=False,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsListCommand'
    )
    def test_update_networks_mtu(
        self,
        mock_dhcp_list_command,
        mock_setoptions_command,
        mock_dbset_command,
        mock_connection,
    ):
        mock_dhcp_list_command.return_value.execute.return_value = []

        ovn_north = NeutronApi()
        network_rest_data = NetworkApiInputMaker(
            OvnNorthData.NETWORK_NAMEMTU, mtu=OvnNorthData.VALUE_NETWORK_MTU
        ).get()
        ovn_north.add_network(network_rest_data)

        # create a subnet associated with the above network
        subnet_rest_data = SubnetApiInputMaker(
            OvnNorthData.SUBNET_102.external_ids.get(SubnetMapper.OVN_NAME),
            cidr=OvnNorthData.SUBNET_CIDR,
            network_id=str(OvnNorthData.NETWORK_IDMTU),
            dns_nameservers=['1.1.1.1'],
            gateway_ip='1.1.1.0',
            ip_version=4,
        ).get()

        ovn_north.add_subnet(subnet_rest_data)
        new_mtu = 14999
        mtu_update = NetworkApiInputMaker(
            OvnNorthData.NETWORK_NAMEMTU, mtu=new_mtu
        ).get()

        assert mock_setoptions_command.call_count == 1
        mock_dhcp_list_command.return_value.execute.return_value = [
            OvnNorthData.SUBNET_MTU
        ]

        ovn_north.update_network(mtu_update, OvnNorthData.NETWORK_IDMTU)
        expected_external_ids_update = extend_call_by_version(
            mock.call(
                ovn_north.idl,
                ovnconst.TABLE_LS,
                OvnNorthData.NETWORK_IDMTU,
                (
                    ovnconst.ROW_LS_EXTERNAL_IDS,
                    {
                        NetworkMapper.OVN_NETWORK_NAME: (
                            OvnNorthData.NETWORK_NAMEMTU
                        ),
                        NetworkMapper.REST_MTU: str(new_mtu),
                    },
                ),
            ),
            if_exists=True,
        )
        expected_network_mtu_update = extend_call_by_version(
            mock.call(
                ovn_north.idl,
                ovnconst.TABLE_DHCP_Options,
                OvnNorthData.SUBNET_IDMTU,
                (
                    ovnconst.ROW_DHCP_OPTIONS,
                    {SubnetMapper.OVN_DHCP_MTU: str(new_mtu)},
                ),
            ),
            if_exists=True,
        )
        assert expected_external_ids_update in mock_dbset_command.mock_calls
        assert expected_network_mtu_update in mock_dbset_command.mock_calls

    @mock.patch(
        'ovsdbapp.backend.ovs_idl.transaction.Transaction.commit',
        lambda x: None,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsGetCommand.execute',
        lambda cmd, check_error: OvnNetworkRow(
            OvnNorthData.NETWORK_ID10, OvnNorthData.NETWORK_NAME10
        ),
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbSetCommand', autospec=False
    )
    def test_update_network(self, mock_set_command, mock_connection):
        ovn_north = NeutronApi()
        rest_data = NetworkApiInputMaker(OvnNorthData.NETWORK_NAME10).get()
        result = ovn_north.update_network(rest_data, OvnNorthData.NETWORK_ID10)

        network = Network(ls=OvnNorthData.NETWORK_10, localnet_lsp=None)
        assert_network_equal(result, network)
        assert mock_set_command.call_count == 1
        assert mock_set_command.mock_calls[0] == extend_call_by_version(
            mock.call(
                ovn_north.idl,
                ovnconst.TABLE_LS,
                OvnNorthData.NETWORK_ID10,
                (
                    ovnconst.ROW_LS_EXTERNAL_IDS,
                    {
                        NetworkMapper.OVN_NETWORK_NAME: (
                            OvnNorthData.NETWORK_NAME10
                        )
                    },
                ),
            ),
            if_exists=True,
        )

    @mock.patch(
        'ovsdbapp.backend.ovs_idl.transaction.Transaction.commit',
        lambda x: None,
    )
    @mock.patch('ovsdbapp.schema.ovn_northbound.commands.LsGetCommand')
    @mock.patch('ovsdbapp.backend.ovs_idl.command.DbSetCommand')
    def test_update_localnet_network(
        self, mock_set_command, mock_ls_get_command, mock_connection
    ):
        mock_ls_get_command.return_value.execute.return_value = (
            OvnNorthData.NETWORK_LOCALNET_12
        )
        ovn_north = NeutronApi()
        rest_data = NetworkApiInputMaker(
            OvnNorthData.NETWORK_NAME12,
            provider_type=NetworkMapper.NETWORK_TYPE_VLAN,
            provider_physical_network=OvnNorthData.LOCALNET_NAME,
            vlan_tag=OvnNorthData.LOCALNET_VLAN,
        ).get()
        result = ovn_north.update_network(rest_data, OvnNorthData.NETWORK_ID12)

        localnet_network = OvnNorthData.NETWORK_LOCALNET_12
        assert_network_equal(
            result,
            Network(
                ls=localnet_network, localnet_lsp=localnet_network.ports[0]
            ),
        )
        assert mock_set_command.call_count == 2
        assert mock_set_command.mock_calls[0] == extend_call_by_version(
            mock.call(
                ovn_north.idl,
                ovnconst.TABLE_LS,
                OvnNorthData.NETWORK_ID12,
                (
                    ovnconst.ROW_LS_EXTERNAL_IDS,
                    {
                        NetworkMapper.OVN_NETWORK_NAME: (
                            OvnNorthData.NETWORK_NAME12
                        )
                    },
                ),
            ),
            if_exists=True,
        )

    @mock.patch(
        'ovsdbapp.backend.ovs_idl.transaction.Transaction.commit',
        lambda x: None,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsGetCommand.execute',
        lambda cmd, check_error: OvnNorthData.NETWORK_10,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsDelCommand', autospec=False
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsListCommand.'
        'execute',
        lambda cmd, check_error: [],
    )
    def test_delete_network(self, mock_del_command, mock_connection):
        ovn_north = NeutronApi()
        ovn_north.delete_network(OvnNorthData.NETWORK_ID10)
        assert mock_del_command.call_count == 1
        expected_del_call = mock.call(
            ovn_north.idl, OvnNorthData.NETWORK_ID10, False
        )
        assert mock_del_command.mock_calls[0] == expected_del_call
