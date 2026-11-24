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
from neutron.neutron_api import NeutronApi
from neutron.neutron_api_mappers import RestDataError
from neutron.neutron_api_mappers import RouterMapper

Lr = namedtuple('Lr', ['uuid', 'name', 'ports', 'nat', 'external_ids'])
Lrp = namedtuple('Lrp', ['uuid', 'name', 'networks', 'gateway_chassis'])
Nat = namedtuple('Nat', ['type', 'external_ip', 'logical_ip'])
Lsp = namedtuple('Lsp', ['uuid', 'name', 'external_ids'])
Ls = namedtuple('Ls', ['uuid', 'ports'])

ROUTER_ID = '44444444-4444-4444-4444-444444444444'
GW_LSP_ID = '33333333-3333-3333-3333-333333333333'
GW_IP = '172.16.0.2'

GW_LRP = Lrp('gw-lrp', 'lrp-' + GW_LSP_ID, [GW_IP + '/24'], ['gw-chassis'])
INT_LRP = Lrp('int-lrp', 'lrp-int', ['10.0.0.1/24'], [])
INT6_LRP = Lrp('int6-lrp', 'lrp-int6', ['fd00::1/64'], [])


def make_api():
    api = object.__new__(NeutronApi)
    api.idl = mock.MagicMock()
    api.ovn_north = mock.MagicMock()
    api.ovn_north.list_ls.return_value = []
    api.tx_manager = mock.MagicMock()
    api.security_group_support = False
    return api


def make_lr(ports, nat=(), snat=True, gateway=True):
    external_ids = {}
    if gateway:
        external_ids[RouterMapper.OVN_ROUTER_GATEWAY_PORT] = GW_LSP_ID
    if snat:
        external_ids[RouterMapper.OVN_ROUTER_ENABLE_SNAT] = 'true'
    return Lr(ROUTER_ID, 'r1', list(ports), list(nat), external_ids)


def setup_router(api, lr):
    api.ovn_north.get_lr.return_value = lr
    api.ovn_north.get_lrp.return_value = GW_LRP
    api.ovn_north.lrp_has_gateway_chassis.side_effect = lambda lrp: bool(
        lrp.gateway_chassis
    )


class TestRouterSnatMapping(object):
    def test_enable_snat_defaults_to_true_with_gateway(self):
        rest = {
            'external_gateway_info': {
                'network_id': 'net',
                'external_fixed_ips': [
                    {'subnet_id': 's', 'ip_address': GW_IP}
                ],
            }
        }
        assert RouterMapper._get_enable_snat_from_rest(rest) is True

    def test_enable_snat_untouched_without_gateway(self):
        assert RouterMapper._get_enable_snat_from_rest({'name': 'r'}) is None

    def test_enable_snat_must_be_bool(self):
        with pytest.raises(RestDataError):
            RouterMapper._validate_external_gateway_info(
                {
                    'external_gateway_info': {
                        'network_id': 'net',
                        'enable_snat': 'yes',
                        'external_fixed_ips': [
                            {'subnet_id': 's', 'ip_address': GW_IP}
                        ],
                    }
                }
            )

    def test_is_snat_enabled(self):
        assert RouterMapper.is_snat_enabled(make_lr([], snat=True))
        assert not RouterMapper.is_snat_enabled(make_lr([], snat=False))


class TestRouterSnatSync(object):
    def _tx(self, api):
        return api.tx_manager.transaction.return_value.__enter__.return_value

    def test_adds_snat_for_ipv4_interfaces_only(self):
        api = make_api()
        setup_router(api, make_lr([GW_LRP, INT_LRP, INT6_LRP]))
        api._sync_router_snat(ROUTER_ID)
        api.ovn_north.add_nat.assert_called_once_with(
            lr_id=ROUTER_ID,
            nat_type=ovnconst.NAT_SNAT,
            external_ip=GW_IP,
            logical_ip='10.0.0.0/24',
            transaction=self._tx(api),
        )
        api.ovn_north.remove_nat.assert_not_called()

    def test_in_sync_does_nothing(self):
        api = make_api()
        nat = [Nat(ovnconst.NAT_SNAT, GW_IP, '10.0.0.0/24')]
        setup_router(api, make_lr([GW_LRP, INT_LRP], nat=nat))
        api._sync_router_snat(ROUTER_ID)
        api.tx_manager.transaction.assert_not_called()

    def test_removes_stale_snat_and_keeps_floatingip_nat(self):
        api = make_api()
        nat = [
            Nat(ovnconst.NAT_SNAT, GW_IP, '10.0.0.0/24'),
            Nat(ovnconst.NAT_BOTH, '172.16.0.10', '10.0.0.5'),
        ]
        setup_router(api, make_lr([GW_LRP], nat=nat))
        api._sync_router_snat(ROUTER_ID)
        api.ovn_north.remove_nat.assert_called_once_with(
            lr_id=ROUTER_ID,
            nat_type=ovnconst.NAT_SNAT,
            match_ip='10.0.0.0/24',
            transaction=self._tx(api),
        )
        api.ovn_north.add_nat.assert_not_called()

    def test_disabled_snat_removes_rules(self):
        api = make_api()
        nat = [Nat(ovnconst.NAT_SNAT, GW_IP, '10.0.0.0/24')]
        setup_router(api, make_lr([GW_LRP, INT_LRP], nat=nat, snat=False))
        api._sync_router_snat(ROUTER_ID)
        api.ovn_north.remove_nat.assert_called_once()
        api.ovn_north.add_nat.assert_not_called()


class TestGatewayChassis(object):
    def test_bound_port_left_alone(self):
        api = make_api()
        setup_router(api, make_lr([GW_LRP]))
        assert api._ensure_gateway_chassis(GW_LRP.name)
        api.ovn_north.set_lrp_gateway_chassis.assert_not_called()

    @mock.patch(
        'neutron.neutron_api.gateway_chassis', return_value=['ch1', 'ch2']
    )
    def test_configured_chassis_applied(self, mock_chassis):
        api = make_api()
        unbound = GW_LRP._replace(gateway_chassis=[])
        api.ovn_north.get_lrp.return_value = unbound
        api.ovn_north.lrp_has_gateway_chassis.return_value = False
        assert api._ensure_gateway_chassis(unbound.name)
        api.ovn_north.set_lrp_gateway_chassis.assert_called_once_with(
            unbound.name, ['ch1', 'ch2']
        )

    @mock.patch('neutron.neutron_api.gateway_chassis', return_value=[])
    def test_no_chassis_configured(self, mock_chassis):
        api = make_api()
        api.ovn_north.get_lrp.return_value = GW_LRP._replace(
            gateway_chassis=[]
        )
        api.ovn_north.lrp_has_gateway_chassis.return_value = False
        assert not api._ensure_gateway_chassis(GW_LRP.name)
