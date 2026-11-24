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
import constants as ovnconst
import neutron.constants as neutron_constants
from neutron.mappers.networks import NetworkMapper
from neutron.mappers.ports import PortMapper
from neutron.mappers.security_groups import SecurityGroupMapper
from neutron.mappers.security_groups import SecurityGroupRuleMapper
from ovirt_provider_config_common import tenant_id
from ovntestlib import OvnNetworkRow
from ovntestlib import OvnPortRow
from ovntestlib import OvnRouterRow
from ovntestlib import OvnSecurityGroupRow
from ovntestlib import OvnSecurityGroupRuleRow
from ovntestlib import OvnSubnetRow
from ovsdbapp import __version__ as ovsdbapp_version


ovsdbapp_major = int(ovsdbapp_version.split('.')[0])


def extend_call_by_version(original_call, *args, **kwargs):
    if ovsdbapp_major < 2:
        return original_call

    return mock.call(*original_call.args, *args, **kwargs)


class OvnNorthData(object):
    """OVN rows and ids shared by the NeutronApi tests."""

    MAC_ADDRESS = '01:00:00:00:00:11'
    DEVICE_ID = 'device-id-123456'
    NIC_NAME = 'port_name'
    NETWORK_NAME = 'test_net'
    LOCALNET_NAME = 'localnet'
    LOCALNET_VLAN = 10
    DEVICE_OWNER_OVIRT = 'oVirt'
    SUBNET_CIDR = '1.1.1.0/24'
    SUBNET_IPV6_CIDR = 'bef0:1234:a890:5678::/64'
    SUBNET_IPV6_GATEWAY = 'bef0:1234:a890:5678::1'
    VALUE_NETWORK_MTU = 32854

    NETWORK_ID10 = UUID(int=10)
    NETWORK_ID11 = UUID(int=11)
    NETWORK_ID12 = UUID(int=12)
    NETWORK_IDMTU = UUID(int=123)
    NETWORK_ID_UNICODE = UUID(int=456)
    NETWORK_NAME10 = 'name10'
    NETWORK_NAME11 = 'name11'
    NETWORK_NAME12 = 'name12'
    NETWORK_NAMEMTU = 'nameMTU'
    NETWORK_NAME_UNICODE = u'רשתחיצונית'

    PORT_BINDING_ID = 'bee7-15900d-bee7-1590d'

    PORT_ID01 = UUID(int=1)
    PORT_ID02 = UUID(int=2)
    PORT_ID03 = UUID(int=3)
    PORT_NAME01 = 'port1'
    PORT_NAME02 = 'port2'
    PORT_NAME03 = 'port3'

    PORT_NAME01_FIXED_IP = "1.1.1.1"
    PORT_NAME01_FIXED_IPS = [
        {PortMapper.REST_PORT_IP_ADDRESS: PORT_NAME01_FIXED_IP}
    ]

    PORT_1 = OvnPortRow(
        PORT_ID01,
        addresses=MAC_ADDRESS,
        external_ids={
            PortMapper.OVN_NIC_NAME: PORT_NAME01,
            PortMapper.OVN_DEVICE_ID: str(PORT_ID01),
            PortMapper.OVN_DEVICE_OWNER: DEVICE_OWNER_OVIRT,
        },
    )
    PORT_2 = OvnPortRow(
        PORT_ID02,
        addresses=MAC_ADDRESS,
        external_ids={
            PortMapper.OVN_NIC_NAME: PORT_NAME02,
            PortMapper.OVN_DEVICE_ID: str(PORT_ID02),
            PortMapper.OVN_DEVICE_OWNER: DEVICE_OWNER_OVIRT,
        },
    )

    PORT_3 = OvnPortRow(
        PORT_ID03,
        addresses=MAC_ADDRESS,
        external_ids={
            PortMapper.OVN_NIC_NAME: PORT_NAME03,
            PortMapper.OVN_DEVICE_ID: str(PORT_ID03),
            PortMapper.OVN_DEVICE_OWNER: DEVICE_OWNER_OVIRT,
        },
        port_type=ovnconst.LSP_TYPE_LOCALNET,
        options={ovnconst.LSP_OPTION_NETWORK_NAME: LOCALNET_NAME},
        tag=LOCALNET_VLAN,
    )

    SUBNET_ID101 = UUID(int=101)
    SUBNET_ID102 = UUID(int=102)
    SUBNET_IDMTU = UUID(int=987)
    SUBNET_IDV6 = UUID(int=6)

    SUBNET_101 = OvnSubnetRow(
        SUBNET_ID101, network_id=str(NETWORK_ID10), cidr=SUBNET_CIDR
    )

    SUBNET_102 = OvnSubnetRow(SUBNET_ID102, cidr=SUBNET_CIDR)

    SUBNET_MTU = OvnSubnetRow(
        SUBNET_IDMTU, network_id=str(NETWORK_IDMTU), cidr=SUBNET_CIDR
    )

    SUBNET_IPV6 = OvnSubnetRow(
        SUBNET_IDV6, cidr=SUBNET_IPV6_CIDR, ip_version=6
    )

    NETWORK_10 = OvnNetworkRow(NETWORK_ID10, NETWORK_NAME10)
    NETWORK_11 = OvnNetworkRow(
        NETWORK_ID11, NETWORK_NAME11, ports=[PORT_1, PORT_2]
    )
    NETWORK_12 = OvnNetworkRow(NETWORK_ID12, NETWORK_NAME12)
    NETWORK_LOCALNET_12 = OvnNetworkRow(
        NETWORK_ID12, NETWORK_NAME12, ports=[PORT_3]
    )
    NETWORK_MTU = OvnNetworkRow(
        NETWORK_IDMTU,
        NETWORK_NAMEMTU,
        external_ids={NetworkMapper.REST_MTU: str(VALUE_NETWORK_MTU)},
    )

    NETWORK_UNICODE = OvnNetworkRow(NETWORK_ID_UNICODE, NETWORK_NAME_UNICODE)

    ROUTER_ID20 = UUID(int=20)
    ROUTER_NAME20 = 'router20'

    ROUTER_20 = OvnRouterRow(ROUTER_ID20, ROUTER_NAME20)

    SECURITY_GROUP_ID = UUID(int=666)
    SECURITY_GROUP_NAME = u'ultra-mega-security-弹射'
    SECURITY_GROUP_DESCRIPTION = 'as safe as it gets'
    SECURITY_GROUP = OvnSecurityGroupRow(
        SECURITY_GROUP_ID,
        str(SECURITY_GROUP_ID),
        external_ids={
            SecurityGroupMapper.OVN_SECURITY_GROUP_DESCRIPTION: SECURITY_GROUP_DESCRIPTION,  # noqa: E501
            SecurityGroupMapper.OVN_SECURITY_GROUP_CREATE_TS: '',
            SecurityGroupMapper.OVN_SECURITY_GROUP_UPDATE_TS: '',
            SecurityGroupMapper.OVN_SECURITY_GROUP_REV_NUMBER: '1',
            SecurityGroupMapper.OVN_SECURITY_GROUP_TENANT: tenant_id(),
            SecurityGroupMapper.OVN_SECURITY_GROUP_PROJECT: tenant_id(),
            SecurityGroupMapper.OVN_SECURITY_GROUP_NAME: SECURITY_GROUP_NAME,
        },
    )
    DEFAULT_SECURITY_GROUP = OvnSecurityGroupRow(
        SECURITY_GROUP_ID,
        'Default',
        external_ids={
            SecurityGroupMapper.OVN_SECURITY_GROUP_DESCRIPTION: SECURITY_GROUP_DESCRIPTION,  # noqa: E501
            SecurityGroupMapper.OVN_SECURITY_GROUP_CREATE_TS: '',
            SecurityGroupMapper.OVN_SECURITY_GROUP_UPDATE_TS: '',
            SecurityGroupMapper.OVN_SECURITY_GROUP_REV_NUMBER: '1',
            SecurityGroupMapper.OVN_SECURITY_GROUP_TENANT: tenant_id(),
            SecurityGroupMapper.OVN_SECURITY_GROUP_PROJECT: tenant_id(),
        },
    )

    SECURITY_GROUP_RULE_ID_01 = UUID(int=1)
    SECURITY_GROUP_RULE_ID_02 = UUID(int=2)
    SECURITY_GROUP_RULE_ID_03 = UUID(int=3)
    SECURITY_GROUP_RULE_01_EXT_IDS = {
        SecurityGroupRuleMapper.OVN_SEC_GROUP_RULE_SEC_GROUP_ID: str(
            SECURITY_GROUP_ID
        ),
        SecurityGroupRuleMapper.OVN_SEC_GROUP_RULE_PROTOCOL: neutron_constants.PROTO_NAME_TCP,  # noqa: E501
        SecurityGroupRuleMapper.OVN_SEC_GROUP_RULE_ETHERTYPE: neutron_constants.IPV4_ETHERTYPE,  # noqa: E501
    }
    SECURITY_GROUP_RULE_02_EXT_IDS = {
        SecurityGroupRuleMapper.OVN_SEC_GROUP_RULE_SEC_GROUP_ID: str(
            SECURITY_GROUP_ID
        ),
        SecurityGroupRuleMapper.OVN_SEC_GROUP_RULE_PROTOCOL: 'udp',
        SecurityGroupRuleMapper.OVN_SEC_GROUP_RULE_ETHERTYPE: 'IPv6',
    }
    SECURITY_GROUP_RULE_03_EXT_IDS = {
        SecurityGroupRuleMapper.OVN_SEC_GROUP_RULE_SEC_GROUP_ID: str(
            SECURITY_GROUP_ID
        ),
        SecurityGroupRuleMapper.OVN_SEC_GROUP_RULE_PROTOCOL: 'udp',
        SecurityGroupRuleMapper.OVN_SEC_GROUP_RULE_ETHERTYPE: 'IPv4',
        SecurityGroupRuleMapper.OVN_SEC_GROUP_RULE_MIN_PORT: '161',
    }
    SECURITY_GROUP_RULE_01 = OvnSecurityGroupRuleRow(
        SECURITY_GROUP_RULE_ID_01,
        str(SECURITY_GROUP_RULE_ID_01),
        'from-lport',
        'ip4 && tcp',
        1001,
        str(SECURITY_GROUP_ID),
        'allow',
        SECURITY_GROUP_RULE_01_EXT_IDS,
    )

    SECURITY_GROUP_RULE_02 = OvnSecurityGroupRuleRow(
        SECURITY_GROUP_RULE_ID_02,
        str(SECURITY_GROUP_RULE_ID_02),
        'to-lport',
        'ip6 && udp',
        1000,
        str(SECURITY_GROUP_ID),
        'drop',
        SECURITY_GROUP_RULE_02_EXT_IDS,
    )
    SECURITY_GROUP_RULE_03 = OvnSecurityGroupRuleRow(
        SECURITY_GROUP_RULE_ID_03,
        str(SECURITY_GROUP_RULE_ID_03),
        'from-lport',
        'ip4 && udp && udp.dst == 161',
        1001,
        str(SECURITY_GROUP_ID),
        'allow',
        SECURITY_GROUP_RULE_03_EXT_IDS,
    )

    ports = [PORT_1, PORT_2, PORT_3]

    networks = [NETWORK_10, NETWORK_11, NETWORK_LOCALNET_12]

    subnets = [SUBNET_101, SUBNET_102]
