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

import json
from handlers.base_handler import GET
from handlers.base_handler import DELETE
from handlers.base_handler import POST
from handlers.base_handler import PUT
from handlers.base_handler import Response
from handlers.responses_utils import get_entity
from handlers.selecting_handler import rest
from handlers.neutron_routes import _responses


ROUTER_ID = 'router_id'
ROUTERS = 'routers'
ROUTER_ENTITY = 'routers/{router_id}'
ADD_ROUTER_INTERFACE = 'routers/{router_id}/add_router_interface'
DELETE_ROUTER_INTERFACE = 'routers/{router_id}/remove_router_interface'


@rest(GET, ROUTERS, _responses)
def get_routers(nb_db, content, parameters):
    return Response({'routers': nb_db.list_routers()})


@rest(POST, ROUTERS, _responses)
def post_routers(nb_db, content, parameters):
    content_json = json.loads(content)
    received_router = content_json['router']
    router = nb_db.add_router(received_router)
    return Response({'router': router})


@rest(GET, ROUTER_ENTITY, _responses)
def get_router(nb_db, content, parameters):
    return Response({'router': nb_db.get_router(parameters[ROUTER_ID])})


@rest(PUT, ROUTER_ENTITY, _responses)
def put_router(nb_db, content, parameters):
    content_json = json.loads(content)
    received_router = content_json['router']
    router = nb_db.update_router(received_router, parameters[ROUTER_ID])
    return Response({'router': router})


@rest(DELETE, ROUTER_ENTITY, _responses)
def delete_router(nb_db, content, parameters):
    nb_db.delete_router(parameters[ROUTER_ID])
    return Response()


@rest(PUT, ADD_ROUTER_INTERFACE, _responses)
def put_add_router_inerface(nb_db, content, parameters):
    result = nb_db.add_router_interface(
        get_entity(content), parameters[ROUTER_ID]
    )
    return Response(result)


@rest(PUT, DELETE_ROUTER_INTERFACE, _responses)
def put_remove_router_interface(nb_db, content, parameters):
    result = nb_db.delete_router_interface(
        get_entity(content), parameters[ROUTER_ID]
    )
    return Response(result)
