# Copyright 2026 Red Hat, Inc.
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
from unittest import mock

import pytest

import constants as ovnconst
from handlers.base_handler import BadRequestError
from handlers.base_handler import ConflictError
from handlers.base_handler import ElementNotFoundError
from neutron.api.floating_ips import FloatingIpTarget
from neutron.neutron_api import NeutronApi
from neutron.mappers.floating_ips import FloatingIP
from neutron.mappers.floating_ips import FloatingipMapper
from neutron.mappers.ports import PortMapper
from neutron.mappers.base import RestDataError
from neutron.mappers.routers import RouterMapper
from neutron.mappers.subnets import SubnetMapper

Lsp = namedtuple(
    'Lsp',
    [
        'uuid',
        'name',
        'type',
        'addresses',
        'dynamic_addresses',
        'external_ids',
        'options',
        'dhcpv4_options',
        'dhcpv6_options',
    ],
)
Ls = namedtuple('Ls', ['uuid', 'name', 'ports', 'other_config'])
Dhcp = namedtuple('Dhcp', ['uuid', 'cidr', 'options', 'external_ids'])
Lr = namedtuple('Lr', ['uuid', 'name', 'external_ids'])

FIP_ID = '11111111-1111-1111-1111-111111111111'
VM_PORT_ID = '22222222-2222-2222-2222-222222222222'
GW_PORT_ID = '33333333-3333-3333-3333-333333333333'
ROUTER_ID = '44444444-4444-4444-4444-444444444444'
EXT_NET_ID = '55555555-5555-5555-5555-555555555555'
INT_NET_ID = '66666666-6666-6666-6666-666666666666'
FIP_IP = '172.16.0.10'


def make_lsp(
    name, addresses, external_ids=None, port_type='', dynamic_addresses=None
):
    return Lsp(
        uuid=name,
        name=name,
        type=port_type,
        addresses=addresses,
        dynamic_addresses=dynamic_addresses or [],
        external_ids=external_ids or {},
        options={},
        dhcpv4_options=[],
        dhcpv6_options=[],
    )


def make_fip_lsp(**extra_ids):
    external_ids = {
        FloatingipMapper.OVN_FLOATINGIP_MARKER: 'true',
        PortMapper.OVN_NIC_NAME: FloatingipMapper.FLOATINGIP_PREFIX + FIP_ID,
        FloatingipMapper.OVN_FLOATINGIP_CREATE_TS: '2026-01-01T00:00:00',
    }
    external_ids.update(extra_ids)
    return make_lsp(FIP_ID, [f'00:00:00:00:00:01 {FIP_IP}'], external_ids)


def make_api():
    api = object.__new__(NeutronApi)
    api.idl = mock.MagicMock()
    api.ovn_north = mock.MagicMock()
    api.tx_manager = mock.MagicMock()
    api.security_group_support = False
    return api


class TestFloatingipMapper(object):
    def test_update_passes_id_and_omits_missing_port_id(self):
        func = mock.Mock()
        FloatingipMapper.rest2row(
            None, func, {'description': 'x'}, floatingip_id=FIP_ID
        )
        func.assert_called_once_with(
            None, floatingip_id=FIP_ID, description='x'
        )

    def test_update_keeps_explicit_null_port_id(self):
        func = mock.Mock()
        FloatingipMapper.rest2row(
            None, func, {'port_id': None}, floatingip_id=FIP_ID
        )
        func.assert_called_once_with(
            None, floatingip_id=FIP_ID, description=None, port_id=None
        )

    def test_add(self):
        func = mock.Mock()
        FloatingipMapper.rest2row(
            None,
            func,
            {'floating_network_id': EXT_NET_ID, 'port_id': VM_PORT_ID},
            None,
        )
        func.assert_called_once_with(
            None,
            network_id=EXT_NET_ID,
            floating_ip_address=None,
            description=None,
            port_id=VM_PORT_ID,
        )

    def test_add_requires_network(self):
        with pytest.raises(RestDataError):
            FloatingipMapper.validate_add_rest_input({})

    def test_long_description_rejected(self):
        with pytest.raises(RestDataError):
            FloatingipMapper.validate_update_rest_input(
                {'description': 'x' * 65}
            )

    def test_row2rest_unassociated(self):
        network = Ls(EXT_NET_ID, 'ext', [], {})
        rest = FloatingipMapper.row2rest(
            FloatingIP(make_fip_lsp(), network, None, None)
        )
        assert rest['id'] == FIP_ID
        assert rest['floating_ip_address'] == FIP_IP
        assert rest['floating_network_id'] == EXT_NET_ID
        assert rest['status'] == FloatingipMapper.STATUS_DOWN
        assert rest['port_id'] is None
        assert rest['router_id'] is None
        assert rest['created_at'] == '2026-01-01T00:00:00Z'
        assert rest['updated_at'] is None


