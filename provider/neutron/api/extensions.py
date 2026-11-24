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

import constants as ovnconst
from handlers.base_handler import ElementNotFoundError
from neutron.api.base import NeutronApiBase


# The resource APIs are mixins of NeutronApi and call each other through
# it, which pylint can not see.
# pylint: disable=no-member


class ExtensionsApi(NeutronApiBase):
    """Neutron API extensions."""

    @staticmethod
    def list_extensions():
        extensions = []
        for name, alias in ovnconst.SUPPORTED_EXTENSIONS:
            extensions.append(
                {
                    'updated': ovnconst.EXTENSION_UPDATED,
                    'name': name,
                    'alias': alias,
                    'description': name,
                    'links': [],
                }
            )
        return extensions

    @staticmethod
    def get_extension(ext_alias):
        for _, alias in ovnconst.SUPPORTED_EXTENSIONS:
            if ext_alias == alias:
                return
        raise ElementNotFoundError(
            f'Cannot find extension with alias "{ext_alias}"'
        )
