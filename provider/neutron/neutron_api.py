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

from neutron.api.networks import NetworksApi
from neutron.api.ports import PortsApi
from neutron.api.subnets import SubnetsApi
from neutron.api.routers import RoutersApi
from neutron.api.security_groups import SecurityGroupsApi
from neutron.api.floating_ips import FloatingIpsApi
from neutron.api.extensions import ExtensionsApi


class NeutronApi(
    NetworksApi,
    PortsApi,
    SubnetsApi,
    RoutersApi,
    SecurityGroupsApi,
    FloatingIpsApi,
    ExtensionsApi,
):
    """
    The neutron API served by the provider. Each resource is
    implemented by its own mixin in the neutron.api package.
    """