class TestFloatingipApi(object):
    def _network(self, ports, exclude_ips=None):
        other_config = {}
        if exclude_ips:
            other_config[ovnconst.LS_OPTION_EXCLUDE_IPS] = exclude_ips
        return Ls(EXT_NET_ID, 'ext', ports, other_config)

    def _subnet(self, cidr='172.16.0.0/29', gateway='172.16.0.1'):
        return Dhcp(
            'subnet-uuid', cidr, {SubnetMapper.OVN_GATEWAY: gateway}, {}
        )

    def test_allocate_skips_gateway_used_and_excluded(self):
        api = make_api()
        used = make_lsp('p1', ['00:00:00:00:00:02 172.16.0.2'])
        network = self._network([used], exclude_ips='172.16.0.3..172.16.0.4')
        address = api._allocate_floating_ip_address(
            network, self._subnet(), None
        )
        assert address == '172.16.0.5'

    def test_allocate_exhausted(self):
        api = make_api()
        network = self._network([], exclude_ips='172.16.0.2..172.16.0.6')
        with pytest.raises(ConflictError):
            api._allocate_floating_ip_address(network, self._subnet(), None)

    def test_allocate_requested_in_use(self):
        api = make_api()
        used = make_lsp('p1', ['00:00:00:00:00:02 172.16.0.2'])
        with pytest.raises(ConflictError):
            api._allocate_floating_ip_address(
                self._network([used]), self._subnet(), '172.16.0.2'
            )

    def test_allocate_requested_outside_subnet(self):
        api = make_api()
        with pytest.raises(BadRequestError):
            api._allocate_floating_ip_address(
                self._network([]), self._subnet(), '10.0.0.1'
            )

    def test_allocate_requested_broadcast(self):
        api = make_api()
        with pytest.raises(BadRequestError):
            api._allocate_floating_ip_address(
                self._network([]), self._subnet(), '172.16.0.7'
            )

    def test_port_named_like_floatingip_is_not_one(self):
        api = make_api()
        port = make_lsp(
            VM_PORT_ID,
            ['00:00:00:00:00:02 10.0.0.2'],
            {PortMapper.OVN_NIC_NAME: 'fip-vm'},
        )
        assert not api._is_floating_ip_port(port)
        assert api._is_floating_ip_port(make_fip_lsp())

    def test_non_floatingip_port_is_not_found(self):
        api = make_api()
        api.ovn_north.get_lsp.return_value = make_lsp(
            VM_PORT_ID,
            ['00:00:00:00:00:02 10.0.0.2'],
            {PortMapper.OVN_NIC_NAME: 'vm'},
        )
        with pytest.raises(ElementNotFoundError):
            api.delete_floatingip(VM_PORT_ID)
        api.ovn_north.remove_lsp.assert_not_called()

    def test_delete_removes_nat_and_port(self):
        api = make_api()
        fip = make_fip_lsp(
            **{
                FloatingipMapper.OVN_FLOATINGIP_PORT_ID: VM_PORT_ID,
                FloatingipMapper.OVN_FLOATINGIP_ROUTER_ID: ROUTER_ID,
            }
        )
        api.ovn_north.get_lsp.return_value = fip
        api.delete_floatingip(FIP_ID)
        tx = api.tx_manager.transaction.return_value.__enter__.return_value
        api.ovn_north.remove_nat.assert_called_once_with(
            lr_id=ROUTER_ID,
            nat_type=ovnconst.NAT_BOTH,
            match_ip=FIP_IP,
            transaction=tx,
        )
        api.ovn_north.remove_lsp.assert_called_once_with(
            FIP_ID, transaction=tx
        )

    def test_update_with_null_port_disassociates(self):
        api = make_api()
        fip = make_fip_lsp(
            **{
                FloatingipMapper.OVN_FLOATINGIP_PORT_ID: VM_PORT_ID,
                FloatingipMapper.OVN_FLOATINGIP_ROUTER_ID: ROUTER_ID,
            }
        )

        def get_lsp(lsp_id):
            if lsp_id == FIP_ID:
                return fip
            # the formerly associated port no longer exists
            raise ElementNotFoundError(lsp_id)

        api.ovn_north.get_lsp.side_effect = get_lsp
        api.ovn_north.list_ls.return_value = [self._network([fip])]
        api.ovn_north.get_dhcp.return_value = None
        rest = api.update_floatingip({'port_id': None}, FIP_ID)
        assert rest['id'] == FIP_ID
        api.ovn_north.remove_nat.assert_called_once()
        removed_keys = {
            call.args[3] for call in api.idl.db_remove.call_args_list
        }
        assert removed_keys == {
            FloatingipMapper.OVN_FLOATINGIP_PORT_ID,
            FloatingipMapper.OVN_FLOATINGIP_ROUTER_ID,
        }
        api.ovn_north.add_nat.assert_not_called()

    def _setup_target(self, api, gw_network_id=EXT_NET_ID, router=True):
        vm_port = make_lsp(
            VM_PORT_ID,
            ['00:00:00:00:00:02 10.0.0.2'],
            {PortMapper.OVN_NIC_NAME: 'vm'},
        )
        gw_port = make_lsp(GW_PORT_ID, ['router'], port_type='router')
        internal = Ls(INT_NET_ID, 'int', [vm_port], {})
        external = Ls(gw_network_id, 'ext', [gw_port], {})
        ports = {VM_PORT_ID: vm_port, GW_PORT_ID: gw_port}
        api.ovn_north.get_lsp.side_effect = lambda lsp_id: ports[lsp_id]
        api.ovn_north.list_ls.return_value = [internal, external]
        subnet_ids = (
            {SubnetMapper.OVN_GATEWAY_ROUTER_ID: ROUTER_ID} if router else {}
        )
        api.ovn_north.get_dhcp.return_value = Dhcp(
            'int-subnet', '10.0.0.0/24', {}, subnet_ids
        )
        api.ovn_north.get_lr.return_value = Lr(
            ROUTER_ID,
            'r1',
            {RouterMapper.OVN_ROUTER_GATEWAY_PORT: GW_PORT_ID},
        )

    def test_target_ok(self):
        api = make_api()
        self._setup_target(api)
        assert api._get_floatingip_target(
            EXT_NET_ID, VM_PORT_ID
        ) == FloatingIpTarget(VM_PORT_ID, ROUTER_ID, '10.0.0.2')

    def test_target_subnet_without_router(self):
        api = make_api()
        self._setup_target(api, router=False)
        with pytest.raises(BadRequestError):
            api._get_floatingip_target(EXT_NET_ID, VM_PORT_ID)

    def test_target_router_gateway_on_other_network(self):
        api = make_api()
        self._setup_target(api, gw_network_id='other-network')
        with pytest.raises(BadRequestError):
            api._get_floatingip_target(EXT_NET_ID, VM_PORT_ID)
