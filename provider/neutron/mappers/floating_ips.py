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
import neutron.ip as ip_utils
from ovirt_provider_config_common import tenant_id
from neutron.mappers.base import Mapper
from neutron.mappers.base import RestDataError
from neutron.mappers.base import to_rest_timestamp
from neutron.mappers.ports import PortMapper


FloatingIP = namedtuple(
    'FloatingIP',
    [
        'floatingip',
        'floatingip_network',
        'floatingip_subnet',
        'floatingip_port',
    ],
)


class FloatingNetworkIdRequiredError(RestDataError):
    message = 'floating_network_id is required for a floating IP'

    def __init__(self):
        super(FloatingNetworkIdRequiredError, self).__init__(self.message)


class FloatingipMapper(Mapper):
    # The names of properties received/sent in a REST request
    REST_FLOATINGIP_ID = 'id'
    REST_FLOATINGIP_NETWORK_ID = 'floating_network_id'
    REST_FLOATINGIP_IP_ADDRESS = 'floating_ip_address'
    REST_FLOATINGIP_FIXED_IP = 'fixed_ip_address'
    REST_FLOATINGIP_SUBNET_ID = 'subnet_id'
    REST_FLOATINGIP_PORT_ID = 'port_id'
    REST_FLOATINGIP_ROUTER_ID = 'router_id'
    REST_FLOATINGIP_PORT_DETAILS = 'port_details'
    REST_FLOATINGIP_STATUS = 'status'
    REST_FLOATINGIP_PORT_FORWARDINGS = 'port_forwardings'
    REST_FLOATINGIP_DESCRIPTION = 'description'
    REST_FLOATINGIP_CREATED_AT = 'created_at'
    REST_FLOATINGIP_UPDATED_AT = 'updated_at'

    OVN_FLOATINGIP_DESCRIPTION = 'ovirt_description'
    OVN_FLOATINGIP_UPDATE_TS = 'ovirt_updated_at'
    OVN_FLOATINGIP_CREATE_TS = 'ovirt_created_at'
    OVN_FLOATINGIP_ROUTER_ID = 'ovirt_gateway_id'
    OVN_FLOATINGIP_PORT_ID = 'ovirt_fip_port_id'

    # Marks the LSPs backing floating IPs. It is not reachable through the
    # REST API, unlike port names or device owners.
    OVN_FLOATINGIP_MARKER = 'ovirt_floatingip'

    FLOATINGIP_PREFIX = 'fip-'
    DEVICE_OWNER_FLOATING_IP = 'network:floatingip'

    STATUS_ACTIVE = 'ACTIVE'
    STATUS_DOWN = 'DOWN'

    PORT_DETAILS_KEYS = (
        PortMapper.REST_PORT_NAME,
        PortMapper.REST_PORT_NETWORK_ID,
        PortMapper.REST_PORT_MAC_ADDRESS,
        PortMapper.REST_PORT_ADMIN_STATE_UP,
        PortMapper.REST_PORT_DEVICE_ID,
        PortMapper.REST_PORT_DEVICE_OWNER,
    )

    @staticmethod
    def rest2row(wrapped_self, func, rest_data, floatingip_id):
        description = rest_data.get(
            FloatingipMapper.REST_FLOATINGIP_DESCRIPTION
        )
        kwargs = {'description': description}
        # On update, a missing port_id means "leave the association as is",
        # while an explicit null means "disassociate".
        if FloatingipMapper.REST_FLOATINGIP_PORT_ID in rest_data:
            kwargs['port_id'] = rest_data[
                FloatingipMapper.REST_FLOATINGIP_PORT_ID
            ]

        if floatingip_id:
            return func(wrapped_self, floatingip_id=floatingip_id, **kwargs)
        return func(
            wrapped_self,
            network_id=rest_data.get(
                FloatingipMapper.REST_FLOATINGIP_NETWORK_ID
            ),
            floating_ip_address=rest_data.get(
                FloatingipMapper.REST_FLOATINGIP_IP_ADDRESS
            ),
            **kwargs,
        )

    @staticmethod
    def row2rest(row):
        if not row:
            return {}
        floatingip, network, subnet, port = row
        port_details = {}
        port_id = None
        fixed_ip_address = None
        if port is not None:
            port_rest_data = PortMapper.row2rest(port)
            port_id = port_rest_data[PortMapper.REST_PORT_ID]
            fixed_ips = port_rest_data.get(PortMapper.REST_PORT_FIXED_IPS)
            if fixed_ips:
                fixed_ip_address = fixed_ips[0][
                    PortMapper.REST_PORT_IP_ADDRESS
                ]
            port_details = {
                key: port_rest_data.get(key)
                for key in FloatingipMapper.PORT_DETAILS_KEYS
            }
            port_details[FloatingipMapper.REST_FLOATINGIP_STATUS] = (
                FloatingipMapper.STATUS_ACTIVE
                if port_rest_data.get(PortMapper.REST_PORT_ADMIN_STATE_UP)
                else FloatingipMapper.STATUS_DOWN
            )

        external_ids = floatingip.external_ids
        return {
            FloatingipMapper.REST_FLOATINGIP_ID: floatingip.name,
            FloatingipMapper.REST_FLOATINGIP_NETWORK_ID: str(network.uuid),
            FloatingipMapper.REST_TENANT_ID: tenant_id(),
            FloatingipMapper.REST_PROJECT_ID: tenant_id(),
            FloatingipMapper.REST_FLOATINGIP_IP_ADDRESS: (
                ip_utils.get_port_ip(floatingip)
            ),
            FloatingipMapper.REST_FLOATINGIP_FIXED_IP: fixed_ip_address,
            FloatingipMapper.REST_FLOATINGIP_SUBNET_ID: (
                str(subnet.uuid) if subnet else None
            ),
            FloatingipMapper.REST_FLOATINGIP_PORT_ID: port_id,
            FloatingipMapper.REST_FLOATINGIP_ROUTER_ID: (
                external_ids.get(FloatingipMapper.OVN_FLOATINGIP_ROUTER_ID)
                if port is not None
                else None
            ),
            FloatingipMapper.REST_FLOATINGIP_STATUS: (
                FloatingipMapper.STATUS_ACTIVE
                if port is not None
                else FloatingipMapper.STATUS_DOWN
            ),
            FloatingipMapper.REST_FLOATINGIP_PORT_DETAILS: port_details,
            FloatingipMapper.REST_FLOATINGIP_PORT_FORWARDINGS: [],
            FloatingipMapper.REST_FLOATINGIP_DESCRIPTION: external_ids.get(
                FloatingipMapper.OVN_FLOATINGIP_DESCRIPTION, ''
            ),
            FloatingipMapper.REST_FLOATINGIP_CREATED_AT: to_rest_timestamp(
                external_ids.get(FloatingipMapper.OVN_FLOATINGIP_CREATE_TS)
            ),
            FloatingipMapper.REST_FLOATINGIP_UPDATED_AT: to_rest_timestamp(
                external_ids.get(FloatingipMapper.OVN_FLOATINGIP_UPDATE_TS)
            ),
        }

    @staticmethod
    def validate_add_rest_input(rest_data):
        if not rest_data.get(FloatingipMapper.REST_FLOATINGIP_NETWORK_ID):
            raise FloatingNetworkIdRequiredError()
        floating_ip_address = rest_data.get(
            FloatingipMapper.REST_FLOATINGIP_IP_ADDRESS
        )
        if floating_ip_address is not None and (
            ip_utils.get_ip_version(floating_ip_address) is None
        ):
            raise RestDataError(f'Invalid IP address: {floating_ip_address}')
        FloatingipMapper._validate_common(rest_data)

    @staticmethod
    def validate_update_rest_input(rest_data):
        FloatingipMapper._validate_common(rest_data)

    @staticmethod
    def _validate_common(rest_data):
        if rest_data.get(FloatingipMapper.REST_FLOATINGIP_FIXED_IP):
            raise RestDataError(
                'Selecting fixed_ip_address of a floating IP is not supported'
            )
        description = rest_data.get(
            FloatingipMapper.REST_FLOATINGIP_DESCRIPTION
        )
        if (
            description is not None
            and len(description) > ovnconst.FLOATING_IP_MAX_DESCRIPTION_LEN
        ):
            raise RestDataError(
                'Floating IP description must not be longer than '
                f'{ovnconst.FLOATING_IP_MAX_DESCRIPTION_LEN} characters'
            )
