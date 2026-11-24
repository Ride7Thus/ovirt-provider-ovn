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
from ovirt_provider_config_common import tenant_id
from handlers.base_handler import MethodNotAllowedError
from neutron.mappers.base import Mapper
from neutron.mappers.base import RestDataError


Router = namedtuple(
    'Router', ['lr', 'ext_gw_ls_id', 'ext_gw_dhcp_options_id', 'gw_ip']
)


RouterInterface = namedtuple(
    'RouterInterface', ['id', 'ls_id', 'lsp_id', 'dhcp_options_id']
)


class RouterMapper(Mapper):
    REST_ROUTER_ID = 'id'
    REST_ROUTER_NAME = 'name'

    REST_ROUTER_ROUTES = 'routes'
    REST_ROUTER_ADMIN_STATE_UP = 'admin_state_up'
    REST_ROUTER_STATUS = 'status'

    REST_ROUTER_EXTERNAL_GATEWAY_INFO = 'external_gateway_info'
    REST_ROUTER_NETWORK_ID = 'network_id'
    REST_ROUTER_ENABLE_SNAT = 'enable_snat'

    REST_ROUTER_FIXED_IPS = 'external_fixed_ips'
    REST_ROUTER_IP_ADDRESS = 'ip_address'
    REST_ROUTER_SUBNET_ID = 'subnet_id'

    REST_ROUTER_DESTINATION = 'destination'
    REST_ROUTER_NEXTHOP = 'nexthop'

    OVN_ROUTER_GATEWAY_PORT = 'ovirt_gateway_port'
    OVN_ROUTER_ENABLE_SNAT = 'ovirt_enable_snat'

    ROUTER_STATUS_ACTIVE = 'ACTIVE'
    ROUTER_STATUS_INACTIVE = 'INACTIVE'

    @staticmethod
    def rest2row(wrapped_self, func, rest_data, router_id):
        name = rest_data.get(RouterMapper.REST_ROUTER_NAME)
        enabled = rest_data.get(RouterMapper.REST_ROUTER_ADMIN_STATE_UP, True)
        routes = rest_data.get(RouterMapper.REST_ROUTER_ROUTES)

        network, subnet, ip = RouterMapper._get_external_gateway_from_rest(
            rest_data
        )
        enable_snat = RouterMapper._get_enable_snat_from_rest(rest_data)

        if router_id:
            return func(
                wrapped_self,
                router_id=router_id,
                name=name,
                enabled=enabled,
                network_id=network,
                gateway_subnet=subnet,
                gateway_ip=ip,
                routes=routes,
                enable_snat=enable_snat,
            )
        else:
            return func(
                wrapped_self,
                name=name,
                enabled=enabled,
                network_id=network,
                gateway_subnet=subnet,
                gateway_ip=ip,
                routes=routes,
                enable_snat=enable_snat,
            )

    @staticmethod
    def _get_enable_snat_from_rest(rest_data):
        """
        As in neutron, SNAT defaults to enabled when an external gateway is
        given. None means the request does not touch the external gateway.
        """
        gateway_info = rest_data.get(
            RouterMapper.REST_ROUTER_EXTERNAL_GATEWAY_INFO
        )
        if not gateway_info:
            return None
        return bool(
            gateway_info.get(RouterMapper.REST_ROUTER_ENABLE_SNAT, True)
        )

    @staticmethod
    def is_snat_enabled(lr):
        return (
            lr.external_ids.get(RouterMapper.OVN_ROUTER_ENABLE_SNAT, 'false')
            == 'true'
        )

    @staticmethod
    def _get_external_gateway_from_rest(rest_data):
        gateway_info = rest_data.get(
            RouterMapper.REST_ROUTER_EXTERNAL_GATEWAY_INFO, {}
        )
        if not gateway_info:
            return None, None, None
        network_id = gateway_info.get(RouterMapper.REST_ROUTER_NETWORK_ID)
        fixed_ips = gateway_info.get(RouterMapper.REST_ROUTER_FIXED_IPS)
        fixed_ip = fixed_ips[0]
        gateway_subnet = fixed_ip.get(RouterMapper.REST_ROUTER_SUBNET_ID)
        gateway_ip = fixed_ip.get(RouterMapper.REST_ROUTER_IP_ADDRESS)
        return network_id, gateway_subnet, gateway_ip

    @staticmethod
    def row2rest(router):
        if not router:
            return {}
        row = router.lr
        result = {
            RouterMapper.REST_ROUTER_ID: str(row.uuid),
            RouterMapper.REST_ROUTER_NAME: row.name,
            RouterMapper.REST_ROUTER_ADMIN_STATE_UP: (
                row.enabled[0] if row.enabled else True
            ),
            RouterMapper.REST_ROUTER_STATUS: (
                RouterMapper.ROUTER_STATUS_ACTIVE
                if row.enabled
                else RouterMapper.ROUTER_STATUS_INACTIVE
            ),
            RouterMapper.REST_TENANT_ID: tenant_id(),
            RouterMapper.REST_ROUTER_EXTERNAL_GATEWAY_INFO: RouterMapper._get_external_gateway_from_row(  # noqa: E501
                router
            ),
            RouterMapper.REST_ROUTER_ROUTES: RouterMapper._get_routes_from_row(
                row.static_routes
            ),
        }

        return result

    @staticmethod
    def _get_routes_from_row(routes):
        return [
            {
                RouterMapper.REST_ROUTER_DESTINATION: route.ip_prefix,
                RouterMapper.REST_ROUTER_NEXTHOP: route.nexthop,
            }
            for route in routes
        ]

    @staticmethod
    def _get_external_gateway_from_row(router):
        if not router.ext_gw_ls_id:
            return None
        return {
            RouterMapper.REST_ROUTER_NETWORK_ID: router.ext_gw_ls_id,
            RouterMapper.REST_ROUTER_ENABLE_SNAT: RouterMapper.is_snat_enabled(
                router.lr
            ),
            RouterMapper.REST_ROUTER_FIXED_IPS: [
                {
                    RouterMapper.REST_ROUTER_SUBNET_ID: router.ext_gw_dhcp_options_id,  # noqa: E501
                    RouterMapper.REST_ROUTER_IP_ADDRESS: router.gw_ip,
                }
            ],
        }

    @staticmethod
    def validate_add_rest_input(rest_data):
        RouterMapper._validate_external_gateway_info(rest_data)

    @staticmethod
    def validate_update_rest_input(rest_data):
        RouterMapper._validate_external_gateway_info(rest_data)

    @staticmethod
    def _validate_external_gateway_info(rest_data):
        gateway_info = rest_data.get(
            RouterMapper.REST_ROUTER_EXTERNAL_GATEWAY_INFO, {}
        )
        if gateway_info:
            message = '{key} missing in the external gateway information.'
            if RouterMapper.REST_ROUTER_NETWORK_ID not in gateway_info:
                raise RestDataError(
                    message.format(key=RouterMapper.REST_ROUTER_NETWORK_ID)
                )
            if RouterMapper.REST_ROUTER_FIXED_IPS not in gateway_info:
                raise RestDataError(
                    message.format(key=RouterMapper.REST_ROUTER_FIXED_IPS)
                )
            fixed_ips = gateway_info.get(RouterMapper.REST_ROUTER_FIXED_IPS)
            if not fixed_ips or len(fixed_ips) > 1:
                raise RestDataError(
                    '{key} must have exactly one element'.format(
                        key=RouterMapper.REST_ROUTER_FIXED_IPS
                    )
                )
            if RouterMapper.REST_ROUTER_SUBNET_ID not in fixed_ips[0]:
                raise RestDataError(
                    message.format(key=RouterMapper.REST_ROUTER_SUBNET_ID)
                )
            if RouterMapper.REST_ROUTER_IP_ADDRESS not in fixed_ips[0]:
                raise RestDataError(
                    message.format(key=RouterMapper.REST_ROUTER_IP_ADDRESS)
                )
            enable_snat = gateway_info.get(
                RouterMapper.REST_ROUTER_ENABLE_SNAT, True
            )
            if not isinstance(enable_snat, bool):
                raise RestDataError(
                    '{key} must be a boolean'.format(
                        key=RouterMapper.REST_ROUTER_ENABLE_SNAT
                    )
                )
        routes = rest_data.get(RouterMapper.REST_ROUTER_ROUTES)
        if routes:
            for route in routes:
                has_required_fields = (
                    type(route) is dict
                    and route.get(RouterMapper.REST_ROUTER_NEXTHOP) is not None
                    and route.get(RouterMapper.REST_ROUTER_DESTINATION)
                    is not None
                )
                if not has_required_fields:
                    raise RestDataError(
                        'Static route must have {destination} and {nexthop} '
                        'specified.'.format(
                            destination=RouterMapper.REST_ROUTER_DESTINATION,
                            nexthop=RouterMapper.REST_ROUTER_NEXTHOP,
                        )
                    )


