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
from netaddr import IPNetwork
import constants as ovnconst
import neutron.ip as ip_utils
import neutron.validation as validate
from neutron.mappers.routers import RouterMapper
from neutron.mappers.subnets import SubnetMapper
from ovirt_provider_config_common import gateway_chassis
from neutron.api.base import NeutronApiBase


# The resource APIs are mixins of NeutronApi and call each other through
# it, which pylint can not see.
# pylint: disable=no-member


class RouterGatewaysApi(NeutronApiBase):
    """Router external gateways, their gateway chassis and SNAT."""

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
