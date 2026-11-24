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


SECURITY_GROUP_ID = 'security_group_id'
SECURITY_GROUP_RULE_ID = 'security_group_rule_id'
SECURITY_GROUPS = 'security-groups'
SECURITY_GROUP_ENTITY = 'security-groups/{security_group_id}'
SECURITY_GROUP_RULES = 'security-group-rules'
SECURITY_GROUP_RULE_ENTITY = 'security-group-rules/{security_group_rule_id}'


@rest(GET, SECURITY_GROUPS, _responses)
def get_security_groups(nb_db, content, parameters):
    return Response({'security_groups': nb_db.list_security_groups()})


@rest(GET, SECURITY_GROUP_ENTITY, _responses)
def show_security_group(nb_db, content, parameters):
    return Response(
        {
            'security_group': nb_db.get_security_group(
                parameters[SECURITY_GROUP_ID]
            )
        }
    )


@rest(POST, SECURITY_GROUPS, _responses)
def post_security_groups(nb_db, content, parameters):
    sec_group = get_entity(content, 'security_group')
    sec_group_data = nb_db.add_security_group(sec_group)
    return Response({'security_group': sec_group_data})


@rest(DELETE, SECURITY_GROUP_ENTITY, _responses)
def delete_security_group(nb_db, content, parameters):
    nb_db.delete_security_group(parameters[SECURITY_GROUP_ID])
    return Response()


@rest(PUT, SECURITY_GROUP_ENTITY, _responses)
def put_security_group(nb_db, content, parameters):
    received_security_group = get_entity(content, 'security_group')
    sec_group = nb_db.update_security_group(
        received_security_group, parameters[SECURITY_GROUP_ID]
    )
    return Response({'security_group': sec_group})


@rest(GET, SECURITY_GROUP_RULES, _responses)
def get_security_group_rules(nb_db, content, parameters):
    return Response(
        {'security_group_rules': nb_db.list_security_group_rules()}
    )


@rest(GET, SECURITY_GROUP_RULE_ENTITY, _responses)
def show_security_group_rule(nb_db, content, parameters):
    return Response(
        {
            'security_group_rule': nb_db.get_security_group_rule(
                parameters[SECURITY_GROUP_RULE_ID]
            )
        }
    )


@rest(POST, SECURITY_GROUP_RULES, _responses)
def post_security_group_rule(nb_db, content, parameters):
    received_sec_group_rule = get_entity(content, 'security_group_rule')
    return Response(
        {
            'security_group_rule': nb_db.add_security_group_rule(
                received_sec_group_rule
            )
        }
    )


@rest(DELETE, SECURITY_GROUP_RULE_ENTITY, _responses)
def delete_security_group_rule(nb_db, content, parameters):
    nb_db.delete_security_group_rule(parameters[SECURITY_GROUP_RULE_ID])
    return Response()
