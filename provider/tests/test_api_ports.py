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

from uuid import UUID
import unittest.mock as mock
import pytest
import constants as ovnconst
from handlers.base_handler import BadRequestError
from handlers.base_handler import ConflictError
from neutron.mappers.ports import NetworkPort
from neutron.mappers.ports import PortMapper
from neutron.mappers.subnets import SubnetMapper
from neutron.neutron_api import NeutronApi
from ovntestlib import assert_port_equal
from ovntestlib import PortApiInputMaker
from ovntestlib import OvnNetworkRow
from ovntestlib import OvnPortRow
from ovntestlib import OvnSubnetRow
from ovn_north_data import OvnNorthData
from ovn_north_data import extend_call_by_version


@mock.patch('ovsdbapp.backend.ovs_idl.connection', autospec=False)
class TestPortsApi(OvnNorthData):
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.transaction.Transaction.commit',
        lambda x: None,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsListCommand.execute',
        lambda cmd, check_error: OvnNorthData.networks,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LspGetCommand.execute',
        lambda cmd, check_error: OvnNorthData.PORT_1,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsListCommand.'
        'execute',
        lambda cmd, check_error: [OvnNorthData.SUBNET_101],
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsGetCommand.execute',
        lambda cmd, check_error: OvnNorthData.NETWORK_10,
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbClearCommand.execute',
        lambda cmd, check_error: [],
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LspAddCommand', autospec=False
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbSetCommand', autospec=False
    )
    @mock.patch('neutron.api.ports.ovs_version_29', lambda: True)
    def test_add_port(self, mock_db_set, mock_add_command, mock_connection):
        mock_add_command.return_value.execute.return_value = (
            OvnNorthData.PORT_1
        )
        ovn_north = NeutronApi()
        rest_data = PortApiInputMaker(
            OvnNorthData.PORT_NAME01,
            str(OvnNorthData.NETWORK_ID10),
            device_id=OvnNorthData.DEVICE_ID,
            device_owner=OvnNorthData.DEVICE_OWNER_OVIRT,
            admin_state_up=True,
            mac_address=OvnNorthData.MAC_ADDRESS,
            fixed_ips=OvnNorthData.PORT_NAME01_FIXED_IPS,
            binding_host_id=OvnNorthData.PORT_BINDING_ID,
        ).get()
        result = ovn_north.add_port(rest_data)

        # ID11 because this network has the port in OvnNorthData.networks
        logical_switch = OvnNetworkRow(
            OvnNorthData.NETWORK_ID11,
            name=OvnNorthData.NETWORK_NAME11,
            ports=[OvnNorthData.PORT_1],
        )
        port = NetworkPort(
            lsp=OvnNorthData.PORT_1,
            ls=logical_switch,
            dhcp_options=None,
            lrp=None,
        )
        assert_port_equal(result, port)

        assert mock_add_command.call_count == 1
        mock_add_command.assert_called_with(
            ovn_north.idl,
            str(OvnNorthData.NETWORK_ID10),
            mock.ANY,
            None,
            None,
            False,
            external_ids={
                'ovirt_nic_name': OvnNorthData.PORT_NAME01,
            },
        )

        assert mock_db_set.call_count == 4

        assert (
            extend_call_by_version(
                mock.call(
                    ovn_north.idl,
                    ovnconst.TABLE_LSP,
                    mock.ANY,
                    (
                        ovnconst.ROW_LSP_EXTERNAL_IDS,
                        {PortMapper.OVN_DEVICE_ID: OvnNorthData.DEVICE_ID},
                    ),
                    (
                        ovnconst.ROW_LSP_EXTERNAL_IDS,
                        {PortMapper.OVN_NIC_NAME: OvnNorthData.PORT_NAME01},
                    ),
                    (
                        ovnconst.ROW_LSP_EXTERNAL_IDS,
                        {
                            PortMapper.OVN_DEVICE_OWNER: OvnNorthData.DEVICE_OWNER_OVIRT  # noqa: E501
                        },
                    ),
                    (ovnconst.ROW_LSP_ENABLED, True),
                    (
                        ovnconst.ROW_LSP_OPTIONS,
                        {
                            PortMapper.OVN_REQUESTED_CHASSIS: OvnNorthData.PORT_BINDING_ID  # noqa: E501
                        },
                    ),
                ),
                if_exists=True,
            )
            in mock_db_set.mock_calls
        )

        assert (
            extend_call_by_version(
                mock.call(
                    ovn_north.idl,
                    ovnconst.TABLE_LSP,
                    mock.ANY,
                    (
                        ovnconst.ROW_LSP_DHCPV4_OPTIONS,
                        OvnNorthData.SUBNET_ID101,
                    ),
                    (
                        ovnconst.ROW_LSP_ADDRESSES,
                        [
                            '{mac_address} {ip_address}'.format(
                                mac_address=OvnNorthData.MAC_ADDRESS,
                                ip_address=OvnNorthData.PORT_NAME01_FIXED_IP,
                            )
                        ],
                    ),
                ),
                if_exists=True,
            )
            in mock_db_set.mock_calls
        )

    @mock.patch(
        'ovsdbapp.backend.ovs_idl.transaction.Transaction.commit',
        lambda x: None,
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbClearCommand.execute',
        lambda cmd, check_error: [],
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsListCommand', autospec=False
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LspGetCommand', autospec=False
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsGetCommand', autospec=False
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsListCommand',
        autospec=False,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LspAddCommand', autospec=False
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbSetCommand', autospec=False
    )
    @mock.patch('neutron.api.ports.ovs_version_29', lambda: True)
    def test_add_port_subnet(
        self,
        mock_db_set,
        mock_add_command,
        mock_get_dhcp_options,
        mock_ls_get,
        mock_lsp_get,
        mock_ls_list,
        mock_connection,
    ):
        networkd_uuid = UUID(int=505)
        subnet_cidr = '192.168.14.0/24'
        subnet_uuid = UUID(int=606)
        port_name = 'mega-port'
        port_uuid = UUID(int=707)

        subnet = OvnSubnetRow(
            subnet_uuid, network_id=str(networkd_uuid), cidr=subnet_cidr
        )
        port_fixed_ips = [{PortMapper.REST_PORT_SUBNET_ID: str(subnet_uuid)}]
        ovn_port = OvnPortRow(
            port_uuid,
            addresses=[OvnNorthData.MAC_ADDRESS, '192.168.14.2'],
            external_ids={
                PortMapper.OVN_NIC_NAME: port_name,
                PortMapper.OVN_DEVICE_ID: str(port_uuid),
                PortMapper.OVN_DEVICE_OWNER: OvnNorthData.DEVICE_OWNER_OVIRT,
            },
        )
        port_network = OvnNetworkRow(networkd_uuid, 'net4', ports=[ovn_port])
        mock_add_command.return_value.execute.return_value = ovn_port
        mock_get_dhcp_options.return_value.execute.return_value = [subnet]
        mock_ls_get.return_value.execute.return_value = port_network
        mock_lsp_get.return_value.execute.return_value = ovn_port
        mock_ls_list.return_value.execute.return_value = [port_network]

        ovn_north = NeutronApi()
        rest_data = PortApiInputMaker(
            port_name,
            str(networkd_uuid),
            device_id=OvnNorthData.DEVICE_ID,
            device_owner=OvnNorthData.DEVICE_OWNER_OVIRT,
            admin_state_up=True,
            mac_address=OvnNorthData.MAC_ADDRESS,
            fixed_ips=port_fixed_ips,
            binding_host_id=OvnNorthData.PORT_BINDING_ID,
        ).get()
        result = ovn_north.add_port(rest_data)

        port = NetworkPort(
            lsp=ovn_port, ls=port_network, dhcp_options=subnet, lrp=None
        )
        assert_port_equal(result, port)

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsListCommand.'
        'execute',
        lambda cmd, check_error: [],
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsListCommand.execute',
        lambda cmd, check_error: OvnNorthData.networks,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LspListCommand.execute',
        lambda cmd, check_error: OvnNorthData.ports,
    )
    def test_list_ports(self, mock_connection):
        ovn_north = NeutronApi()
        ports = ovn_north.list_ports()
        assert len(ports) == 3
        logical_switch = OvnNetworkRow(
            OvnNorthData.NETWORK_ID11,
            name=OvnNorthData.NETWORK_NAME11,
            ports=[OvnNorthData.PORT_1, OvnNorthData.PORT_2],
        )
        first_port = NetworkPort(
            lsp=OvnNorthData.PORT_1,
            ls=logical_switch,
            dhcp_options=None,
            lrp=None,
        )
        second_port = NetworkPort(
            lsp=OvnNorthData.PORT_2,
            ls=logical_switch,
            dhcp_options=None,
            lrp=None,
        )

        third_port = NetworkPort(
            lsp=OvnNorthData.PORT_3,
            ls=OvnNetworkRow(OvnNorthData.NETWORK_ID12),
            dhcp_options=None,
            lrp=None,
        )

        assert_port_equal(ports[0], first_port)
        assert_port_equal(ports[1], second_port)
        assert_port_equal(ports[2], third_port)

    @mock.patch(
        'ovsdbapp.backend.ovs_idl.transaction.Transaction.commit',
        lambda x: None,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LspGetCommand.' 'execute',
        lambda cmd, check_error: OvnPortRow(
            OvnNorthData.PORT_ID01,
            external_ids={
                PortMapper.OVN_DEVICE_OWNER: OvnNorthData.DEVICE_OWNER_OVIRT
            },
        ),
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LspDelCommand', autospec=False
    )
    def test_delete_port(self, mock_del_command, mock_connection):
        ovn_north = NeutronApi()
        ovn_north.delete_port(OvnNorthData.PORT_ID01)
        assert mock_del_command.call_count == 1
        expected_del_call = mock.call(
            ovn_north.idl, OvnNorthData.PORT_ID01, None, False
        )
        assert mock_del_command.mock_calls[0] == expected_del_call

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LspGetCommand.' 'execute',
        lambda cmd, check_error: OvnPortRow(
            OvnNorthData.PORT_ID01,
            external_ids={
                PortMapper.OVN_DEVICE_OWNER: PortMapper.DEVICE_OWNER_ROUTER
            },
        ),
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LspDelCommand', autospec=False
    )
    def test_delete_router_port(self, mock_del_command, mock_connection):
        ovn_north = NeutronApi()
        with pytest.raises(ConflictError):
            ovn_north.delete_port(OvnNorthData.PORT_ID01)
        assert mock_del_command.call_count == 0

    def test_port_admin_state_up_none_enabled_none(self, mock_connection):
        self._port_admin_state(mock_connection, None, None, False)

    def test_port_admin_state_up_true_enabled_none(self, mock_connection):
        self._port_admin_state(mock_connection, [True], None, True)

    def test_port_admin_state_up_false_enabled_none(self, mock_connection):
        self._port_admin_state(mock_connection, [False], None, False)

    def test_port_admin_state_up_none_enabled_true(self, mock_connection):
        self._port_admin_state(mock_connection, None, [True], False)

    def test_port_admin_state_up_true_enabled_true(self, mock_connection):
        self._port_admin_state(mock_connection, [True], [True], True)

    def test_port_admin_state_up_false_enabled_true(self, mock_connection):
        self._port_admin_state(mock_connection, [False], [True], False)

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsListCommand.'
        'execute',
        lambda cmd, check_error: [],
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsListCommand',
    )
    @mock.patch('ovsdbapp.schema.ovn_northbound.commands.LspGetCommand')
    def _port_admin_state(
        self,
        mock_connection,
        is_up,
        is_enabled,
        result,
        mock_lsp_get,
        mock_ls_list,
    ):
        port_row = OvnPortRow(
            OvnNorthData.PORT_ID01,
            external_ids={
                PortMapper.OVN_NIC_NAME: OvnNorthData.PORT_NAME01,
                PortMapper.OVN_DEVICE_ID: str(OvnNorthData.PORT_ID01),
                PortMapper.OVN_DEVICE_OWNER: OvnNorthData.DEVICE_OWNER_OVIRT,
            },
        )
        port_row.up = is_up
        port_row.enabled = is_enabled

        mock_lsp_get.return_value.execute.return_value = port_row
        mock_ls_list.return_value.execute.return_value = [
            OvnNetworkRow(OvnNorthData.NETWORK_ID11, ports=[port_row])
        ]

        ovn_north = NeutronApi()
        port = ovn_north.get_port(OvnNorthData.PORT_ID01)
        assert port[PortMapper.REST_PORT_ADMIN_STATE_UP] == result

    @mock.patch(
        'ovsdbapp.backend.ovs_idl.transaction.Transaction.commit',
        lambda tx: None,
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbSetCommand', autospec=False
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LspAddCommand', autospec=False
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbListCommand.execute',
        lambda cmd, check_error: [],
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LspListCommand.' 'execute',
        lambda cmd, check_error: [],
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsListCommand.'
        'execute',
        lambda cmd, check_error: [
            OvnSubnetRow(
                OvnNorthData.SUBNET_IDV6,
                cidr=OvnNorthData.SUBNET_IPV6_CIDR,
                ip_version=6,
                network_id=str(OvnNorthData.NETWORK_IDMTU),
                external_ids={
                    SubnetMapper.OVN_IPV6_ADDRESS_MODE: SubnetMapper.IPV6_ADDRESS_MODE_STATELESS  # noqa: E501
                },
            )
        ],
    )
    def test_create_port_fixed_ip_on_stateless_subnet(
        self, mock_add_port, mock_update_port, mock_connection
    ):
        ovn_north = NeutronApi()
        port_rest_data = PortApiInputMaker(
            OvnNorthData.PORT_NAME01,
            str(OvnNorthData.NETWORK_IDMTU),
            fixed_ips=[
                {
                    PortMapper.REST_PORT_IP_ADDRESS: 'bef0:1234:a890:5678::3',
                    PortMapper.REST_PORT_SUBNET_ID: str(
                        OvnNorthData.SUBNET_IDV6
                    ),
                }
            ],
        ).get()

        with pytest.raises(BadRequestError) as bre:
            ovn_north.add_port(port_rest_data)
        assert str(bre.value) == (
            'IPv6 address bef0:1234:a890:5678::3 cannot be directly assigned '
            'to a port on subnet 00000000-0000-0000-0000-000000000006 as the '
            'subnet is configured for automatic addresses'
        )
