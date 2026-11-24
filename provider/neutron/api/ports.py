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
from handlers.base_handler import ConflictError
from neutron.mappers.networks import NetworkMapper
from neutron.mappers.ports import NetworkPort
from neutron.mappers.ports import PortMapper
from neutron.mappers.security_groups import SecurityGroupMapper
from neutron.mappers.subnets import SubnetMapper
from ovirt_provider_config_common import default_port_security_enabled
from ovirt_provider_config_common import ovs_version_29
from ovndb.ovn_north import optionally_use_transactions
from neutron.api.base import NeutronApiBase


# The resource APIs are mixins of NeutronApi and call each other through
# it, which pylint can not see.
# pylint: disable=no-member


class PortsApi(NeutronApiBase):
    """Ports (OVN logical switch ports)."""

    @PortMapper.map_to_rest
    def list_ports(self):
        return [
            self._get_network_port(lsp, ls)
            for ls in self.ovn_north.list_ls()
            for lsp in ls.ports
            if self._is_port_ovirt_controlled(lsp)
        ]

    @PortMapper.map_to_rest
    def get_port(self, port_id):
        return self._get_network_port(
            self.ovn_north.get_lsp(ovirt_lsp_id=port_id)
        )

    @PortMapper.map_to_rest
    def _serialize_port(self, port):
        return port

    def _get_network_port(self, lsp, ls=None):
        if ls is None:
            ls = self._get_port_network(lsp)
        dhcp_options = self._get_dhcp(lsp, ls)
        lrp_name = lsp.options.get(ovnconst.LSP_OPTION_ROUTER_PORT)
        lrp = self.ovn_north.get_lrp(lrp_name=lrp_name) if lrp_name else None
        return NetworkPort(lsp=lsp, ls=ls, dhcp_options=dhcp_options, lrp=lrp)

    def _get_dhcp(self, lsp, ls):
        dhcp_id = None
        if lsp.dhcpv4_options:
            dhcp_id = lsp.dhcpv4_options[0].uuid
        if lsp.dhcpv6_options:
            dhcp_id = lsp.dhcpv6_options[0].uuid

        if dhcp_id:
            return self.ovn_north.get_dhcp(dhcp_id=dhcp_id)
        else:
            return self.ovn_north.get_dhcp(ls_id=ls.uuid)

    @PortMapper.validate_add
    @PortMapper.map_from_rest
    def add_port(
        self,
        network_id,
        name,
        mac=None,
        is_enabled=None,
        device_id=None,
        device_owner=None,
        fixed_ips=None,
        binding_host=None,
        port_security=None,
        security_groups=None,
    ):
        with self.tx_manager.transaction() as tx:
            port_id = self._create_port(name, network_id, transaction=tx)
            self._update_port_values(
                port_id,
                name,
                is_enabled,
                device_id,
                device_owner,
                binding_host,
                transaction=tx,
            )
            mac = mac or ip_utils.random_unique_mac(
                self.ovn_north.list_lsp(), self.ovn_north.list_lrp()
            )
            tx.add(
                self.get_update_port_addr_command(
                    port_id,
                    network_id=network_id,
                    mac=mac,
                    fixed_ips=fixed_ips,
                ).build_command()
            )
            port_security = (
                port_security
                if port_security is not None
                else self._get_port_security_from_network(network_id)
            )

            if security_groups is None and port_security:
                security_groups = [SecurityGroupMapper.DEFAULT_PG_NAME]
            elif security_groups is None:
                security_groups = []

            self.update_port_security(tx, port_id, mac, port_security)
            self.ovn_north.add_security_groups_to_port(
                port_id, security_groups, tx
            )
            self._update_port_security_groups_command(
                port_id, security_groups, tx
            )
        port_data = self._get_network_port(
            self.ovn_north.get_lsp(ovirt_lsp_id=port_id)
        )
        return self._serialize_port(port_data)

    @PortMapper.validate_update
    @PortMapper.map_from_rest
    def update_port(
        self,
        port_id,
        network_id=None,
        name=None,
        mac=None,
        is_enabled=None,
        device_id=None,
        device_owner=None,
        fixed_ips=None,
        binding_host=None,
        port_security=None,
        security_groups=None,
    ):
        port = self.ovn_north.get_lsp(ovirt_lsp_id=port_id)
        network_id = self._get_validated_port_network_id(port, network_id)
        current_mac = ip_utils.get_port_mac(port)
        mac = mac or current_mac
        with self.tx_manager.transaction() as tx:
            self._update_port_values(
                port.uuid,
                name,
                is_enabled,
                device_id,
                device_owner,
                binding_host,
                transaction=tx,
            )
            # Rewriting the addresses without fixed_ips would turn a static
            # address into a dynamic one, so only do it when they change.
            if fixed_ips is not None or mac != current_mac:
                tx.add(
                    self.get_update_port_addr_command(
                        port.name,
                        network_id=network_id,
                        mac=mac,
                        fixed_ips=fixed_ips,
                        port_type=port.type,
                    ).build_command()
                )
            self.update_port_security(
                tx, port.name, mac, port_security, lsp=port
            )
            self._update_port_security_groups(
                port, security_groups, tx, port_security=port_security
            )
        return self.get_port(port_id)

    def _update_lsp_bound_lrp(self, port_id, fixed_ips):
        if not fixed_ips:
            return
        lrp = self.ovn_north.get_lrp(lsp_id=port_id)
        subnet = self.ovn_north.get_dhcp(lsp_id=port_id)
        validate.fixed_ip_matches_port_subnet(fixed_ips, subnet)
        validate.fixed_ips_require_stateful_dhcp(subnet, fixed_ips)

        new_lrp_ip = '{ip}/{netmask}'.format(
            ip=fixed_ips[0].get(PortMapper.REST_PORT_IP_ADDRESS),
            netmask=ip_utils.get_mask_from_subnet(subnet),
        )

        self.ovn_north.db_set(
            ovnconst.TABLE_LRP,
            str(lrp.uuid),
            (ovnconst.ROW_LRP_NETWORKS, new_lrp_ip),
        )

    @optionally_use_transactions
    def _update_port_values(
        self,
        port,
        name=None,
        is_enabled=None,
        device_id=None,
        device_owner=None,
        binding_host=None,
        transaction=None,
    ):
        return (
            self.ovn_north.create_ovn_update_command(ovnconst.TABLE_LSP, port)
            .add(
                ovnconst.ROW_LSP_EXTERNAL_IDS,
                {PortMapper.OVN_DEVICE_ID: device_id},
                device_id,
            )
            .add(
                ovnconst.ROW_LSP_EXTERNAL_IDS,
                {PortMapper.OVN_NIC_NAME: name},
                name,
            )
            .add(
                ovnconst.ROW_LSP_EXTERNAL_IDS,
                {PortMapper.OVN_DEVICE_OWNER: device_owner},
                device_owner,
            )
            .add(ovnconst.ROW_LSP_ENABLED, is_enabled, is_enabled)
            .add(
                ovnconst.ROW_LSP_OPTIONS,
                {PortMapper.OVN_REQUESTED_CHASSIS: binding_host},
                ovs_version_29() and binding_host,
            )
            .build_command()
        )

    def get_update_port_addr_command(
        self, port_id, network_id, mac=None, fixed_ips=None, port_type=None
    ):
        if port_type == ovnconst.LSP_TYPE_ROUTER:
            self._update_lsp_bound_lrp(port_id, fixed_ips)
            return
        subnet = self.ovn_north.get_dhcp(ls_id=network_id)
        validate.fixed_ip_matches_port_subnet(fixed_ips, subnet)
        validate.fixed_ips_require_stateful_dhcp(subnet, fixed_ips)
        db_set_command = self.ovn_north.create_ovn_update_command(
            ovnconst.TABLE_LSP, port_id
        )
        ip_version = int(
            subnet.external_ids.get(
                SubnetMapper.OVN_IP_VERSION, SubnetMapper.IP_VERSION_4
            )
            if subnet
            else SubnetMapper.IP_VERSION_4
        )
        if mac:
            if subnet:
                self.update_port_subnet(db_set_command, subnet, ip_version)
                mac += ' ' + self._get_port_addesses_suffix(
                    network_id, fixed_ips
                )
            else:
                db_set_command.add(ovnconst.ROW_LSP_DHCPV4_OPTIONS, [])
            db_set_command.add(ovnconst.ROW_LSP_ADDRESSES, [mac])
        return db_set_command

    @staticmethod
    def update_port_subnet(ovsdb_update_command, subnet, ip_version):
        options_type = (
            ovnconst.ROW_LSP_DHCPV4_OPTIONS
            if ip_version == SubnetMapper.IP_VERSION_4
            else ovnconst.ROW_LSP_DHCPV6_OPTIONS
        )
        ovsdb_update_command.add(options_type, subnet.uuid)

    def update_port_security(
        self, transaction, port_id, mac, port_security, lsp=None
    ):
        update_db_command = self.ovn_north.create_ovn_update_command(
            ovnconst.TABLE_LSP, port_id
        )
        if port_security is True:
            self.ovn_north.activate_default_security_group(
                port_id, transaction, update_port_association=lsp is None
            )
            update_db_command.add(ovnconst.ROW_LSP_PORT_SECURITY, [mac])
        elif port_security is False:
            update_db_command = self.deactivate_port_security(
                port_id,
                transaction,
                old_port_security=PortMapper.is_port_security_enabled(lsp=lsp),
            )
        cmd = update_db_command.build_command()
        if cmd:
            transaction.add(cmd)

    def _get_port_addesses_suffix(self, network_id, fixed_ips):
        if not fixed_ips:
            return ovnconst.LSP_ADDRESS_TYPE_DYNAMIC

        # Only one fixed ip is supported for now
        # OVN does allow multiple IP's, so support for multiple fixed ips
        # can be added
        # TODO: handle multiple fixed_ips
        fixed_ip = fixed_ips[0]
        ip = fixed_ip.get(PortMapper.REST_PORT_IP_ADDRESS)
        if not ip:
            return ovnconst.LSP_ADDRESS_TYPE_DYNAMIC
        validate.ip_available_in_network(
            self.ovn_north.get_ls(ls_id=network_id), ip
        )
        return ip

    def _connect_port_to_router(
        self,
        port,
        router_port_name,
        router_id,
        name=None,
        is_enabled=True,
        is_external_gateway=False,
    ):
        self._update_port_values(
            port=port,
            name=name,
            is_enabled=is_enabled,
            device_id=router_id,
            device_owner=(
                PortMapper.DEVICE_OWNER_ROUTER_GATEWAY
                if is_external_gateway
                else PortMapper.DEVICE_OWNER_ROUTER
            ),
        )

        self.ovn_north.create_ovn_update_command(ovnconst.TABLE_LSP, port).add(
            ovnconst.ROW_LSP_TYPE,
            ovnconst.LSP_TYPE_ROUTER,
        ).add(
            ovnconst.ROW_LSP_OPTIONS,
            {ovnconst.LSP_OPTION_ROUTER_PORT: router_port_name},
        ).add(
            ovnconst.ROW_LSP_ADDRESSES, [ovnconst.LSP_ADDRESS_TYPE_ROUTER]
        ).execute()

        self.ovn_north.clear_row_column(
            ovnconst.TABLE_LSP, port, ovnconst.ROW_LSP_DHCPV4_OPTIONS
        )

    def _get_validated_port_network_id(self, port, network_id):
        """
        Validates that the network_id proposed for the port is valid,
        or if no network_id is given, retrieves the port to which
        the port currently belongs.
        If network_id is not None, it has to match the network to which
        the port already belongs. Moving a port from one network to another
        is not supported
        :param port: the port to be checked
        :param network_id: the network_id received for the port, None if not
        specified
        :return: the port's network_id
        :raises ValueError if new network_id does not match the existing one
        """
        old_network_id = self._get_port_network(port).uuid
        if network_id and not str(old_network_id) == network_id:
            raise ValueError('Unable to change network of existing port')
        return network_id or old_network_id

    def _create_port(self, name, network_id, transaction=None):
        generated_id = str(uuid.uuid4())
        self.ovn_north.add_lsp(
            generated_id, name, network_id, transaction=transaction
        )
        return generated_id

    def _update_port_security_groups(
        self, port, security_groups, transaction, port_security=None
    ):
        if security_groups is not None:
            new_groups = set(security_groups)
        elif port_security is True:
            new_groups = {SecurityGroupMapper.DEFAULT_PG_NAME}
        else:
            return
        old_security_groups = port.external_ids.get(
            PortMapper.OVN_SECURITY_GROUPS, ''
        ).split()
        old_groups = set(old_security_groups)
        sec_groups_to_install = new_groups - old_groups
        sec_groups_to_delete = old_groups - new_groups

        self.ovn_north.add_security_groups_to_port(
            port.uuid, sec_groups_to_install, transaction
        )
        self.ovn_north.remove_security_groups_from_port(
            port.uuid, sec_groups_to_delete, transaction
        )
        self._update_port_security_groups_command(
            port.uuid, security_groups or sec_groups_to_install, transaction
        )

    def _update_port_security_groups_command(
        self, port_id, security_groups, transaction
    ):
        transaction.add(
            self.ovn_north.create_ovn_update_command(
                ovnconst.TABLE_LSP, port_id
            )
            .add(
                ovnconst.ROW_LSP_EXTERNAL_IDS,
                {PortMapper.OVN_SECURITY_GROUPS: ' '.join(security_groups)},
            )
            .build_command()
        )

    def update_port_mac(self, port_id, macaddress):
        pass

    def delete_port(self, port_id):
        lsp = self.ovn_north.get_lsp(lsp_id=port_id)
        validate.port_is_not_connected_to_router(lsp)
        if self._is_floating_ip_port(lsp):
            raise ConflictError(
                f'Port {port_id} belongs to a floating IP, '
                'delete the floating IP instead'
            )
        with self.tx_manager.transaction() as tx:
            self._disassociate_port_floatingips(str(lsp.name), tx)
            self.ovn_north.remove_lsp(port_id, transaction=tx)

    def deactivate_port_security(
        self, port_id, transaction, old_port_security
    ):
        if old_port_security:
            self.ovn_north.deactivate_dropall_security_group(
                port_id, transaction
            )
        return self.ovn_north.create_ovn_update_command(
            ovnconst.TABLE_LSP, port_id
        ).add(ovnconst.ROW_LSP_PORT_SECURITY, [])

    def _is_port_address_value_static(self, type):
        return (
            type == ovnconst.LSP_TYPE_ROUTER
            or type == ovnconst.LSP_TYPE_LOCALNET
        )

    def _get_port_security_from_network(self, network_id):
        network = self.ovn_north.get_ls(ls_id=network_id)
        return NetworkMapper._str2bool(
            str(
                network.external_ids.get(
                    NetworkMapper.OVN_NETWORK_PORT_SECURITY,
                    default_port_security_enabled(),
                )
            )
        )
