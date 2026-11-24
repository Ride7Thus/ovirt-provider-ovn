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
#
"""
Router SNAT and floating IP scenarios, verified against the OVN north DB.

Requires PROVIDER_CONTAINER_ID (set by automation/create_it_env.sh) and the
provider configured with ovn-gateway-chassis.
"""

import contextlib
import os

import pytest
import requests

from lib.containerlib import ovn_nbctl

ENDPOINT = 'http://localhost:9696/v2.0/'

EXT_CIDR = '172.30.0.0/24'
EXT_GATEWAY = '172.30.0.1'
ROUTER_EXT_IP = '172.30.0.2'
INT_CIDR = '10.30.0.0/24'
INT_GATEWAY = '10.30.0.1'
VM_IP = '10.30.0.10'

GATEWAY_CHASSIS = os.environ.get('OVN_GATEWAY_CHASSIS')

NAT_SNAT = 'snat'
NAT_BOTH = 'dnat_and_snat'


def _url(*parts):
    return ENDPOINT + '/'.join(parts)


def _post(entity, payload):
    return requests.post(_url(entity), json=payload)


def _put(entity, entity_id, payload):
    return requests.put(_url(entity, entity_id), json=payload)


def _get(entity, entity_id):
    return requests.get(_url(entity, entity_id))


def _delete(entity, entity_id):
    return requests.delete(_url(entity, entity_id))


def _created(response, key):
    assert response.status_code == 201, response.text
    return response.json()[key]


@contextlib.contextmanager
def _resource(entity, key, payload):
    resource = _created(_post(entity, payload), key)
    try:
        yield resource
    finally:
        _delete(entity, resource['id'])


@contextlib.contextmanager
def _network_with_subnet(name, cidr, gateway):
    with _resource('networks', 'network', {'network': {'name': name}}) as net:
        subnet_payload = {
            'subnet': {
                'name': name + '-subnet',
                'network_id': net['id'],
                'ip_version': 4,
                'cidr': cidr,
                'gateway_ip': gateway,
            }
        }
        with _resource('subnets', 'subnet', subnet_payload) as subnet:
            yield net, subnet


def _router_interface(router_id, action, subnet_id):
    return requests.put(
        _url('routers', router_id, action), json={'subnet_id': subnet_id}
    )


def router_nat(router_id):
    nat_ids = ovn_nbctl(
        '--bare', '--columns=nat', 'list', 'Logical_Router', router_id
    ).split()
    rules = set()
    for nat_id in nat_ids:
        nat_type, external_ip, logical_ip = ovn_nbctl(
            '--bare',
            '--columns=type,external_ip,logical_ip',
            'list',
            'NAT',
            nat_id,
        ).split()
        rules.add((nat_type, external_ip, logical_ip))
    return rules


def router_gateway_chassis(router_id):
    gw_port_id = ovn_nbctl(
        'get', 'Logical_Router', router_id, 'external_ids:ovirt_gateway_port'
    ).strip('"')
    output = ovn_nbctl('lrp-get-gateway-chassis', 'lrp-' + gw_port_id)
    return [line.split()[0] for line in output.splitlines() if line.strip()]


@pytest.fixture(scope='module')
def external_network():
    with _network_with_subnet('fip-ext', EXT_CIDR, EXT_GATEWAY) as network:
        yield network


@pytest.fixture(scope='module')
def internal_network():
    with _network_with_subnet('fip-int', INT_CIDR, INT_GATEWAY) as network:
        yield network


@pytest.fixture(scope='module')
def router(external_network, internal_network):
    ext_net, ext_subnet = external_network
    _, int_subnet = internal_network
    payload = {
        'router': {
            'name': 'fip-router',
            # enable_snat is left out on purpose: it defaults to true
            'external_gateway_info': {
                'network_id': ext_net['id'],
                'external_fixed_ips': [
                    {
                        'subnet_id': ext_subnet['id'],
                        'ip_address': ROUTER_EXT_IP,
                    }
                ],
            },
        }
    }
    router = _created(_post('routers', payload), 'router')
    response = _router_interface(
        router['id'], 'add_router_interface', int_subnet['id']
    )
    assert response.status_code == 200, response.text
    try:
        yield router
    finally:
        _router_interface(
            router['id'], 'remove_router_interface', int_subnet['id']
        )
        _delete('routers', router['id'])


@pytest.fixture
def vm_port(internal_network):
    int_net, int_subnet = internal_network
    payload = {
        'port': {
            'name': 'fip-vm',
            'network_id': int_net['id'],
            'admin_state_up': True,
            'fixed_ips': [
                {'subnet_id': int_subnet['id'], 'ip_address': VM_IP}
            ],
        }
    }
    port = _created(_post('ports', payload), 'port')
    try:
        yield port
    finally:
        _delete('ports', port['id'])


def test_router_snat_enabled_by_default(router):
    gateway_info = router['external_gateway_info']
    assert gateway_info['enable_snat'] is True
    assert (NAT_SNAT, ROUTER_EXT_IP, INT_CIDR) in router_nat(router['id'])


