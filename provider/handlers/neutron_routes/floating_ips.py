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


FLOATINGIPS = 'floatingips'
FLOATINGIP_ID = 'floatingip_id'
FLOATINGIP_ENTITY = 'floatingips/{floatingip_id}'


@rest(GET, FLOATINGIPS, _responses)
def get_floating_ips(nb_db, content, parameters):
    floatingips = nb_db.list_floatingips()
    return Response({'floatingips': floatingips})


@rest(POST, FLOATINGIPS, _responses)
def post_floating_ips(nb_db, content, parameters):
    received_floatingip = get_entity(content, 'floatingip')
    floatingip = nb_db.add_floatingip(received_floatingip)
    return Response({'floatingip': floatingip})


@rest(DELETE, FLOATINGIP_ENTITY, _responses)
def delete_floatingip(nb_db, content, parameters):
    nb_db.delete_floatingip(parameters[FLOATINGIP_ID])
    return Response()


@rest(GET, FLOATINGIP_ENTITY, _responses)
def show_floatingip(nb_db, content, parameters):
    return Response(
        {'floatingip': nb_db.get_floatingip(parameters[FLOATINGIP_ID])}
    )


@rest(PUT, FLOATINGIP_ENTITY, _responses)
def put_floatingip(nb_db, content, parameters):
    received_floatingip = get_entity(content, 'floatingip')
    floatingip = nb_db.update_floatingip(
        received_floatingip, parameters[FLOATINGIP_ID]
    )
    return Response({'floatingip': floatingip})
