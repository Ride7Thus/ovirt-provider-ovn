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
from handlers.base_handler import DELETE
from handlers.base_handler import POST
from handlers.base_handler import PUT
from handlers.base_handler import Response
from handlers.responses_utils import get_entity
from handlers.selecting_handler import rest
from handlers.neutron_routes import _responses


PORT_ID = 'port_id'
PORTS = 'ports'
PORT_ENTITY = 'ports/{port_id}'


@rest(GET, PORT_ENTITY, _responses)
def show_port(nb_db, content, parameters):
    return Response({'port': nb_db.get_port(parameters[PORT_ID])})


@rest(GET, PORTS, _responses)
def get_ports(nb_db, content, parameters):
    ports = nb_db.list_ports()
    return Response({'ports': ports})


@rest(DELETE, PORT_ENTITY, _responses)
def delete_port(nb_db, content, parameters):
    nb_db.delete_port(parameters[PORT_ID])
    return Response()


@rest(POST, PORTS, _responses)
def post_ports(nb_db, content, parameters):
    received_port = get_entity(content, 'port')
    port = nb_db.add_port(received_port)
    return Response({'port': port})


@rest(PUT, PORT_ENTITY, _responses)
def put_ports(nb_db, content, parameters):
    received_port = get_entity(content, 'port')
    port = nb_db.update_port(received_port, parameters[PORT_ID])
    return Response({'port': port})