@pytest.mark.skipif(
    not GATEWAY_CHASSIS, reason='OVN_GATEWAY_CHASSIS is not set'
)
def test_router_gateway_bound_to_chassis(router):
    gw_port_id = ovn_nbctl(
        'get',
        'Logical_Router',
        router['id'],
        'external_ids:ovirt_gateway_port',
    ).strip('"')
    # ovsdbapp names the Gateway_Chassis rows <lrp name>_<chassis name>
    assert router_gateway_chassis(router['id']) == [
        'lrp-{}_{}'.format(gw_port_id, GATEWAY_CHASSIS)
    ]


def test_disable_and_enable_snat(router, external_network):
    ext_net, ext_subnet = external_network
    gateway_info = {
        'network_id': ext_net['id'],
        'external_fixed_ips': [
            {'subnet_id': ext_subnet['id'], 'ip_address': ROUTER_EXT_IP}
        ],
    }
    for enable_snat in (False, True):
        gateway_info['enable_snat'] = enable_snat
        response = _put(
            'routers',
            router['id'],
            {'router': {'external_gateway_info': gateway_info}},
        )
        assert response.status_code == 200, response.text
        updated = response.json()['router']
        assert updated['external_gateway_info']['enable_snat'] is enable_snat
        snat = (NAT_SNAT, ROUTER_EXT_IP, INT_CIDR)
        assert (snat in router_nat(router['id'])) is enable_snat


def test_floating_ip_lifecycle(
    router, external_network, internal_network, vm_port
):
    ext_net, ext_subnet = external_network
    _, int_subnet = internal_network

    floatingip = _created(
        _post(
            'floatingips',
            {
                'floatingip': {
                    'floating_network_id': ext_net['id'],
                    'port_id': vm_port['id'],
                    'description': 'it',
                }
            },
        ),
        'floatingip',
    )
    try:
        fip_ip = floatingip['floating_ip_address']
        assert floatingip['status'] == 'ACTIVE'
        assert floatingip['router_id'] == router['id']
        assert floatingip['fixed_ip_address'] == VM_IP
        assert floatingip['subnet_id'] == ext_subnet['id']
        assert fip_ip not in (EXT_GATEWAY, ROUTER_EXT_IP)
        assert (NAT_BOTH, fip_ip, VM_IP) in router_nat(router['id'])

        # resources the floating IP depends on can not be removed
        assert _delete('routers', router['id']).status_code == 409
        assert (
            _router_interface(
                router['id'], 'remove_router_interface', int_subnet['id']
            ).status_code
            == 409
        )
        assert _delete('ports', floatingip['id']).status_code == 409

        # an explicit null port_id disassociates
        response = _put(
            'floatingips', floatingip['id'], {'floatingip': {'port_id': None}}
        )
        assert response.status_code == 200, response.text
        assert response.json()['floatingip']['status'] == 'DOWN'
        assert response.json()['floatingip']['router_id'] is None
        assert (NAT_BOTH, fip_ip, VM_IP) not in router_nat(router['id'])

        # a missing port_id leaves the association alone
        response = _put(
            'floatingips',
            floatingip['id'],
            {'floatingip': {'port_id': vm_port['id']}},
        )
        assert response.status_code == 200, response.text
        response = _put(
            'floatingips',
            floatingip['id'],
            {'floatingip': {'description': 'updated'}},
        )
        assert response.status_code == 200, response.text
        updated = response.json()['floatingip']
        assert updated['description'] == 'updated'
        assert updated['port_id'] == vm_port['id']
        assert (NAT_BOTH, fip_ip, VM_IP) in router_nat(router['id'])
    finally:
        assert _delete('floatingips', floatingip['id']).status_code in (
            200,
            204,
        )

    assert _get('floatingips', floatingip['id']).status_code == 404
    assert not any(rule[0] == NAT_BOTH for rule in router_nat(router['id']))


def test_deleting_port_disassociates_floating_ip(
    router, external_network, internal_network
):
    ext_net, _ = external_network
    int_net, int_subnet = internal_network
    port = _created(
        _post(
            'ports',
            {
                'port': {
                    'name': 'fip-short-lived',
                    'network_id': int_net['id'],
                    'fixed_ips': [{'subnet_id': int_subnet['id']}],
                }
            },
        ),
        'port',
    )
    with _resource(
        'floatingips',
        'floatingip',
        {
            'floatingip': {
                'floating_network_id': ext_net['id'],
                'port_id': port['id'],
            }
        },
    ) as floatingip:
        assert _delete('ports', port['id']).status_code in (200, 204)
        current = _get('floatingips', floatingip['id']).json()['floatingip']
        assert current['port_id'] is None
        assert current['status'] == 'DOWN'
        assert not any(
            rule[0] == NAT_BOTH for rule in router_nat(router['id'])
        )


def test_requested_floating_ip_address(external_network):
    ext_net, _ = external_network
    payload = {
        'floatingip': {
            'floating_network_id': ext_net['id'],
            'floating_ip_address': '172.30.0.50',
        }
    }
    with _resource('floatingips', 'floatingip', payload) as floatingip:
        assert floatingip['floating_ip_address'] == '172.30.0.50'
        assert floatingip['status'] == 'DOWN'
        assert _post('floatingips', payload).status_code == 409

    payload['floatingip']['floating_ip_address'] = '10.99.0.1'
    assert _post('floatingips', payload).status_code == 400
