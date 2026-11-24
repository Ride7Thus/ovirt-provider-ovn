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


SUBNET_ID = 'subnet_id'
SUBNETS = 'subnets'
SUBNET_ENTITY = 'subnets/{subnet_id}'


@rest(GET, SUBNET_ENTITY, _responses)
def show_subnet(nb_db, content, parameters):
    return Response({'subnet': nb_db.get_subnet(parameters[SUBNET_ID])})


@rest(GET, SUBNETS, _responses)
def get_subnets(nb_db, content, parameters):
    return Response({'subnets': nb_db.list_subnets()})


@rest(DELETE, SUBNET_ENTITY, _responses)
def delete_subnet(nb_db, content, parameters):
    nb_db.delete_subnet(parameters[SUBNET_ID])
    return Response()


@rest(POST, SUBNETS, _responses)
def post_subnets(nb_db, content, parameters):
    received_subnet = get_entity(content, 'subnet')
    subnet = nb_db.add_subnet(received_subnet)
    return Response({'subnet': subnet})


@rest(PUT, SUBNET_ENTITY, _responses)
def put_subnets(nb_db, content, parameters):
    received_subnet = get_entity(content, 'subnet')
    subnet = nb_db.update_subnet(received_subnet, parameters[SUBNET_ID])
    return Response({'subnet': subnet})
