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
import constants as ovnconst
import neutron.ip as ip_utils
import neutron.validation as validate
from neutron.mappers.networks import NetworkMapper
from neutron.mappers.networks import Network
from neutron.mappers.base import RestDataError
from neutron.mappers.subnets import SubnetMapper
from ovirt_provider_config_common import default_port_security_enabled
from neutron.api.base import NeutronApiBase


# The resource APIs are mixins of NeutronApi and call each other through
# it, which pylint can not see.
# pylint: disable=no-member


class NetworksApi(NeutronApiBase):
    """Networks (OVN logical switches)."""

    @NetworkMapper.map_to_rest
    def list_networks(self):
        ls_rows = self.ovn_north.list_ls()
        return [self._get_network(ls) for ls in ls_rows]

    def _get_network(self, ls):
        return Network(ls=ls, localnet_lsp=self._get_localnet_lsp(ls))

    @NetworkMapper.map_to_rest
    def get_network(self, network_id):
        return self._get_network(self.ovn_north.get_ls(ls_id=network_id))

    @NetworkMapper.validate_add
    @NetworkMapper.map_from_rest
    @NetworkMapper.map_to_rest
    def add_network(
        self,
        name,
        localnet=None,
        vlan=None,
        mtu=None,
        port_security_enabled=None,
    ):
        with self.tx_manager.transaction() as tx:
            if localnet:
                network_id = self._add_localnet_network(
                    name,
                    localnet,
                    vlan,
                    mtu,
                    port_security_enabled,
                    transaction=tx,
                )
            else:
                network_id = self._create_network(
                    name, tx, mtu, port_security_enabled
                )
        return self._get_network(self.ovn_north.get_ls(ls_id=network_id))

    def _create_network(self, name, transaction, mtu=None, port_security=None):
        external_ids_dict = {NetworkMapper.OVN_NETWORK_NAME: name}
        if mtu is not None:
            external_ids_dict[NetworkMapper.OVN_MTU] = str(mtu)
        external_ids_dict[NetworkMapper.OVN_NETWORK_PORT_SECURITY] = str(
            port_security
            if port_security is not None
            else default_port_security_enabled()
        )
        name = u'ovirt-{name}-{gen_id}'.format(name=name, gen_id=uuid.uuid4())
        transaction.add(
            self.ovn_north.add_ls(
                name=name,
                external_ids=self._generate_external_ids(
                    {}, **external_ids_dict
                ),
            )
        )
        return name

    @staticmethod
    def _generate_external_ids(current_external_ids, **kwargs):
        return dict(current_external_ids, **kwargs)

    def _add_localnet_network(
        self, name, localnet, vlan, mtu, port_security_enabled, transaction
    ):
        network_uuid = self._create_network(
            name, transaction, mtu, port_security_enabled
        )
        lsp_id = self._create_port(
            ovnconst.LOCALNET_SWITCH_PORT_NAME,
            network_uuid,
            transaction=transaction,
        )
        transaction.add(self._set_port_localnet_values(lsp_id, localnet, vlan))
        return network_uuid

    @NetworkMapper.validate_update
    @NetworkMapper.map_from_rest
    def update_network(
        self,
        network_id,
        name,
        localnet=None,
        vlan=None,
        mtu=None,
        port_security_enabled=None,
    ):
        with self.tx_manager.transaction() as tx:
            self._update_network_data(
                network_id, name, mtu, port_security_enabled, tx
            )
            self._update_localnet_on_network(network_id, localnet, vlan, tx)
        return self.get_network(network_id)

    def _update_network_data(
        self, network_id, name, mtu, port_security, transaction
    ):
        current_external_ids = self.ovn_north.get_ls(
            ls_id=network_id
        ).external_ids

        relevant_external_ids = {
            NetworkMapper.OVN_NETWORK_NAME: name
            or current_external_ids[NetworkMapper.OVN_NETWORK_NAME]
        }
        if mtu is not None:
            relevant_external_ids[NetworkMapper.OVN_MTU] = str(mtu)
        if port_security is not None:
            relevant_external_ids[NetworkMapper.OVN_NETWORK_PORT_SECURITY] = (
                str(port_security)
            )
        new_external_ids = self._generate_external_ids(
            current_external_ids, **relevant_external_ids
        )
        transaction.add(
            self.ovn_north.create_ovn_update_command(
                ovnconst.TABLE_LS, network_id
            )
            .add(ovnconst.ROW_LS_EXTERNAL_IDS, new_external_ids)
            .build_command()
        )
        if mtu:
            self._update_networks_mtu(network_id, mtu, transaction)

    def _update_localnet_on_network(
        self, network_id, localnet, vlan, transaction
    ):
        network = self.ovn_north.get_ls(ls_id=network_id)
        localnet_port = self._get_localnet_lsp(network)
        if localnet:
            if not localnet_port:
                lsp_id = self._create_port(
                    ovnconst.LOCALNET_SWITCH_PORT_NAME,
                    str(network.uuid),
                    transaction=transaction,
                )
            else:
                lsp_id = localnet_port.name
            transaction.add(
                self._set_port_localnet_values(lsp_id, localnet, vlan)
            )
        elif localnet_port:
            self.ovn_north.remove_lsp(
                str(localnet_port.uuid), transaction=transaction
            )

    def _set_port_localnet_values(self, port_id, localnet, vlan):
        return (
            self.ovn_north.create_ovn_update_command(
                ovnconst.TABLE_LSP, port_id
            )
            .add(
                ovnconst.ROW_LSP_ADDRESSES, [ovnconst.LSP_ADDRESS_TYPE_UNKNOWN]
            )
            .add(
                ovnconst.ROW_LSP_OPTIONS,
                {ovnconst.LSP_OPTION_NETWORK_NAME: localnet},
            )
            .add(ovnconst.ROW_LSP_TYPE, ovnconst.LSP_TYPE_LOCALNET)
            .add(ovnconst.ROW_LSP_TAG, vlan)
            .build_command()
        )

    def _update_networks_mtu(self, network_id, mtu, transaction=None):
        subnet = self.ovn_north.get_dhcp(ls_id=network_id)
        old_mtu = self._get_subnet_mtu(subnet)
        if subnet and old_mtu != mtu:
            transaction.add(
                self.ovn_north.create_ovn_update_command(
                    ovnconst.TABLE_DHCP_Options, subnet.uuid
                )
                .add(
                    (
                        ovnconst.ROW_DHCP_OPTIONS
                        if ip_utils.is_subnet_ipv4(subnet)
                        else ovnconst.ROW_DHCP_EXTERNAL_IDS
                    ),
                    {SubnetMapper.OVN_DHCP_MTU: str(mtu)},
                )
                .build_command()
            )
            if ip_utils.is_subnet_ipv6(subnet):
                self._update_ipv6_subnet_lrp_mtu(subnet, str(mtu), transaction)

    @staticmethod
    def _get_subnet_mtu(subnet):
        return (
            (
                subnet.options.get(NetworkMapper.REST_MTU)
                if ip_utils.is_subnet_ipv4(subnet)
                else subnet.external_ids.get(SubnetMapper.OVN_DHCP_MTU)
            )
            if subnet
            else None
        )

    def _update_ipv6_subnet_lrp_mtu(self, subnet, mtu, transaction):
        impacted_lrp = self.ovn_north.get_lrp_by_subnet(subnet)
        if impacted_lrp:
            transaction.add(
                self._update_ipv6_lrp_mtu(impacted_lrp, subnet, mtu)
            )

    def _update_ipv6_lrp_mtu(self, router_port, subnet, mtu):
        return (
            self.ovn_north.create_ovn_update_command(
                ovnconst.TABLE_LRP, self.ovn_north.get_lrp_id(router_port)
            )
            .add(
                ovnconst.ROW_LRP_IPV6_RA_CONFIGS,
                self._build_ra_config_dict(subnet, mtu),
            )
            .build_command()
        )

    def delete_network(self, network_id):
        network = self.ovn_north.get_ls(ls_id=network_id)
        if not network:
            raise RestDataError('Network %s does not exist' % network_id)
        validate.network_has_no_ports(
            network_id, network.ports, self._get_localnet_lsp(network)
        )

        with self.tx_manager.transaction() as tx:
            subnets = self.ovn_north.list_dhcp()
            for subnet in subnets:
                subnet_network_id = subnet.external_ids.get('ovirt_network_id')
                if subnet_network_id:
                    if network_id == subnet_network_id:
                        self.ovn_north.remove_dhcp_options(
                            subnet.uuid, transacion=tx
                        )
            tx.add(self.ovn_north.remove_ls(ls_id=network_id))

    def _get_localnet_lsp(self, ls):
        for lsp in ls.ports:
            if lsp.type == ovnconst.LSP_TYPE_LOCALNET:
                return lsp
        return None
