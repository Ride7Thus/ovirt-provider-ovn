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

from handlers.base_handler import GET
from handlers.base_handler import Response
from handlers.selecting_handler import rest
from ovirt_provider_config_common import neutron_url_with_version
from handlers.neutron_routes import _responses


ALIAS = 'alias'
EXTENSIONS = 'extensions'
EXTENSION_ENTITY = 'extensions/{alias}'


@rest(GET, '', _responses)
def get_default(nb_db, content, parameters):
    return Response(
        {
            'versions': [
                {
                    'status': 'CURRENT',
                    'id': 'v2.0',
                    'links': [
                        {'href': neutron_url_with_version(), 'rel': 'self'}
                    ],
                }
            ]
        }
    )


@rest(GET, EXTENSIONS, _responses)
def get_extensions(nb_db, content, parameters):
    return Response({'extensions': nb_db.list_extensions()})


@rest(GET, EXTENSION_ENTITY, _responses)
def show_extension(nb_db, content, parameters):
    nb_db.get_extension(parameters[ALIAS])
    return Response()


@rest(GET, 'tech', _responses)
def get_debug(nb_db, content, parameters):
    networks = nb_db.list_networks()
    ports = nb_db.list_ports()
    subnets = nb_db.list_subnets()
    routers = nb_db.list_routers()
    return Response(
        {
            'networks': networks,
            'ports': ports,
            'subnets': subnets,
            'routers': routers,
        }
    )
