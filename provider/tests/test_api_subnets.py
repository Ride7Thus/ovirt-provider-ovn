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
import pytest
from ovsdbapp.backend.ovs_idl.idlutils import RowNotFound
import constants as ovnconst
from handlers.base_handler import BadRequestError
from neutron.mappers.networks import NetworkMapper
from neutron.mappers.subnets import SubnetConfigError
from neutron.mappers.subnets import SubnetMapper
from neutron.mappers.base import UnsupportedDataValueError
from neutron.neutron_api import NeutronApi
from ovirt_provider_config_common import dhcp_lease_time
from ovirt_provider_config_common import dhcp_mtu
from ovirt_provider_config_common import dhcp_server_mac
from ovirt_provider_config_common import tenant_id
from ovntestlib import assert_subnet_equal
from ovntestlib import SubnetApiInputMaker
from ovntestlib import OvnNetworkRow
from ovn_north_data import OvnNorthData
from ovn_north_data import extend_call_by_version


@mock.patch('ovsdbapp.backend.ovs_idl.connection', autospec=False)
class TestSubnetsApi(OvnNorthData):
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsListCommand.'
        'execute',
        lambda cmd, check_error: OvnNorthData.subnets,
    )
    def test_list_subnets(self, mock_connection):
        ovn_north = NeutronApi()
        result = ovn_north.list_subnets()
        assert len(result) == 2
        assert result[0]['id'] == str(OvnNorthData.SUBNET_ID101)
        assert result[0]['network_id'] == str(OvnNorthData.NETWORK_ID10)
        assert result[0]['tenant_id'] == tenant_id()

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsGetCommand.'
        'execute',
        lambda cmd, check_error: OvnNorthData.SUBNET_101,
    )
    def test_get_subnet(self, mock_connection):
        ovn_north = NeutronApi()
        result = ovn_north.get_subnet(OvnNorthData.SUBNET_ID101)
        assert result['id'] == str(OvnNorthData.SUBNET_ID101)
        assert result['network_id'] == str(OvnNorthData.NETWORK_ID10)
        gateway_ip = OvnNorthData.SUBNET_101.options['router']
        assert result['gateway_ip'] == gateway_ip

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsDelCommand',
        autospec=False,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsGetCommand.'
        'execute',
        lambda cmd, check_error: OvnNorthData.SUBNET_101,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsGetCommand.execute',
        lambda cmd, check_error: OvnNorthData.NETWORK_10,
    )
    def test_delete_subnet(self, mock_del_command, mock_connection):
        ovn_north = NeutronApi()
        ovn_north.delete_subnet(OvnNorthData.SUBNET_ID101)
        assert mock_del_command.call_count == 1
        expected_del_call = mock.call(
            ovn_north.idl,
            OvnNorthData.SUBNET_ID101,
        )
        assert mock_del_command.mock_calls[0] == expected_del_call

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsListCommand.'
        'execute',
        lambda cmd, check_error: [],
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsGetCommand.execute',
        lambda cmd, check_error: OvnNorthData.NETWORK_10,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsGetCommand.'
        'execute',
        lambda cmd, check_error: OvnNorthData.SUBNET_102,
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbSetCommand', autospec=False
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsAddCommand',
        autospec=False,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsSetOptionsCommand',
        autospec=False,
    )
    def test_add_subnet(
        self,
        mock_setoptions_command,
        mock_add_command,
        mock_dbset_command,
        mock_connection,
    ):
        add_execute = mock_add_command.return_value.execute
        add_execute.return_value = OvnNorthData.SUBNET_102
        ovn_north = NeutronApi()
        rest_data = SubnetApiInputMaker(
            OvnNorthData.SUBNET_102.external_ids.get(SubnetMapper.OVN_NAME),
            cidr=OvnNorthData.SUBNET_CIDR,
            ip_version=4,
            network_id=str(OvnNorthData.NETWORK_ID10),
            dns_nameservers=['1.1.1.1'],
            gateway_ip='1.1.1.0',
        ).get()
        result = ovn_north.add_subnet(rest_data)
        assert_subnet_equal(result, OvnNorthData.SUBNET_102)
        assert mock_dbset_command.call_count == 1
        assert mock_add_command.call_count == 1
        assert mock_setoptions_command.call_count == 1

        expected_dbset_call = extend_call_by_version(
            mock.call(
                ovn_north.idl,
                ovnconst.TABLE_LS,
                str(OvnNorthData.NETWORK_ID10),
                (
                    ovnconst.ROW_LS_OTHER_CONFIG,
                    {NetworkMapper.OVN_SUBNET: OvnNorthData.SUBNET_CIDR},
                ),
            ),
            if_exists=True,
        )
        assert mock_dbset_command.mock_calls[0] == expected_dbset_call

        expected_add_call = mock.call(
            ovn_north.idl,
            OvnNorthData.SUBNET_CIDR,
            ovirt_name=OvnNorthData.SUBNET_102.external_ids.get(
                SubnetMapper.OVN_NAME
            ),
            ovirt_network_id=str(OvnNorthData.NETWORK_ID10),
            ip_version='4',
        )
        assert mock_add_command.mock_calls[0] == expected_add_call

        expected_options_call = mock.call(
            ovn_north.idl,
            OvnNorthData.SUBNET_ID102,
            dns_server='1.1.1.1',
            lease_time=dhcp_lease_time(),
            router='1.1.1.0',
            server_id='1.1.1.0',
            server_mac=dhcp_server_mac(),
            mtu=dhcp_mtu(),
        )
        assert mock_setoptions_command.mock_calls[0] == expected_options_call

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsListCommand.'
        'execute',
        lambda cmd, check_error: [],
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsGetCommand.execute',
        lambda cmd, check_error: OvnNorthData.NETWORK_10,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsGetCommand.'
        'execute',
        lambda cmd, check_error: OvnNorthData.SUBNET_102,
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbSetCommand', autospec=False
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsAddCommand',
        autospec=False,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsSetOptionsCommand',
        autospec=False,
    )
    def test_add_subnet_no_dns(
        self,
        mock_setoptions_command,
        mock_add_command,
        mock_dbset_command,
        mock_connection,
    ):
        add_execute = mock_add_command.return_value.execute
        add_execute.return_value = OvnNorthData.SUBNET_102
        ovn_north = NeutronApi()
        rest_data = SubnetApiInputMaker(
            'subnet_name',
            cidr=OvnNorthData.SUBNET_CIDR,
            network_id=str(OvnNorthData.NETWORK_ID10),
            dns_nameservers=[],
            gateway_ip='1.1.1.0',
            ip_version=4,
        ).get()
        result = ovn_north.add_subnet(rest_data)
        assert_subnet_equal(result, OvnNorthData.SUBNET_102)
        assert mock_dbset_command.call_count == 1
        assert mock_add_command.call_count == 1
        assert mock_setoptions_command.call_count == 1

    """
    TODO: This test causes Jenkins to get stuck. Commenting out until the
    issue is solved.

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsListCommand.execute',
        lambda cmd, check_error: OvnNorthData.networks
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LspGetCommand.execute',
        lambda cmd, check_error: OvnNorthData.PORT_1
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsListCommand.'
        'execute',
        lambda cmd, check_error: []
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbSetCommand',
        autospec=False
    )
    def test_update_subnet(self, mock_db_set, mock_connection):

        ovn_north = OvnNorth()
        rest_data = {
           SubnetMapper.REST_SUBNET_NAME: 'subnet_name',
           SubnetMapper.REST_SUBNET_ENABLE_DHCP: True,
           SubnetMapper.REST_SUBNET_NETWORK_ID: OvnNorthData.NETWORK_ID10,
           SubnetMapper.REST_SUBNET_DNS_NAMESERVERS: ['8.8.8.8'],
           SubnetMapper.REST_SUBNET_GATEWAY_IP: '172.16.0.254',
           SubnetMapper.REST_SUBNET_IP_VERSION: 4,
           SubnetMapper.REST_SUBNET_CIDR: '172.16.0.0/24'
        }
        ovn_north.update_subnet(rest_data, OvnNorthData.SUBNET_ID101)

        assert mock_db_set.call_count == 2

        assert mock_db_set.mock_calls[0] == mock.call(
            ovn_north.idl,
            OvnNorth.TABLE_LS,
            OvnNorthData.NETWORK_ID10,
            (
                OvnNorth.ROW_LS_OTHER_CONFIG,
                {NetworkMapper.OVN_SUBNET:
                    rest_data[SubnetMapper.REST_SUBNET_CIDR]}
            )
        )

        assert mock_db_set.mock_calls[2] == mock.call(
            ovn_north.idl,
            OvnNorth.TABLE_DHCP_Options,
            OvnNorthData.SUBNET_ID101,
            (
                OvnNorth.ROW_DHCP_OPTIONS,
                {SubnetMapper.OVN_DHCP_SERVER_ID:
                    rest_data[SubnetMapper.REST_SUBNET_CIDR].split('/', 1)[0]}
            ),
            (
                OvnNorth.ROW_DHCP_CIDR,
                rest_data[SubnetMapper.REST_SUBNET_CIDR]
            ),
            (
                OvnNorth.ROW_DHCP_EXTERNAL_IDS,
                {SubnetMapper.OVN_NAME:
                    rest_data[SubnetMapper.REST_SUBNET_NAME]}
            ),
            (
                OvnNorth.ROW_DHCP_EXTERNAL_IDS,
                {SubnetMapper.OVN_NETWORK_ID:
                    rest_data[SubnetMapper.REST_SUBNET_NETWORK_ID]}
            ),
            (
                OvnNorth.ROW_DHCP_OPTIONS,
                {SubnetMapper.OVN_GATEWAY:
                    rest_data[SubnetMapper.REST_SUBNET_GATEWAY_IP]}
            ),
            (
                OvnNorth.ROW_DHCP_OPTIONS,
                {SubnetMapper.OVN_DNS_SERVER:
                    rest_data[SubnetMapper.REST_SUBNET_DNS_NAMESERVERS][0]}
            ),
            (
                OvnNorth.ROW_DHCP_OPTIONS,
                {SubnetMapper.OVN_DHCP_LEASE_TIME: dhcp_lease_time()}
            ),
            (
                OvnNorth.ROW_DHCP_OPTIONS,
                {SubnetMapper.OVN_DHCP_SERVER_MAC: dhcp_server_mac()}
            )
        )
    """

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsGetCommand.execute',
        lambda cmd, check_error: OvnNetworkRow(
            OvnNorthData.NETWORK_ID10, OvnNorthData.NETWORK_NAME10
        ),
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsListCommand.'
        'execute',
        lambda cmd, check_error: OvnNorthData.subnets,
    )
    def test_subnet_add_duplicate_network(self, mock_connection):
        ovn_north = NeutronApi()
        rest_data = SubnetApiInputMaker(
            'subnet_name',
            cidr=OvnNorthData.SUBNET_CIDR,
            ip_version=4,
            network_id=str(OvnNorthData.NETWORK_ID10),
            gateway_ip='1.1.1.0',
        ).get()
        with pytest.raises(SubnetConfigError):
            ovn_north.add_subnet(rest_data)

    def test_subnet_dhcp_enabled_false(self, mock_connection):
        ovn_north = NeutronApi()
        rest_data = SubnetApiInputMaker(
            'subnet_name',
            cidr=OvnNorthData.SUBNET_CIDR,
            network_id='',
            dns_nameservers=['1.1.1.1'],
            gateway_ip='1.1.1.0',
            enable_dhcp=False,
            ip_version=4,
        ).get()
        with pytest.raises(UnsupportedDataValueError):
            ovn_north.add_subnet(rest_data)

    @mock.patch('ovsdbapp.schema.ovn_northbound.commands.LsGetCommand.execute')
    def test_subnet_add_invalid_network(
        self, mock_ls_get_cmd, mock_connection
    ):
        mock_ls_get_cmd.side_effect = RowNotFound()
        ovn_north = NeutronApi()
        rest_data = SubnetApiInputMaker(
            'subnet_name',
            cidr=OvnNorthData.SUBNET_CIDR,
            network_id=7,
            dns_nameservers=['1.1.1.1'],
            gateway_ip='1.1.1.0',
            ip_version=4,
        ).get()
        with pytest.raises(SubnetConfigError):
            ovn_north.add_subnet(rest_data)

    def test_invalid_v6_cidr(self, mock_connection):
        ovn_north = NeutronApi()
        rest_data = SubnetApiInputMaker(
            OvnNorthData.SUBNET_102.external_ids.get(SubnetMapper.OVN_NAME),
            cidr=OvnNorthData.SUBNET_CIDR,
            network_id=str(OvnNorthData.NETWORK_ID10),
            dns_nameservers=['1.1.1.1'],
            gateway_ip='1.1.1.0',
            ip_version=6,
        ).get()
        with pytest.raises(BadRequestError) as exception:
            ovn_north.add_subnet(rest_data)
        assert str(exception.value) == (
            'The provided ip_version [6] does not match the supplied '
            'cidr=1.1.1.0/24 or gateway=1.1.1.0'
        )

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsGetCommand.'
        'execute',
        lambda cmd, check_error: OvnNorthData.SUBNET_IPV6,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsAddCommand.'
        'execute',
        lambda cmd, check_error: OvnNorthData.SUBNET_IPV6,
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
    def test_ipv6_support(
        self, mock_setoptions_command, mock_dbset_command, mock_connection
    ):
        for mode in [
            None,
            'dhcpv6-stateful',
            'dhcpv6-stateless',
            'dhcpv6_stateful',
            'dhcpv6_stateless',
        ]:
            ovn_north = NeutronApi()
            rest_data = SubnetApiInputMaker(
                OvnNorthData.SUBNET_IPV6.external_ids.get(
                    SubnetMapper.OVN_NAME
                ),
                cidr=OvnNorthData.SUBNET_IPV6_CIDR,
                network_id=str(OvnNorthData.NETWORK_IDMTU),
                gateway_ip=OvnNorthData.SUBNET_IPV6_GATEWAY,
                ip_version=6,
                address_mode=mode,
            ).get()

            created_subnet = ovn_north.add_subnet(rest_data)
            assert_subnet_equal(created_subnet, OvnNorthData.SUBNET_IPV6)

    def test_ipv6_allowed_ra_modes(self, mock_connection):
        ovn_north = NeutronApi()
        slaac_rest_data = SubnetApiInputMaker(
            OvnNorthData.SUBNET_IPV6.external_ids.get(SubnetMapper.OVN_NAME),
            cidr=OvnNorthData.SUBNET_IPV6_CIDR,
            network_id=str(OvnNorthData.NETWORK_IDMTU),
            gateway_ip=OvnNorthData.SUBNET_IPV6_GATEWAY,
            ip_version=6,
            address_mode='slaac',
        ).get()

        with pytest.raises(UnsupportedDataValueError) as error:
            ovn_north.add_subnet(slaac_rest_data)
        assert str(error.value) == (
            'Setting ipv6_address_mode value to slaac is not supported. '
            'Allowed values are: [\'dhcpv6-stateful\', \'dhcpv6-stateless\','
            ' \'dhcpv6_stateful\', \'dhcpv6_stateless\']'
        )

    def test_v4_subnet_having_v6_attributes(self, mock_connection):
        ovn_north = NeutronApi()
        rest_data = SubnetApiInputMaker(
            OvnNorthData.SUBNET_102.external_ids.get(SubnetMapper.OVN_NAME),
            cidr=OvnNorthData.SUBNET_CIDR,
            network_id=str(OvnNorthData.NETWORK_ID10),
            dns_nameservers=['1.1.1.1'],
            gateway_ip='1.1.1.0',
            ip_version=4,
            address_mode='dhcpv6-stateful',
        ).get()

        with pytest.raises(BadRequestError) as bre:
            ovn_north.add_subnet(rest_data)
        assert str(bre.value) == (
            'The \'ipv6_address_mode\' parameter can only be used '
            'when \'ip_version\' == 6'
        )

    def test_ipv6_subnet_stateless_mode_invalid_prefix(self, mock_connection):
        ovn_north = NeutronApi()
        stateless_dhcpv6_rest_data = SubnetApiInputMaker(
            OvnNorthData.SUBNET_102.external_ids.get(SubnetMapper.OVN_NAME),
            cidr='bef0:1234:a890:5678::/96',
            network_id=str(OvnNorthData.NETWORK_IDMTU),
            gateway_ip=OvnNorthData.SUBNET_IPV6_GATEWAY,
            ip_version=6,
            address_mode='dhcpv6-stateless',
        ).get()

        with pytest.raises(BadRequestError) as bre:
            ovn_north.add_subnet(stateless_dhcpv6_rest_data)
        assert str(bre.value) == (
            'Invalid CIDR bef0:1234:a890:5678::/96 for IPv6 address mode. '
            'OVN uses the EUI-64 address format, which requires the prefix '
            'to be /64'
        )
