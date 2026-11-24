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

import uuid
from ovsdbapp.backend.ovs_idl.idlutils import RowNotFound
import constants as ovnconst
import neutron.ip as ip_utils
import neutron.validation as validate
from handlers.base_handler import ConflictError
from handlers.base_handler import ElementNotFoundError
from neutron.mappers.routers import Router
from neutron.mappers.routers import RouterMapper
from neutron.api.base import NeutronApiBase


# The resource APIs are mixins of NeutronApi and call each other through
# it, which pylint can not see.
# pylint: disable=no-member


class RoutersApi(NeutronApiBase):
    """Routers."""

    @RouterMapper.map_to_rest
    def get_router(self, router_id):
        return self._get_router_from_lr(self.ovn_north.get_lr(lr_id=router_id))

    def _get_router_from_lr(self, lr):
        gw_port_id = lr.external_ids.get(RouterMapper.OVN_ROUTER_GATEWAY_PORT)
        if not gw_port_id:
            return Router(
                lr=lr,
                ext_gw_ls_id=None,
                ext_gw_dhcp_options_id=None,
                gw_ip=None,
            )
        gw_port = self.ovn_north.get_lsp(lsp_id=gw_port_id)
        ls = self._get_port_network(gw_port)
        ls_id = str(ls.uuid)

        dhcp_options = self.ovn_north.get_dhcp(ls_id=ls_id)
        lrp = self.ovn_north.get_lrp(lsp_id=gw_port_id)
        gw_ip = ip_utils.get_ip_from_cidr(lrp.networks[0])

        return Router(
            lr=lr,
            ext_gw_ls_id=ls_id,
            ext_gw_dhcp_options_id=str(dhcp_options.uuid),
            gw_ip=gw_ip,
        )

    @RouterMapper.map_to_rest
    def list_routers(self):
        return [
            self._get_router_from_lr(lr) for lr in self.ovn_north.list_lr()
        ]

    def _add_router(
        self,
        name,
        enabled,
        network_id=None,
        gateway_subnet_id=None,
        gateway_ip=None,
        routes=None,
        enable_snat=None,
    ):
        self._validate_external_gateway(
            gateway_ip, gateway_subnet_id, network_id
        )
        validate.no_default_gateway_in_routes(network_id is not None, routes)
        self._reserve_network_ip(network_id, gateway_ip)

        router = self.ovn_north.add_lr(name, enabled)
        router_id = str(router.uuid)

        self._add_external_gateway_to_router(
            gateway_ip, gateway_subnet_id, network_id, router_id
        )
        self._add_routes_to_router(router_id, routes)
        self._set_router_snat_flag(router_id, enable_snat)
        self._sync_router_snat(router_id)
        router = self.ovn_north.get_lr(lr_id=router_id)
        return Router(
            lr=router,
            ext_gw_ls_id=network_id,
            ext_gw_dhcp_options_id=gateway_subnet_id,
            gw_ip=gateway_ip,
        )

    def _add_routes_to_router(self, router_id, routes):
        if not routes:
            return
        for route in routes:
            self.ovn_north.add_route(
                lrp_id=router_id,
                prefix=route[RouterMapper.REST_ROUTER_DESTINATION],
                nexthop=route[RouterMapper.REST_ROUTER_NEXTHOP],
            )

    @RouterMapper.validate_add
    @RouterMapper.map_from_rest
    @RouterMapper.map_to_rest
    def add_router(
        self,
        name,
        enabled,
        network_id=None,
        gateway_subnet=None,
        gateway_ip=None,
        routes=None,
        enable_snat=None,
    ):
        return self._add_router(
            name,
            enabled,
            network_id,
            gateway_subnet,
            gateway_ip,
            routes,
            enable_snat=enable_snat,
        )

    @RouterMapper.validate_update
    @RouterMapper.map_from_rest
    def update_router(
        self,
        router_id,
        name,
        enabled,
        network_id=None,
        gateway_subnet=None,
        gateway_ip=None,
        routes=None,
        enable_snat=None,
    ):
        lr = self.ovn_north.get_lr(lr_id=router_id)
        if not self._is_gateway_unchanged(lr, gateway_subnet, gateway_ip):
            # Re-sending the current gateway (e.g. to toggle enable_snat)
            # must not fail on the gateway ip being in use by this router.
            self._validate_external_gateway(
                gateway_ip, gateway_subnet, network_id
            )

        if routes is not None:
            # NOTE: we only validate default route and external gateway being
            # both present for the rest difinition. We overwrite existing
            # external gateway if a new default route is specified in rest
            # request
            validate.no_default_gateway_in_routes(network_id, routes)

            added_routes, removed_routes = ip_utils.diff_routes(
                routes, lr.static_routes
            )

            for destination in removed_routes:
                self.ovn_north.remove_static_route(lr, destination)
            for destination in added_routes:
                self.ovn_north.add_route(
                    router_id, destination, added_routes[destination]
                )

        existing_gw_lsp_id = lr.external_ids.get(
            RouterMapper.OVN_ROUTER_GATEWAY_PORT
        )
        is_updated_gw_different_than_existing = (
            self._is_updated_gw_different_than_existing(
                lr,
                gateway_subnet,
                gateway_ip,
                uuid.UUID(existing_gw_lsp_id) if existing_gw_lsp_id else None,
            )
        )
        if is_updated_gw_different_than_existing:
            self._validate_gateway_change_keeps_floatingips(
                router_id, existing_gw_lsp_id, network_id
            )
            self._delete_router_interface_by_port(
                router_id, existing_gw_lsp_id, sync_snat=False
            )
        self._reserve_network_ip(network_id, gateway_ip)

        self.ovn_north.create_ovn_update_command(
            ovnconst.TABLE_LR, router_id
        ).add(ovnconst.ROW_LR_NAME, name, name).add(
            ovnconst.ROW_LR_ENABLED, enabled
        ).execute()

        should_external_gw_be_added = (
            is_updated_gw_different_than_existing
            or (gateway_subnet and not existing_gw_lsp_id)
        )

        if should_external_gw_be_added:
            self._add_external_gateway_to_router(
                gateway_ip, gateway_subnet, network_id, router_id
            )
        self._set_router_snat_flag(router_id, enable_snat)
        self._sync_router_snat(router_id)
        return self.get_router(router_id)

    def delete_router(self, router_id):
        lr = self.ovn_north.get_lr(lr_id=router_id)
        existing_gw_lsp_id = lr.external_ids.get(
            RouterMapper.OVN_ROUTER_GATEWAY_PORT
        )
        # Validate everything before touching the router, so a refused
        # request does not leave it half deleted.
        self._validate_router_has_no_floatingips(router_id)
        gw_lrp = (
            self.ovn_north.get_lrp(lsp_id=existing_gw_lsp_id)
            if existing_gw_lsp_id
            else None
        )
        interfaces = [
            lrp
            for lrp in lr.ports
            if gw_lrp is None or lrp.uuid != gw_lrp.uuid
        ]
        if interfaces:
            raise ConflictError(
                f'Router {router_id} still has interfaces attached, '
                'remove them first'
            )
        if existing_gw_lsp_id:
            self._delete_router_interface_by_port(
                router_id, existing_gw_lsp_id, sync_snat=False
            )

        validate.router_has_no_ports(self.ovn_north.get_lr(lr_id=router_id))
        self.ovn_north.remove_router(router_id)

    def _validate_router_exists(self, router_id):
        try:
            self.idl.lookup(ovnconst.TABLE_LR, router_id)
        except RowNotFound:
            raise ElementNotFoundError(
                'Router {router} does not exist'.format(router=router_id)
            )
