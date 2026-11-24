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
from handlers.base_handler import BadRequestError
from neutron.mappers.base import InvalidRestData
from neutron.mappers.base import MandatoryDataMissing
from neutron.mappers.ports import PortMapper
from neutron.mappers.security_groups import SecurityGroup
from neutron.mappers.security_groups import SecurityGroupRule
from neutron.mappers.security_groups import SecurityGroupMapper
from neutron.neutron_api import NeutronApi
from ovirt_provider_config_common import tenant_id
from ovntestlib import assert_security_group_equal
from ovntestlib import assert_security_group_rule_equal
from ovntestlib import SecurityGroupApiInputMaker
from ovntestlib import SecurityGroupRuleApiInputMaker
from ovntestlib import OvnPortRow
from ovntestlib import OvnSecurityGroupRow
from ovn_north_data import OvnNorthData
from ovn_north_data import extend_call_by_version


@mock.patch('ovsdbapp.backend.ovs_idl.connection', autospec=False)
class TestSecurityGroupsApi(OvnNorthData):
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbListCommand.execute',
        lambda command, check_error: [],
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.impl_idl.OvnNbApiIdlImpl.lookup',
        lambda idl, table, uuid: OvnNorthData.SECURITY_GROUP,
    )
    def test_get_security_group(self, mock_connection):
        ovn_north = NeutronApi(sec_group_support=True)
        result = ovn_north.get_security_group(
            str(OvnNorthData.SECURITY_GROUP_ID)
        )
        assert_security_group_equal(
            result,
            SecurityGroup(
                sec_group=OvnNorthData.SECURITY_GROUP, sec_group_rules=[]
            ),
        )

    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbListCommand.execute',
        lambda idl, check_error: [],
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.impl_idl.OvnNbApiIdlImpl.lookup',
        lambda idl, table, uuid: OvnNorthData.SECURITY_GROUP,
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.transaction.Transaction.commit',
        lambda x: OvnNorthData.SECURITY_GROUP,
        [],
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.PgAclAddCommand.execute',
        lambda cmd, check_error: [],
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.transaction.Transaction.add',
        lambda cmd, check_error: OvnNorthData.SECURITY_GROUP,
    )
    def test_add_security_group(self, mock_connection):
        ovn_north = NeutronApi(sec_group_support=True)
        rest_data = SecurityGroupApiInputMaker(
            OvnNorthData.SECURITY_GROUP_NAME,
            tenant_id(),
            tenant_id(),
            description=OvnNorthData.SECURITY_GROUP_DESCRIPTION,
        ).get()

        result = ovn_north.add_security_group(rest_data)
        security_group = SecurityGroup(
            sec_group=OvnNorthData.SECURITY_GROUP, sec_group_rules=[]
        )
        assert_security_group_equal(result, security_group)

    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbListCommand.execute',
        lambda idl, check_error: [],
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.impl_idl.OvnNbApiIdlImpl.lookup',
        lambda idl, table, uuid: OvnNorthData.SECURITY_GROUP,
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.transaction.Transaction.commit',
        lambda x: OvnNorthData.SECURITY_GROUP,
        [],
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbCreateCommand', autospec=False
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.PgAclAddCommand.execute',
        lambda cmd, check_error: [],
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.PgAddCommand.execute',
        lambda cmd, check_error: OvnNorthData.SECURITY_GROUP,
    )
    def test_add_security_group_optional_data(
        self, db_create_mock, mock_connection
    ):
        ovn_north = NeutronApi(sec_group_support=True)
        rest_data = SecurityGroupApiInputMaker(
            OvnNorthData.SECURITY_GROUP_NAME
        ).get()

        result = ovn_north.add_security_group(rest_data)
        security_group = SecurityGroup(
            sec_group=OvnNorthData.SECURITY_GROUP, sec_group_rules=[]
        )
        assert_security_group_equal(result, security_group)

    def test_add_security_group_validator(self, mock_connection):
        ovn_north = NeutronApi(sec_group_support=True)
        rest_data = SecurityGroupApiInputMaker(
            OvnNorthData.SECURITY_GROUP_NAME,
            tenant_id(),
            tenant_id(),
            description=OvnNorthData.SECURITY_GROUP_DESCRIPTION,
        ).get()

        with pytest.raises(InvalidRestData) as invalid_data:
            rest_data.update({'peanut-butter': 32})
            ovn_north.add_security_group(rest_data)
        assert 'Invalid data found: peanut-butter' == str(invalid_data.value)

    def test_add_security_group_validator_data_missing(self, mock_connection):
        ovn_north = NeutronApi(sec_group_support=True)
        rest_data = SecurityGroupApiInputMaker(
            OvnNorthData.SECURITY_GROUP_NAME,
            tenant_id(),
            tenant_id(),
            description=OvnNorthData.SECURITY_GROUP_DESCRIPTION,
        ).get()

        with pytest.raises(MandatoryDataMissing) as invalid_data:
            rest_data.pop('name')
            ovn_north.add_security_group(rest_data)
        assert 'Mandatory data name is missing' == str(invalid_data.value)

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.impl_idl.OvnNbApiIdlImpl.lookup',
        lambda idl, table, uuid: OvnNorthData.SECURITY_GROUP,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.PgDelCommand', autospec=False
    )
    def test_delete_security_group(self, mock_pg_del_command, mock_connection):
        ovn_north = NeutronApi(sec_group_support=True)

        ovn_north.delete_security_group(str(OvnNorthData.SECURITY_GROUP_ID))
        assert mock_pg_del_command.call_count == 1
        expected_del_call = mock.call(
            ovn_north.idl, str(OvnNorthData.SECURITY_GROUP_ID), if_exists=False
        )
        assert mock_pg_del_command.mock_calls[0] == expected_del_call

    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbListCommand.execute',
        lambda idl, check_error: [],
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.impl_idl.OvnNbApiIdlImpl.lookup',
        lambda idl, table, uuid: OvnNorthData.SECURITY_GROUP,
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.transaction.Transaction.commit',
        lambda x: OvnNorthData.SECURITY_GROUP,
        [],
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbCreateCommand', autospec=False
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbSetCommand', autospec=False
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.PgAclAddCommand.execute',
        lambda cmd, check_error: [],
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbListCommand.execute',
        lambda command, check_error: [],
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.impl_idl.OvnNbApiIdlImpl.lookup',
        lambda self, table, the_id: OvnNorthData.SECURITY_GROUP,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.PgAddCommand.execute',
        lambda cmd, check_error: OvnNorthData.SECURITY_GROUP,
    )
    def test_update_security_group(
        self, mock_db_update, db_create_mock, mock_connection
    ):
        ovn_north = NeutronApi(sec_group_support=True)
        rest_data = SecurityGroupApiInputMaker(
            OvnNorthData.SECURITY_GROUP_NAME,
            tenant_id(),
            tenant_id(),
            description=OvnNorthData.SECURITY_GROUP_DESCRIPTION,
        ).get()

        ovn_north.add_security_group(rest_data)

        # update the security group with other stuff
        new_name = 'new_way_cuter_name'
        new_description = 'this thing is waaaay better now'

        ovn_north.update_security_group(
            SecurityGroupApiInputMaker(
                new_name, description=new_description
            ).get(),
            str(OvnNorthData.SECURITY_GROUP_ID),
        )

        assert mock_db_update.call_count == 1

    @mock.patch(
        'ovsdbapp.backend.ovs_idl.transaction.Transaction.commit',
        lambda x: OvnNorthData.SECURITY_GROUP,
        [],
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.impl_idl.OvnNbApiIdlImpl.lookup',
        lambda self, table, the_id: OvnNorthData.DEFAULT_SECURITY_GROUP,
    )
    def test_update_default_sec_group(self, mock_connection):
        ovn_north = NeutronApi(sec_group_support=True)

        # update the default security group
        new_name = 'new_way_cuter_name'
        new_description = 'this thing is waaaay better now'

        with pytest.raises(BadRequestError):
            ovn_north.update_security_group(
                SecurityGroupApiInputMaker(
                    new_name, description=new_description
                ).get(),
                str(OvnNorthData.SECURITY_GROUP_ID),
            )

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.impl_idl.OvnNbApiIdlImpl.lookup',
        lambda idl, table, uuid: (
            OvnNorthData.SECURITY_GROUP
            if table == 'Port_Group'
            else OvnNorthData.SECURITY_GROUP_RULE_01
        ),
    )
    def test_get_security_group_rule(self, mock_connection):
        ovn_north = NeutronApi(sec_group_support=True)
        result = ovn_north.get_security_group_rule(
            OvnNorthData.SECURITY_GROUP_RULE_ID_01
        )
        assert_security_group_rule_equal(
            result, OvnNorthData.SECURITY_GROUP_RULE_01
        )

    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbListCommand.execute',
        lambda command, check_error: [OvnNorthData.SECURITY_GROUP_RULE_01],
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.impl_idl.OvnNbApiIdlImpl.lookup',
        lambda idl, table, uuid: OvnNorthData.SECURITY_GROUP,
    )
    def test_get_security_group_with_rules(self, mock_connection):
        ovn_north = NeutronApi(sec_group_support=True)
        result = ovn_north.get_security_group(
            str(OvnNorthData.SECURITY_GROUP_ID)
        )
        assert_security_group_equal(
            result,
            SecurityGroup(
                sec_group=OvnNorthData.SECURITY_GROUP,
                sec_group_rules=[
                    SecurityGroupRule(
                        OvnNorthData.SECURITY_GROUP_RULE_01,
                        OvnNorthData.SECURITY_GROUP,
                    )
                ],
            ),
        )

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.impl_idl.OvnNbApiIdlImpl.lookup',
        lambda idl, table, uuid: OvnNorthData.SECURITY_GROUP,
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.PgAclAddCommand.execute',
        lambda cmd, check_error: OvnNorthData.SECURITY_GROUP_RULE_01,
    )
    def test_add_security_group_rules(self, mock_connection):
        ovn_north = NeutronApi(sec_group_support=True)
        rest_data = SecurityGroupRuleApiInputMaker(
            'ingress',
            str(OvnNorthData.SECURITY_GROUP_ID),
            ether_type='IPv4',
            protocol='tcp',
        ).get()

        result = ovn_north.add_security_group_rule(rest_data)
        assert_security_group_rule_equal(
            result, OvnNorthData.SECURITY_GROUP_RULE_01
        )

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.impl_idl.OvnNbApiIdlImpl.lookup'
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.PgAclDelCommand',
        autospec=False,
    )
    def test_delete_security_group_rule(
        self, mock_delete_rule, mock_ovn_getter, mock_connection
    ):
        mock_ovn_getter.side_effect = [
            OvnNorthData.SECURITY_GROUP_RULE_01,
            OvnNorthData.SECURITY_GROUP,
        ]
        ovn_north = NeutronApi(sec_group_support=True)
        ovn_north.delete_security_group_rule(
            OvnNorthData.SECURITY_GROUP_RULE_ID_01
        )
        assert mock_delete_rule.call_count == 1
        expected_del_call = extend_call_by_version(
            mock.call(
                ovn_north.idl,
                str(OvnNorthData.SECURITY_GROUP_ID),
                'from-lport',
                1001,
                'ip4 && tcp',
            ),
            False,
        )
        assert mock_delete_rule.mock_calls[0] == expected_del_call

    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbListCommand.execute',
        lambda command, check_error: [
            OvnNorthData.SECURITY_GROUP_RULE_01,
            OvnNorthData.SECURITY_GROUP_RULE_02,
        ],
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.impl_idl.OvnNbApiIdlImpl.lookup',
        lambda idl, table, uuid: OvnNorthData.SECURITY_GROUP,
    )
    def test_filter_out_drop_security_rules(self, mock_connection):
        ovn_north = NeutronApi(sec_group_support=True)
        result = ovn_north.get_security_group(
            str(OvnNorthData.SECURITY_GROUP_ID)
        )
        assert_security_group_equal(
            result,
            SecurityGroup(
                sec_group=OvnNorthData.SECURITY_GROUP,
                sec_group_rules=[
                    SecurityGroupRule(
                        OvnNorthData.SECURITY_GROUP_RULE_01,
                        OvnNorthData.SECURITY_GROUP,
                    )
                ],
            ),
        )

    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbListCommand.execute',
        lambda idl, check_error: [
            OvnNorthData.SECURITY_GROUP_RULE_01,
            OvnNorthData.SECURITY_GROUP_RULE_03,
        ],
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.impl_idl.OvnNbApiIdlImpl.lookup',
        lambda idl, table, uuid: OvnNorthData.SECURITY_GROUP,
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.transaction.Transaction.commit',
        lambda x: OvnNorthData.SECURITY_GROUP,
        [
            OvnNorthData.SECURITY_GROUP_RULE_01,
            OvnNorthData.SECURITY_GROUP_RULE_03,
        ],
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbCreateCommand', autospec=False
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.PgAclAddCommand.execute'
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.transaction.Transaction.add',
        lambda cmd, check_error: OvnNorthData.SECURITY_GROUP,
    )
    def test_add_security_group_automatic_rule_install(
        self, mock_ovn_getter, db_create_mock, mock_connection
    ):
        ovn_north = NeutronApi(sec_group_support=True)
        mock_ovn_getter.side_effect = [
            OvnNorthData.SECURITY_GROUP_RULE_01,
            OvnNorthData.SECURITY_GROUP_RULE_03,
        ]
        rest_data = SecurityGroupApiInputMaker(
            OvnNorthData.SECURITY_GROUP_NAME,
            tenant_id(),
            tenant_id(),
            description=OvnNorthData.SECURITY_GROUP_DESCRIPTION,
        ).get()

        result = ovn_north.add_security_group(rest_data)
        security_group = SecurityGroup(
            sec_group=OvnNorthData.SECURITY_GROUP,
            sec_group_rules=[
                SecurityGroupRule(
                    OvnNorthData.SECURITY_GROUP_RULE_01,
                    OvnNorthData.SECURITY_GROUP,
                ),
                SecurityGroupRule(
                    OvnNorthData.SECURITY_GROUP_RULE_03,
                    OvnNorthData.SECURITY_GROUP,
                ),
            ],
        )
        assert_security_group_equal(result, security_group)

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.impl_idl.OvnNbApiIdlImpl.lookup'
    )
    def test_cannot_delete_assigned_sec_group(
        self, mock_lookup, mock_connection
    ):
        security_group_id = UUID(int=101)
        port_01_id = UUID(int=4)

        port_01 = OvnPortRow(
            port_01_id,
            external_ids={
                PortMapper.OVN_NIC_NAME: OvnNorthData.PORT_NAME01,
                PortMapper.OVN_DEVICE_ID: str(port_01_id),
                PortMapper.OVN_DEVICE_OWNER: OvnNorthData.DEVICE_OWNER_OVIRT,
                PortMapper.OVN_SECURITY_GROUPS: str(security_group_id),
            },
        )

        security_group_with_ports = OvnSecurityGroupRow(
            security_group_id,
            OvnNorthData.SECURITY_GROUP_NAME,
            external_ids={
                SecurityGroupMapper.OVN_SECURITY_GROUP_DESCRIPTION: '',
                SecurityGroupMapper.OVN_SECURITY_GROUP_CREATE_TS: '',
                SecurityGroupMapper.OVN_SECURITY_GROUP_UPDATE_TS: '',
                SecurityGroupMapper.OVN_SECURITY_GROUP_REV_NUMBER: '1',
                SecurityGroupMapper.OVN_SECURITY_GROUP_TENANT: tenant_id(),
                SecurityGroupMapper.OVN_SECURITY_GROUP_PROJECT: tenant_id(),
            },
            ports=[port_01],
        )

        mock_lookup.return_value = security_group_with_ports
        ovn_north = NeutronApi(sec_group_support=True)
        with pytest.raises(BadRequestError) as ex:
            ovn_north.delete_security_group(str(security_group_id))
        assert 'Security Group {} in use'.format(security_group_id) == str(
            ex.value
        )

    def test_sec_group_rules_ip_prefix_requires_ethertype(
        self, mock_connection
    ):
        ovn_north = NeutronApi(sec_group_support=True)
        ip_prefix = '192.168.14.0/24'
        rest_data = SecurityGroupRuleApiInputMaker(
            'ingress', OvnNorthData.SECURITY_GROUP_ID, ip_prefix=ip_prefix
        ).get()

        with pytest.raises(BadRequestError) as exception:
            ovn_north.add_security_group_rule(rest_data)
        assert 'Conflicting value ethertype {} for CIDR {}'.format(
            None, ip_prefix
        ) == str(exception.value)
