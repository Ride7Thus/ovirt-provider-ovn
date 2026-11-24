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


NETWORK_ID = 'network_id'
NETWORKS = 'networks'
NETWORK_ENTITY = 'networks/{network_id}'


@rest(GET, NETWORK_ENTITY, _responses)
def show_network(nb_db, content, parameters):
    return Response({'network': nb_db.get_network(parameters[NETWORK_ID])})


@rest(GET, NETWORKS, _responses)
def get_networks(nb_db, content, parameters):
    networks = nb_db.list_networks()
    return Response({'networks': networks})


@rest(DELETE, NETWORK_ENTITY, _responses)
def delete_network(nb_db, content, parameters):
    nb_db.delete_network(parameters[NETWORK_ID])
    return Response()


@rest(POST, NETWORKS, _responses)
def post_networks(nb_db, content, parameters):
    received_network = get_entity(content, 'network')
    network = nb_db.add_network(received_network)
    return Response({'network': network})


@rest(PUT, NETWORK_ENTITY, _responses)
def put_network(nb_db, content, parameters):
    received_network = get_entity(content, 'network')
    network = nb_db.update_network(received_network, parameters[NETWORK_ID])
    return Response({'network': network})