class BaseRouterInterfaceMapper(Mapper):
    REST_ROUTERINTERFACE_ID = 'id'
    REST_ROUTERINTERFACE_SUBNET_ID = 'subnet_id'
    REST_ROUTERINTERFACE_PORT_ID = 'port_id'
    REST_ROUTERINTERFACE_SUBNET_IDS = 'subnet_ids'
    REST_ROUTERINTERFACE_NETWORK_ID = 'network_id'

    @staticmethod
    def rest2row(wrapped_self, func, rest_data, router_id):
        subnet = rest_data.get(
            BaseRouterInterfaceMapper.REST_ROUTERINTERFACE_SUBNET_ID
        )
        port = rest_data.get(
            BaseRouterInterfaceMapper.REST_ROUTERINTERFACE_PORT_ID
        )
        return func(
            wrapped_self, router_id=router_id, subnet_id=subnet, port_id=port
        )

    @staticmethod
    def row2rest(row):
        if not row:
            return {}

        return {
            AddRouterInterfaceMapper.REST_ROUTERINTERFACE_ID: row.id,
            AddRouterInterfaceMapper.REST_ROUTERINTERFACE_NETWORK_ID: row.ls_id,  # noqa: E501
            AddRouterInterfaceMapper.REST_ROUTERINTERFACE_PORT_ID: row.lsp_id,
            AddRouterInterfaceMapper.REST_ROUTERINTERFACE_SUBNET_ID: row.dhcp_options_id,  # noqa: E501
            AddRouterInterfaceMapper.REST_ROUTERINTERFACE_SUBNET_IDS: [
                row.dhcp_options_id
            ],
            AddRouterInterfaceMapper.REST_TENANT_ID: tenant_id(),
        }

    @staticmethod
    def validate_add_rest_input(rest_data):
        raise MethodNotAllowedError(
            'add_router_interface POST requests are not supported'
        )

    @staticmethod
    def _validate_update(rest_data):
        subnet = rest_data.get(
            BaseRouterInterfaceMapper.REST_ROUTERINTERFACE_SUBNET_ID
        )
        port = rest_data.get(
            BaseRouterInterfaceMapper.REST_ROUTERINTERFACE_PORT_ID
        )
        if not subnet and not port:
            raise RestDataError(
                'Either {} or {} must be specified.'.format(
                    BaseRouterInterfaceMapper.REST_ROUTERINTERFACE_SUBNET_ID,
                    BaseRouterInterfaceMapper.REST_ROUTERINTERFACE_PORT_ID,
                )
            )
        return subnet, port


class AddRouterInterfaceMapper(BaseRouterInterfaceMapper):
    @staticmethod
    def validate_update_rest_input(rest_data):
        subnet, port = BaseRouterInterfaceMapper._validate_update(rest_data)
        if subnet and port:
            raise RestDataError(
                'Subnet and port can not both be set at the same time'
            )


class RemoveRouterInterfaceMapper(BaseRouterInterfaceMapper):
    @staticmethod
    def validate_update_rest_input(rest_data):
        BaseRouterInterfaceMapper._validate_update(rest_data)
