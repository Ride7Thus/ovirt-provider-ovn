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

import threading
import uuid
from collections import namedtuple
from datetime import datetime
from netaddr import IPAddress
from netaddr import IPNetwork
import constants as ovnconst
import neutron.ip as ip_utils
from handlers.base_handler import BadRequestError
from handlers.base_handler import ConflictError
from handlers.base_handler import ElementNotFoundError
from neutron.mappers.ports import PortMapper
from neutron.mappers.routers import RouterMapper
from neutron.mappers.subnets import SubnetMapper
from neutron.mappers.floating_ips import FloatingipMapper
from neutron.mappers.floating_ips import FloatingIP
from neutron.api.base import NeutronApiBase


# The resource APIs are mixins of NeutronApi and call each other through
# it, which pylint can not see.
# pylint: disable=no-member


def _utc_timestamp():
    return datetime.utcnow().isoformat()


FloatingIpTarget = namedtuple(
    'FloatingIpTarget', ['port_id', 'router_id', 'logical_ip']
)


_floatingip_allocation_lock = threading.Lock()


class FloatingIpsApi(NeutronApiBase):
    """Floating IPs."""

    def _list_router_floatingip_lsps(self, router_id):
        return [
            lsp
            for lsp in self._list_floatingip_lsps()
            if lsp.external_ids.get(FloatingipMapper.OVN_FLOATINGIP_ROUTER_ID)
            == str(router_id)
        ]

    def _validate_router_has_no_floatingips(self, router_id):
        floatingips = self._list_router_floatingip_lsps(router_id)
        if floatingips:
            raise ConflictError(
                f'Router {router_id} is used by floating IPs '
                f'{", ".join(sorted(lsp.name for lsp in floatingips))}'
            )

    def _validate_gateway_change_keeps_floatingips(
        self, router_id, existing_gw_lsp_id, new_network_id
    ):
        existing_network_id = str(
            self._get_port_network(
                self.ovn_north.get_lsp(lsp_id=existing_gw_lsp_id)
            ).uuid
        )
        if new_network_id != existing_network_id:
            self._validate_router_has_no_floatingips(router_id)

    def _get_floatingip_port_network_id(self, floatingip_lsp):
        port_id = floatingip_lsp.external_ids.get(
            FloatingipMapper.OVN_FLOATINGIP_PORT_ID
        )
        try:
            port = self.ovn_north.get_lsp(lsp_id=port_id)
        except ElementNotFoundError:
            return None
        return str(self._get_port_network(port).uuid)

    def _validate_interface_not_used_by_floatingips(self, router_id, lsp):
        lr = self.ovn_north.get_lr(lr_id=router_id)
        gw_lsp_id = lr.external_ids.get(RouterMapper.OVN_ROUTER_GATEWAY_PORT)
        floatingips = self._list_router_floatingip_lsps(router_id)
        if str(lsp.name) != str(gw_lsp_id):
            network_id = str(self._get_port_network(lsp).uuid)
            floatingips = [
                fip
                for fip in floatingips
                if self._get_floatingip_port_network_id(fip) == network_id
            ]
        if floatingips:
            raise ConflictError(
                f'Router interface {lsp.name} is required by floating IPs '
                f'{", ".join(sorted(fip.name for fip in floatingips))}'
            )

    # Floating IPs
    #
    # A floating IP is stored as an (unbound) logical switch port on the
    # external network, holding the floating address statically. When it is
    # associated with a port, a dnat_and_snat NAT entry is added to the router
    # that connects the port's subnet to the floating IP network.

    def _is_floating_ip_port(self, port_row):
        return (
            port_row.external_ids.get(FloatingipMapper.OVN_FLOATINGIP_MARKER)
            == 'true'
        )

    def _list_floatingip_lsps(self):
        return [
            lsp
            for ls in self.ovn_north.list_ls()
            for lsp in ls.ports
            if self._is_floating_ip_port(lsp)
        ]

    def _get_floatingip_lsp(self, floatingip_id):
        try:
            lsp = self.ovn_north.get_lsp(lsp_id=floatingip_id)
        except (ElementNotFoundError, BadRequestError):
            lsp = None
        if lsp is None or not self._is_floating_ip_port(lsp):
            raise ElementNotFoundError(
                f'Floating IP {floatingip_id} does not exist'
            )
        return lsp

    def _get_floatingip(self, lsp):
        floatingip_port = None
        port_id = lsp.external_ids.get(FloatingipMapper.OVN_FLOATINGIP_PORT_ID)
        if port_id:
            try:
                floatingip_port = self._get_network_port(
                    self.ovn_north.get_lsp(lsp_id=port_id)
                )
            except ElementNotFoundError:
                floatingip_port = None
        ls = self._get_port_network(lsp)
        return FloatingIP(
            floatingip=lsp,
            floatingip_network=ls,
            floatingip_subnet=self._get_dhcp(lsp, ls),
            floatingip_port=floatingip_port,
        )

    @FloatingipMapper.map_to_rest
    def list_floatingips(self):
        return [
            self._get_floatingip(lsp) for lsp in self._list_floatingip_lsps()
        ]

    @FloatingipMapper.map_to_rest
    def get_floatingip(self, floatingip_id):
        return self._get_floatingip(self._get_floatingip_lsp(floatingip_id))

    def _get_floatingip_subnet(self, network_id):
        subnet = self.ovn_north.get_dhcp(ls_id=network_id)
        if subnet is None:
            raise BadRequestError(
                f'Network {network_id} has no subnet to allocate floating IPs'
            )
        if IPNetwork(subnet.cidr).version != SubnetMapper.IP_VERSION_4:
            raise BadRequestError('Floating IPs require an IPv4 subnet')
        return subnet

    @staticmethod
    def _is_host_address(address, cidr):
        if address not in cidr:
            return False
        if cidr.size <= 2:
            # /31 and /32 have no network and broadcast addresses
            return True
        return address not in (cidr.network, cidr.broadcast)

    def _allocate_floating_ip_address(self, network, subnet, requested_ip):
        cidr = IPNetwork(subnet.cidr)
        unavailable = ip_utils.get_network_used_ips(network)
        gateway = subnet.options.get(SubnetMapper.OVN_GATEWAY)
        if gateway:
            unavailable.add(gateway)
        exclude_ranges = ip_utils.get_network_exclude_ranges(network)

        def is_free(address):
            return str(address) not in unavailable and not (
                ip_utils.is_ip_in_ranges(address, exclude_ranges)
            )

        if requested_ip is not None:
            address = IPAddress(requested_ip)
            if not self._is_host_address(address, cidr):
                raise BadRequestError(
                    f'{requested_ip} is not a valid host address of {cidr}'
                )
            if not is_free(address):
                raise ConflictError(
                    f'IP address {requested_ip} is already allocated '
                    f'in network {network.uuid}'
                )
            return str(address)

        for address in cidr.iter_hosts():
            if is_free(address):
                return str(address)
        raise ConflictError(f'No free IP addresses in network {network.uuid}')

    def _get_floatingip_target(
        self, floatingip_network_id, port_id, floatingip_id=None
    ):
        """
        Validates that port_id can be associated with a floating IP on
        floatingip_network_id and returns where the NAT entry has to go.
        """
        port = self.ovn_north.get_lsp(lsp_id=port_id)
        if (
            not self._is_port_ovirt_controlled(port)
            or self._is_floating_ip_port(port)
            or port.type == ovnconst.LSP_TYPE_ROUTER
        ):
            raise BadRequestError(
                f'Port {port_id} can not be associated with a floating IP'
            )
        port_ip = ip_utils.get_port_ip(port)
        if port_ip is None or ip_utils.get_ip_version(port_ip) != 'ip4':
            raise BadRequestError(f'Port {port_id} has no IPv4 address')

        subnet = self._get_dhcp(port, self._get_port_network(port))
        router_id = (
            self._get_subnet_gateway_router_id(subnet) if subnet else None
        )
        if not router_id:
            raise BadRequestError(
                f'Subnet of port {port_id} is not connected to a router'
            )
        lr = self.ovn_north.get_lr(lr_id=router_id)
        gw_port_id = lr.external_ids.get(RouterMapper.OVN_ROUTER_GATEWAY_PORT)
        gw_network_id = (
            str(
                self._get_port_network(
                    self.ovn_north.get_lsp(lsp_id=gw_port_id)
                ).uuid
            )
            if gw_port_id
            else None
        )
        if gw_network_id != str(floatingip_network_id):
            raise BadRequestError(
                f'Router {router_id} has no external gateway on '
                f'floating IP network {floatingip_network_id}'
            )
        gw_lrp = self.ovn_north.get_lrp(lsp_id=gw_port_id)
        if not self._ensure_gateway_chassis(gw_lrp.name):
            raise BadRequestError(
                f'The external gateway of router {router_id} is not bound '
                'to a gateway chassis. Set ovn-gateway-chassis in the '
                '[NETWORK] section of the provider configuration'
            )

        for other in self._list_floatingip_lsps():
            if other.name != floatingip_id and other.external_ids.get(
                FloatingipMapper.OVN_FLOATINGIP_PORT_ID
            ) == str(port.name):
                raise ConflictError(
                    f'Port {port_id} already has floating IP {other.name}'
                )

        return FloatingIpTarget(
            port_id=str(port.name), router_id=str(lr.uuid), logical_ip=port_ip
        )

    def _add_floatingip_nat(self, floatingip_ip, target, transaction):
        self.ovn_north.add_nat(
            lr_id=target.router_id,
            nat_type=ovnconst.NAT_BOTH,
            external_ip=floatingip_ip,
            logical_ip=target.logical_ip,
            transaction=transaction,
        )

    def _remove_floatingip_nat(self, floatingip_lsp, transaction):
        router_id = floatingip_lsp.external_ids.get(
            FloatingipMapper.OVN_FLOATINGIP_ROUTER_ID
        )
        floatingip_ip = ip_utils.get_port_ip(floatingip_lsp)
        if not router_id or not floatingip_ip:
            return
        try:
            self.ovn_north.get_lr(lr_id=router_id)
        except ElementNotFoundError:
            return
        self.ovn_north.remove_nat(
            lr_id=router_id,
            nat_type=ovnconst.NAT_BOTH,
            match_ip=floatingip_ip,
            transaction=transaction,
        )

    def _set_floatingip_external_ids(
        self, floatingip_lsp, transaction, values=None, remove_keys=()
    ):
        values = dict(values or {})
        values[FloatingipMapper.OVN_FLOATINGIP_UPDATE_TS] = _utc_timestamp()
        transaction.add(
            self.idl.db_set(
                ovnconst.TABLE_LSP,
                floatingip_lsp.uuid,
                (ovnconst.ROW_LSP_EXTERNAL_IDS, values),
            )
        )
        for key in remove_keys:
            transaction.add(
                self.idl.db_remove(
                    ovnconst.TABLE_LSP,
                    floatingip_lsp.uuid,
                    ovnconst.ROW_LSP_EXTERNAL_IDS,
                    key,
                    if_exists=True,
                )
            )

    def _disassociate_floatingip(
        self, floatingip_lsp, transaction, values=None
    ):
        self._remove_floatingip_nat(floatingip_lsp, transaction)
        # A single external_ids write: a db_set following a db_remove on the
        # same column in one transaction would restore the removed keys.
        self._set_floatingip_external_ids(
            floatingip_lsp,
            transaction,
            values=values,
            remove_keys=(
                FloatingipMapper.OVN_FLOATINGIP_PORT_ID,
                FloatingipMapper.OVN_FLOATINGIP_ROUTER_ID,
            ),
        )

    @FloatingipMapper.validate_add
    @FloatingipMapper.map_from_rest
    @FloatingipMapper.map_to_rest
    def add_floatingip(
        self,
        network_id,
        port_id=None,
        description=None,
        floating_ip_address=None,
        **kwargs,
    ):
        network = self.ovn_north.get_ls(ls_id=network_id)
        subnet = self._get_floatingip_subnet(network_id)
        floatingip_id = str(uuid.uuid4())
        now = _utc_timestamp()
        external_ids = {
            FloatingipMapper.OVN_FLOATINGIP_MARKER: 'true',
            PortMapper.OVN_NIC_NAME: (
                FloatingipMapper.FLOATINGIP_PREFIX + floatingip_id
            ),
            PortMapper.OVN_DEVICE_OWNER: (
                FloatingipMapper.DEVICE_OWNER_FLOATING_IP
            ),
            PortMapper.OVN_DEVICE_ID: floatingip_id,
            FloatingipMapper.OVN_FLOATINGIP_DESCRIPTION: description or '',
            FloatingipMapper.OVN_FLOATINGIP_CREATE_TS: now,
            FloatingipMapper.OVN_FLOATINGIP_UPDATE_TS: now,
        }
        target = (
            self._get_floatingip_target(str(network.uuid), port_id)
            if port_id
            else None
        )
        if target:
            external_ids[FloatingipMapper.OVN_FLOATINGIP_PORT_ID] = (
                target.port_id
            )
            external_ids[FloatingipMapper.OVN_FLOATINGIP_ROUTER_ID] = (
                target.router_id
            )

        # The address is picked by the provider, so allocation and commit
        # have to be serialized to avoid handing out the same address twice.
        with _floatingip_allocation_lock:
            floatingip_ip = self._allocate_floating_ip_address(
                network, subnet, floating_ip_address
            )
            mac = ip_utils.random_unique_mac(
                self.ovn_north.list_lsp(), self.ovn_north.list_lrp()
            )
            with self.tx_manager.transaction() as tx:
                self.ovn_north.add_floatingip(
                    floatingip_id,
                    str(network.uuid),
                    addresses=[f'{mac} {floatingip_ip}'],
                    external_ids=external_ids,
                    transaction=tx,
                )
                if target:
                    self._add_floatingip_nat(floatingip_ip, target, tx)
        return self._get_floatingip(self._get_floatingip_lsp(floatingip_id))

    @FloatingipMapper.validate_update
    @FloatingipMapper.map_from_rest
    @FloatingipMapper.map_to_rest
    def update_floatingip(self, floatingip_id, **kwargs):
        lsp = self._get_floatingip_lsp(floatingip_id)
        values = {}
        if kwargs.get('description') is not None:
            values[FloatingipMapper.OVN_FLOATINGIP_DESCRIPTION] = kwargs[
                'description'
            ]
        with self.tx_manager.transaction() as tx:
            if 'port_id' not in kwargs:
                self._set_floatingip_external_ids(lsp, tx, values)
            elif kwargs['port_id'] is None:
                self._disassociate_floatingip(lsp, tx, values)
            else:
                network_id = str(self._get_port_network(lsp).uuid)
                target = self._get_floatingip_target(
                    network_id, kwargs['port_id'], floatingip_id=lsp.name
                )
                if not self._is_floatingip_associated_with(lsp, target):
                    self._remove_floatingip_nat(lsp, tx)
                    self._add_floatingip_nat(
                        ip_utils.get_port_ip(lsp), target, tx
                    )
                values[FloatingipMapper.OVN_FLOATINGIP_PORT_ID] = (
                    target.port_id
                )
                values[FloatingipMapper.OVN_FLOATINGIP_ROUTER_ID] = (
                    target.router_id
                )
                self._set_floatingip_external_ids(lsp, tx, values)
        return self._get_floatingip(self._get_floatingip_lsp(floatingip_id))

    @staticmethod
    def _is_floatingip_associated_with(floatingip_lsp, target):
        external_ids = floatingip_lsp.external_ids
        return (
            external_ids.get(FloatingipMapper.OVN_FLOATINGIP_PORT_ID)
            == target.port_id
            and external_ids.get(FloatingipMapper.OVN_FLOATINGIP_ROUTER_ID)
            == target.router_id
        )

    def delete_floatingip(self, floatingip_id):
        lsp = self._get_floatingip_lsp(floatingip_id)
        with self.tx_manager.transaction() as tx:
            self._remove_floatingip_nat(lsp, tx)
            self.ovn_north.remove_lsp(str(lsp.name), transaction=tx)

    def _disassociate_port_floatingips(self, port_id, transaction):
        for lsp in self._list_floatingip_lsps():
            if (
                lsp.external_ids.get(FloatingipMapper.OVN_FLOATINGIP_PORT_ID)
                == port_id
            ):
                self._disassociate_floatingip(lsp, transaction)
