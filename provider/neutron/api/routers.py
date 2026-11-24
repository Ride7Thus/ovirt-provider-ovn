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

import logging
import uuid
from netaddr import IPNetwork
from ovsdbapp.backend.ovs_idl.idlutils import RowNotFound
import constants as ovnconst
import neutron.ip as ip_utils
import neutron.validation as validate
from handlers.base_handler import BadRequestError
from handlers.base_handler import ConflictError
from handlers.base_handler import ElementNotFoundError
from neutron.mappers.routers import AddRouterInterfaceMapper
from neutron.mappers.networks import NetworkMapper
from neutron.mappers.routers import RemoveRouterInterfaceMapper
from neutron.mappers.routers import Router
from neutron.mappers.routers import RouterInterface
from neutron.mappers.routers import RouterMapper
from neutron.mappers.subnets import SubnetMapper
from ovirt_provider_config_common import gateway_chassis
from neutron.api.base import NeutronApiBase


# The resource APIs are mixins of NeutronApi and call each other through
# it, which pylint can not see.
# pylint: disable=no-member


class RoutersApi(NeutronApiBase):
    """Routers, their interfaces, external gateway and SNAT."""

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

    def _add_external_gateway_to_router(
        self, gateway_ip, gateway_subnet_id, network_id, router_id
    ):
        if network_id:
            self._add_external_gateway_interface(
                router_id, network_id, gateway_subnet_id, gateway_ip
            )
            subnet = self.ovn_north.get_dhcp(dhcp_id=gateway_subnet_id)
            self.ovn_north.add_route(
                lrp_id=router_id,
                prefix=ip_utils.get_default_route(subnet),
                nexthop=ip_utils.get_subnet_gateway(subnet),
            )

    def _validate_external_gateway(
        self, gateway_ip, gateway_subnet_id, network_id
    ):
        if network_id:
            self._validate_create_routing_lsp_by_subnet(
                network_id, gateway_subnet_id, is_external_gateway=True
            )
            validate.ip_available_in_network(
                self.ovn_north.get_ls(ls_id=network_id), gateway_ip
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

    def _is_gateway_unchanged(self, lr, gateway_subnet, gateway_ip):
        existing_gw_lsp_id = lr.external_ids.get(
            RouterMapper.OVN_ROUTER_GATEWAY_PORT
        )
        return bool(
            gateway_subnet
            and existing_gw_lsp_id
            and not self._is_updated_gw_different_than_existing(
                lr, gateway_subnet, gateway_ip, existing_gw_lsp_id
            )
        )

    def _is_updated_gw_different_than_existing(
        self, lr, new_gateway_subnet, new_gateway_ip, existing_lr_gw_lsp_id
    ):
        if not new_gateway_subnet:
            return False
        if not existing_lr_gw_lsp_id:
            return False

        # The gateway port id is the LSP name, not the OVSDB row uuid
        existing_lsp_name = str(existing_lr_gw_lsp_id)
        existing_lsp = self.ovn_north.get_lsp(lsp_id=existing_lsp_name)
        existing_subnet = self.ovn_north.get_dhcp(lsp_id=existing_lsp.uuid)
        existing_ip = ip_utils.get_port_ip(
            existing_lsp,
            self.ovn_north.get_lrp(lsp_id=existing_lsp_name),
        )

        return (
            new_gateway_subnet != str(existing_subnet.uuid)
            or new_gateway_ip != existing_ip
        )

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

    def _create_router_port_name(self, port_id):
        # LSP will reference this LRP by name (port parameter),
        # for convinience we will set the name to the id of the matching LSP
        # with an 'lrp' prefix.
        # We need the prefix due to an ovn issue in OVN lookup (bug pending)
        return ovnconst.ROUTER_PORT_NAME_PREFIX + str(port_id)

    def _get_subnet_gateway_router_id(self, subnet):
        return subnet.external_ids.get(SubnetMapper.OVN_GATEWAY_ROUTER_ID)

    def _set_subnet_gateway_router(self, subnet_id, router_id):
        self.ovn_north.db_set(
            ovnconst.TABLE_DHCP_Options,
            subnet_id,
            (
                ovnconst.ROW_DHCP_EXTERNAL_IDS,
                {SubnetMapper.OVN_GATEWAY_ROUTER_ID: router_id},
            ),
        )

    def _clear_subnet_gateway_router(self, subnet_id):
        self.ovn_north.remove_key_from_column(
            ovnconst.TABLE_DHCP_Options,
            subnet_id,
            ovnconst.ROW_DHCP_EXTERNAL_IDS,
            SubnetMapper.OVN_GATEWAY_ROUTER_ID,
        )

    def _validate_create_routing_lsp_by_subnet(
        self, network_id, subnet_id, router_id=None, is_external_gateway=False
    ):
        existing_subnet_for_network = self.ovn_north.get_dhcp(ls_id=network_id)
        existing_router_for_subnet = self._get_subnet_gateway_router_id(
            existing_subnet_for_network
        )
        validate.create_routing_lsp_by_subnet(
            network_id,
            subnet_id,
            existing_subnet_for_network,
            existing_router_for_subnet,
            router_id,
            is_external_gateway=is_external_gateway,
        )
        if router_id:
            router = self.ovn_north.get_lr(lr_id=router_id)
            self._validate_subnet_is_not_on_router(subnet_id, router_id)
            validate.unique_gateway_per_router(
                router,
                existing_subnet_for_network,
                self._get_router_gateways(router),
            )

    def _get_router_gateways(self, router):
        router_ports = (
            self.ovn_north.list_lrp(router_id=router.uuid) if router else []
        )
        return sum(
            [lrp[ovnconst.ROW_LRP_NETWORKS] for lrp in router_ports], []
        )

    def _create_routing_lsp_by_subnet(self, subnet_id, router_id):
        subnet = self.ovn_north.get_dhcp(dhcp_id=subnet_id)
        network_id = subnet.external_ids.get(SubnetMapper.OVN_NETWORK_ID)
        self._validate_create_routing_lsp_by_subnet(
            network_id, subnet_id, router_id
        )
        lrp_ip = self._get_ip_from_subnet(subnet, network_id, router_id)
        lsp_id = self._create_port(
            ovnconst.ROUTER_SWITCH_PORT_NAME,
            network_id,
        )
        lrp_name = self._create_router_port_name(lsp_id)
        self._connect_port_to_router(
            lsp_id,
            lrp_name,
            router_id,
            name=ovnconst.ROUTER_SWITCH_PORT_NAME,
            is_enabled=True,
        )
        self._set_subnet_gateway_router(subnet_id, router_id)
        return (
            str(lsp_id),
            lrp_name,
            lrp_ip,
            network_id,
            ip_utils.random_unique_mac(
                self.ovn_north.list_lsp(), self.ovn_north.list_lrp()
            ),
        )

    def _validate_subnet_is_not_on_router(self, subnet_id, router_id):
        if self._is_subnet_on_router(router_id, subnet_id):
            raise BadRequestError(
                'Bad router request: Router already has a port on subnet'
                ' {subnet}'.format(subnet=subnet_id)
            )

    def _update_routing_lsp_by_port(self, port_id, router_id):
        port = self.ovn_north.get_lsp(lsp_id=port_id)
        if port.type == ovnconst.LSP_TYPE_ROUTER:
            raise BadRequestError(
                'Can not add {port} to router. Port is already connected to a'
                ' router'.format(port=port_id)
            )
        subnet = self.ovn_north.get_dhcp(lsp_id=port.uuid)
        self._validate_subnet_is_not_on_router(subnet.uuid, router_id)

        lrp_ipmask = self._get_ip_netmask_for_lrp(port, router_id, subnet.cidr)
        lrp_name = self._create_router_port_name(port.name)
        mac = ip_utils.get_port_mac(port)
        self._connect_port_to_router(
            port.uuid, lrp_name, router_id, is_enabled=True
        )
        return (
            port_id,
            lrp_name,
            lrp_ipmask,
            str(self._get_port_network(port).uuid),
            mac,
        )

    def _get_ip_netmask_for_lrp(self, lsp, lr_id, ls_cidr):
        lsp_ip = ip_utils.get_port_ip(lsp)
        validate.port_ip_for_router(lsp_ip, lsp, lr_id)
        validate.port_added_to_lr_must_have_subnet(
            ls_cidr, str(lsp.uuid), lr_id
        )
        return ip_utils.get_ip_with_mask(ip=lsp_ip, cidr=ls_cidr)

    def _reserve_network_ip(self, network_id, gateway_ip):
        if not network_id:
            return
        exclude_values = self.ovn_north.get_ls(
            ls_id=network_id
        ).other_config.get(ovnconst.LS_OPTION_EXCLUDE_IPS, {})
        new_values = (
            (exclude_values + ' ') if exclude_values else str()
        ) + gateway_ip

        self.ovn_north.db_set(
            ovnconst.TABLE_LS,
            network_id,
            (
                ovnconst.ROW_LS_OTHER_CONFIG,
                {ovnconst.LS_OPTION_EXCLUDE_IPS: new_values},
            ),
        )

    def _release_network_ip(self, network_id, ip):
        exclude_values = self.ovn_north.get_ls(
            ls_id=network_id
        ).other_config.get(ovnconst.LS_OPTION_EXCLUDE_IPS, '')
        values = exclude_values.split()
        values.remove(ip)

        if values:
            self.ovn_north.db_set(
                ovnconst.TABLE_LS,
                network_id,
                (
                    ovnconst.ROW_LS_OTHER_CONFIG,
                    {ovnconst.LS_OPTION_EXCLUDE_IPS: ' '.join(values)},
                ),
            )
        else:
            self.ovn_north.remove_key_from_column(
                ovnconst.TABLE_LS,
                network_id,
                ovnconst.ROW_LS_OTHER_CONFIG,
                ovnconst.LS_OPTION_EXCLUDE_IPS,
            )

    def _add_external_gateway_interface(
        self, router_id, network_id, gateway_subnet_id, gateway_ip
    ):
        port_ip = '{ip}/{netmask}'.format(
            ip=gateway_ip,
            netmask=ip_utils.get_mask_from_subnet(
                self.ovn_north.get_dhcp(dhcp_id=gateway_subnet_id)
            ),
        )

        lsp_id = self._create_port(
            ovnconst.ROUTER_SWITCH_PORT_NAME,
            network_id,
        )
        lrp_name = self._create_router_port_name(lsp_id)
        mac = ip_utils.random_unique_mac(
            self.ovn_north.list_lsp(), self.ovn_north.list_lrp()
        )
        self.ovn_north.add_lrp(router_id, lrp_name, mac=mac, lrp_ip=port_ip)
        self._ensure_gateway_chassis(lrp_name)
        self._connect_port_to_router(
            lsp_id,
            lrp_name,
            router_id,
            name=ovnconst.ROUTER_SWITCH_PORT_NAME,
            is_enabled=True,
            is_external_gateway=True,
        )

        self.ovn_north.create_ovn_update_command(
            ovnconst.TABLE_LR, router_id
        ).add(
            ovnconst.ROW_LR_EXTERNAL_IDS,
            {
                RouterMapper.OVN_ROUTER_GATEWAY_PORT: str(lsp_id),
            },
        ).execute()

    @AddRouterInterfaceMapper.validate_update
    @AddRouterInterfaceMapper.map_from_rest
    @AddRouterInterfaceMapper.map_to_rest
    def add_router_interface(self, router_id, subnet_id=None, port_id=None):
        self._validate_router_exists(router_id)
        port_id, lrp_name, lrp_ip, network_id, mac = (
            self._create_routing_lsp_by_subnet(subnet_id, router_id)
            if subnet_id
            else self._update_routing_lsp_by_port(port_id, router_id)
        )
        subnet = (
            self.ovn_north.get_dhcp(dhcp_id=subnet_id)
            if subnet_id
            else self.ovn_north.get_dhcp(ls_id=network_id)
        )
        self.ovn_north.add_lrp(
            router_id,
            lrp_name,
            mac=mac,
            lrp_ip=lrp_ip,
            ipv6_ra_configs=self._get_ra_configs(subnet),
        )
        self._sync_router_snat(router_id)

        return RouterInterface(
            id=router_id,
            ls_id=network_id,
            lsp_id=port_id,
            dhcp_options_id=subnet_id or str(subnet.uuid),
        )

    def _get_ra_configs(self, subnet):
        network = self.ovn_north.get_ls(dhcp=subnet)
        return self._build_ra_config_dict(
            subnet, network.external_ids.get(NetworkMapper.OVN_MTU)
        )

    @staticmethod
    def _build_ra_config_dict(subnet, mtu=None):
        if not ip_utils.is_subnet_ipv6(subnet):
            return {}
        ra_options = {
            ovnconst.ROW_LRP_IPV6_ADDRESS_MODE: subnet.external_ids.get(
                SubnetMapper.OVN_IPV6_ADDRESS_MODE
            ),
            ovnconst.ROW_LRP_IPV6_SEND_PERIODIC: "true",
        }
        if mtu:
            ra_options[ovnconst.ROW_LRP_IPV6_MTU] = mtu
        return ra_options

    def _get_ip_from_subnet(self, subnet, network_id, router_id):
        validate.attach_network_to_router_by_subnet(
            subnet, network_id, router_id
        )
        subnet_gateway = ip_utils.get_subnet_gateway(subnet)
        subnet_netmask = ip_utils.get_mask_from_subnet(subnet)
        return f'{subnet_gateway}/{subnet_netmask}'

    def _get_ip_from_addresses(self, addresses):
        if not addresses:
            return None
        address_parts = addresses[0].split(' ')
        return address_parts[1] if len(address_parts) > 1 else None

    @RemoveRouterInterfaceMapper.validate_update
    @RemoveRouterInterfaceMapper.map_from_rest
    @RemoveRouterInterfaceMapper.map_to_rest
    def delete_router_interface(self, router_id, subnet_id=None, port_id=None):
        if subnet_id and port_id:
            result = self._delete_router_interface_by_subnet_and_port(
                router_id, subnet_id, port_id
            )
        elif subnet_id:
            result = self._delete_router_interface_by_subnet(
                router_id, subnet_id
            )
        else:
            result = self._delete_router_interface_by_port(
                router_id, port_id, sync_snat=False
            )
        self._sync_router_snat(router_id)
        return result

    def _delete_router_interface_by_port(
        self, router_id, port_id, sync_snat=True
    ):
        lsp = self.ovn_north.get_lsp(lsp_name=port_id)
        validate.port_is_connected_to_router(lsp)
        self._validate_interface_not_used_by_floatingips(router_id, lsp)

        subnet = self.ovn_north.get_dhcp(lsp_id=lsp.uuid)
        subnet_id = str(subnet.uuid)
        lrp = self.ovn_north.get_lrp(lsp_id=port_id)
        lrp_ip = ip_utils.get_ip_from_cidr(lrp.networks[0])
        lr = self.ovn_north.get_lr(lr_id=router_id)
        ls_id = str(self.ovn_north.get_ls(dhcp=subnet).uuid)

        is_subnet_gateway = (
            subnet
            and self._is_subnet_on_router(router_id, subnet_id)
            and lrp_ip == ip_utils.get_subnet_gateway(subnet)
        )
        self._delete_router_interface(router_id, port_id, lrp, lr)
        if is_subnet_gateway:
            self._clear_subnet_gateway_router(str(subnet.uuid))

        lr_gw_port = lr.external_ids.get(RouterMapper.OVN_ROUTER_GATEWAY_PORT)
        if port_id == lr_gw_port:
            self._remove_lr_gw_port(lr, ls_id, lrp_ip)
        if sync_snat:
            self._sync_router_snat(router_id)
        return RouterInterface(
            id=router_id,
            ls_id=ls_id,
            lsp_id=port_id,
            dhcp_options_id=subnet_id,
        )

    def _remove_lr_gw_port(self, lr, ls_id, lrp_ip):
        self.ovn_north.remove_key_from_column(
            ovnconst.TABLE_LR,
            str(lr.uuid),
            ovnconst.ROW_LR_EXTERNAL_IDS,
            RouterMapper.OVN_ROUTER_GATEWAY_PORT,
        )
        self.ovn_north.remove_static_route(lr, ovnconst.DEFAULT_ROUTE4)
        self.ovn_north.remove_static_route(lr, ovnconst.DEFAULT_ROUTE6)
        self._release_network_ip(ls_id, lrp_ip)

    def _is_subnet_on_router(self, router_id, subnet_id):
        lr = self.ovn_north.get_lr(lr_id=router_id)
        for lrp in lr.ports:
            lsp_id = self.ovn_north.get_lsp(lrp=lrp).uuid
            lrp_subnet = self.ovn_north.get_dhcp(lsp_id=lsp_id)
            if str(lrp_subnet.uuid) == subnet_id:
                return True
        return False

    def _delete_router_interface(self, router_id, port_id, lrp, lr):
        if lrp not in lr.ports:
            raise BadRequestError(
                'Port {port} is not connected to router {router}'.format(
                    port=port_id, router=router_id
                )
            )
        self.ovn_north.remove_lrp(lrp.uuid)
        self.ovn_north.remove_lsp(port_id)

    def _delete_router_interface_by_subnet_and_port(
        self, router_id, subnet_id, port_id
    ):
        subnet = self.ovn_north.get_dhcp(dhcp_id=subnet_id)
        network_id = subnet.external_ids[SubnetMapper.OVN_NETWORK_ID]
        network = self.ovn_north.get_ls(ls_id=network_id)
        lsp = self.ovn_north.get_lsp(lsp_id=port_id)
        validate.port_does_not_belong_to_subnet(lsp, network, subnet_id)
        return self._delete_router_interface_by_port(router_id, port_id)

    def _delete_router_interface_by_subnet(self, router_id, subnet_id):
        lr = self.ovn_north.get_lr(lr_id=router_id)
        subnet = self.ovn_north.get_dhcp(dhcp_id=subnet_id)
        network_id = subnet.external_ids[SubnetMapper.OVN_NETWORK_ID]
        network = self.ovn_north.get_ls(ls_id=network_id)
        lr_gw_port = lr.external_ids.get(RouterMapper.OVN_ROUTER_GATEWAY_PORT)
        deleted_lsp_id = None
        for lrp in lr.ports:
            lsp = self.ovn_north.get_lsp(lrp=lrp)
            if lsp in network.ports:
                self._validate_interface_not_used_by_floatingips(
                    router_id, lsp
                )
        for lrp in lr.ports:
            lsp_id = self.ovn_north.get_lsp(lrp=lrp).uuid
            lsp = self.ovn_north.get_lsp(lsp_id=lsp_id)
            if lsp in network.ports:
                deleted_lsp_id = lsp_id
                self._delete_router_interface(
                    router_id, lsp_id, lrp=lrp, lr=lr
                )
                if lsp_id == lr_gw_port:
                    self._remove_lr_gw_port(
                        lr,
                        network_id,
                        ip_utils.get_ip_from_cidr(lrp.networks[0]),
                    )
        subnet_gw_router_id = self._get_subnet_gateway_router_id(subnet)
        if subnet_gw_router_id == router_id:
            self._clear_subnet_gateway_router(str(subnet.uuid))

        if not deleted_lsp_id:
            raise BadRequestError(
                'Subnet {subnet_id} is not connected to router {router_id}'.format(  # noqa: E501
                    subnet_id=subnet_id, router_id=router_id
                )
            )
        return RouterInterface(
            id=router_id,
            ls_id=network_id,
            lsp_id=deleted_lsp_id,
            dhcp_options_id=subnet_id,
        )

    # Router gateway chassis and SNAT

    def _ensure_gateway_chassis(self, lrp_name):
        """
        Returns whether the router port is bound to a gateway chassis,
        binding it to the configured ones if needed.
        """
        lrp = self.ovn_north.get_lrp(lrp_name=lrp_name)
        if self.ovn_north.lrp_has_gateway_chassis(lrp):
            return True
        chassis = gateway_chassis()
        if not chassis:
            return False
        self.ovn_north.set_lrp_gateway_chassis(lrp_name, chassis)
        return True

    def _set_router_snat_flag(self, router_id, enable_snat):
        if enable_snat is None:
            return
        self.ovn_north.db_set(
            ovnconst.TABLE_LR,
            router_id,
            (
                ovnconst.ROW_LR_EXTERNAL_IDS,
                {
                    RouterMapper.OVN_ROUTER_ENABLE_SNAT: str(
                        bool(enable_snat)
                    ).lower()
                },
            ),
        )

    def _get_router_snat_rules(self, lr):
        """
        The SNAT rules the router should have: every IPv4 subnet attached to
        it is translated to the IPv4 address of its external gateway.
        """
        gw_lsp_id = lr.external_ids.get(RouterMapper.OVN_ROUTER_GATEWAY_PORT)
        if not gw_lsp_id or not RouterMapper.is_snat_enabled(lr):
            return set()
        gw_lrp = self.ovn_north.get_lrp(lsp_id=gw_lsp_id)
        if not gw_lrp or not gw_lrp.networks:
            return set()
        gw_ip = ip_utils.get_ip_from_cidr(gw_lrp.networks[0])
        if ip_utils.get_ip_version(gw_ip) != 'ip4':
            return set()
        return {
            (gw_ip, str(IPNetwork(network).cidr))
            for lrp in lr.ports
            if lrp.uuid != gw_lrp.uuid
            for network in lrp.networks
            if IPNetwork(network).version == SubnetMapper.IP_VERSION_4
        }

    def _sync_router_snat(self, router_id):
        lr = self.ovn_north.get_lr(lr_id=router_id)
        wanted = self._get_router_snat_rules(lr)
        if wanted:
            gw_lrp = self.ovn_north.get_lrp(
                lsp_id=lr.external_ids[RouterMapper.OVN_ROUTER_GATEWAY_PORT]
            )
            if not self._ensure_gateway_chassis(gw_lrp.name):
                logging.warning(
                    'Router %s has SNAT enabled, but its external gateway '
                    'port %s is not bound to a gateway chassis: set '
                    'ovn-gateway-chassis in the [NETWORK] configuration '
                    'section for SNAT to take effect',
                    router_id,
                    gw_lrp.name,
                )
        existing = {
            (nat.external_ip, str(IPNetwork(nat.logical_ip).cidr))
            for nat in lr.nat
            if nat.type == ovnconst.NAT_SNAT
        }
        if wanted == existing:
            return
        with self.tx_manager.transaction() as tx:
            for _, logical_ip in existing - wanted:
                self.ovn_north.remove_nat(
                    lr_id=router_id,
                    nat_type=ovnconst.NAT_SNAT,
                    match_ip=logical_ip,
                    transaction=tx,
                )
            for external_ip, logical_ip in wanted - existing:
                self.ovn_north.add_nat(
                    lr_id=router_id,
                    nat_type=ovnconst.NAT_SNAT,
                    external_ip=external_ip,
                    logical_ip=logical_ip,
                    transaction=tx,
                )
