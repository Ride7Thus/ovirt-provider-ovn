# Copyright 2016-2021 Red Hat, Inc.
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

from handlers.neutron_routes import _responses
from handlers.neutron_routes import general  # noqa: F401
from handlers.neutron_routes import networks  # noqa: F401
from handlers.neutron_routes import ports  # noqa: F401
from handlers.neutron_routes import subnets  # noqa: F401
from handlers.neutron_routes import routers  # noqa: F401
from handlers.neutron_routes import security_groups  # noqa: F401
from handlers.neutron_routes import floating_ips  # noqa: F401


def responses():
    return _responses
