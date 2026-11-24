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

import ovn_connection
from neutron.mappers.ports import PortMapper
from ovndb.ovn_north import OvnNorth


# The resource APIs are mixins of NeutronApi and call each other through
# it, which pylint can not see.
# pylint: disable=no-member


class NeutronApiBase(object):
    """State and helpers shared by the resource APIs."""

    def __init__(self, sec_group_support=None):
        self.idl = ovn_connection.connect()
        self.ovn_north = OvnNorth(self.idl)
        self.security_group_support = (
            sec_group_support or self.are_security_groups_supported()
        )
        self.tx_manager = ovn_connection.OvnTransactionManager(
            self.idl.ovsdb_connection
        )

    # TODO: could this be moved to ovsdbapp?
    def _get_port_network(self, port):
        networks = self.ovn_north.list_ls()
        return next(network for network in networks if port in network.ports)

    def _is_port_ovirt_controlled(self, port_row):
        return PortMapper.OVN_NIC_NAME in port_row.external_ids
