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

from functools import wraps
import constants as ovnconst
from handlers.base_handler import ElementNotFoundError
from handlers.base_handler import MethodNotAllowedError
from neutron.mappers.security_groups import SecurityGroup
from neutron.mappers.security_groups import SecurityGroupRule
from neutron.mappers.security_groups import SecurityGroupMapper
from neutron.mappers.security_groups import SecurityGroupRuleMapper
from neutron.api.base import NeutronApiBase


# The resource APIs are mixins of NeutronApi and call each other through
# it, which pylint can not see.
# pylint: disable=no-member


def assure_security_groups_support(f):
    @wraps(f)
    def inner(wrapped_self, *args, **kwargs):
        if not wrapped_self.security_group_support:
            raise MethodNotAllowedError(
                'Security Groups are only supported on ovirt <= 4.3'
            )
        return f(wrapped_self, *args, **kwargs)

    return inner


def wrap_default_group_id(f):
    @wraps(f)
    def inner(wrapped_self, *args, **kwargs):
        try:
            default_group = wrapped_self.ovn_north.get_security_group(
                SecurityGroupMapper.DEFAULT_PG_NAME
            )
            default_group_id = default_group.uuid
            return f(
                wrapped_self,
                default_group_id=default_group_id,
                *args,
                **kwargs,
            )
        except ElementNotFoundError:
            return f(wrapped_self, *args, **kwargs)

    return inner


class SecurityGroupsApi(NeutronApiBase):
    """Security groups and their rules (port groups, ACLs)."""

    @SecurityGroupMapper.map_to_rest
    @wrap_default_group_id
    def list_security_groups(self, default_group_id=None):
        return self._list_security_groups(default_group_id)

    def _list_security_groups(self, default_group_id=None):
        if not self.are_security_groups_supported():
            return []
        security_groups = []
        for group_data in self.ovn_north.list_security_groups():
            security_group_rules = self._process_acls(
                default_group_id,
                group_data,
                self.ovn_north.list_security_group_rules(group_data),
            )
            security_groups.append(
                SecurityGroup(group_data, security_group_rules)
            )
        return security_groups

    @SecurityGroupMapper.map_to_rest
    @wrap_default_group_id
    @assure_security_groups_support
    def get_security_group(self, sec_group_id, default_group_id=None):
        security_group = self.ovn_north.get_security_group(sec_group_id)
        all_rules = self.ovn_north.list_security_group_rules(security_group)
        security_group_rules = self._process_acls(
            default_group_id, security_group, all_rules
        )
        return SecurityGroup(
            sec_group=security_group, sec_group_rules=security_group_rules
        )

    def _process_acls(self, default_group_id, security_group, acls):
        return [
            self._build_security_group_rule_wrapper(
                default_group_id, acl, security_group
            )
            for acl in acls
        ]

    def _build_security_group_rule_wrapper(
        self, default_group_id, acl, security_group
    ):
        remote_group_id = acl.external_ids.get(
            SecurityGroupRuleMapper.OVN_SEC_GROUP_RULE_REMOTE_GROUP_ID
        )
        remote_group = (
            self.ovn_north.get_security_group(remote_group_id)
            if remote_group_id
            else None
        )
        return SecurityGroupRule(
            acl,
            security_group,
            remote_group=remote_group,
            default_security_group=default_group_id,
        )

    @SecurityGroupMapper.validate_add
    @SecurityGroupMapper.map_from_rest
    @assure_security_groups_support
    def add_security_group(
        self, name, project_id=None, tenant_id=None, description=None
    ):
        with self.tx_manager.transaction() as tx:
            group_data, egress_rules = self.ovn_north.add_security_group(
                name, project_id, tenant_id, description, transaction=tx
            )
        return self.get_security_group(group_data.name)

    @assure_security_groups_support
    def delete_security_group(self, security_group_id):
        self.ovn_north.remove_security_group(security_group_id)

    @SecurityGroupMapper.validate_update
    @SecurityGroupMapper.map_from_rest
    @assure_security_groups_support
    def update_security_group(self, sec_group_id, name, description=None):
        with self.tx_manager.transaction() as tx:
            self.ovn_north.update_security_group(
                sec_group_id, name, description, transaction=tx
            )
        return self.get_security_group(sec_group_id)

    @SecurityGroupRuleMapper.map_to_rest
    @wrap_default_group_id
    @assure_security_groups_support
    def list_security_group_rules(self, default_group_id=None):
        security_groups = self._list_security_groups(default_group_id)
        security_group_rules = []
        for sec_group in security_groups:
            security_group_rules.extend(
                self._process_acls(
                    default_group_id,
                    sec_group.sec_group,
                    [
                        rule_wrapper.rule
                        for rule_wrapper in sec_group.sec_group_rules
                    ],
                )
            )
        return security_group_rules

    @SecurityGroupRuleMapper.map_to_rest
    @wrap_default_group_id
    @assure_security_groups_support
    def get_security_group_rule(
        self, security_group_rule_id, default_group_id=None
    ):
        rule = self.ovn_north.get_security_group_rule(security_group_rule_id)
        sec_group_id = rule.external_ids[
            SecurityGroupRuleMapper.OVN_SEC_GROUP_RULE_SEC_GROUP_ID
        ]
        remote_group_id = rule.external_ids.get(
            SecurityGroupRuleMapper.OVN_SEC_GROUP_RULE_REMOTE_GROUP_ID
        )
        sec_group = self.ovn_north.get_security_group(sec_group_id)
        remote_group = None
        if remote_group_id:
            remote_group = self.ovn_north.get_security_group(remote_group_id)

        return SecurityGroupRule(
            rule,
            sec_group,
            remote_group=remote_group,
            default_security_group=default_group_id,
        )

    @SecurityGroupRuleMapper.validate_add
    @SecurityGroupRuleMapper.map_from_rest
    @SecurityGroupRuleMapper.map_to_rest
    @assure_security_groups_support
    def add_security_group_rule(
        self,
        security_group_id,
        direction,
        description=None,
        ether_type=None,
        port_min=None,
        port_max=None,
        remote_ip_prefix=None,
        protocol=None,
        remote_group_id=None,
    ):
        sec_group = self.ovn_north.get_security_group(security_group_id)
        (
            sec_group_rule,
            remote_group,
        ) = self.ovn_north.create_security_group_rule(
            sec_group,
            direction,
            description=description,
            ether_type=ether_type,
            remote_ip_prefix=remote_ip_prefix,
            port_min=port_min,
            port_max=port_max,
            protocol=protocol,
            remote_group_id=remote_group_id,
        )
        default_group_id = (
            sec_group.uuid
            if sec_group.name in SecurityGroupMapper.WHITE_LIST_GROUP_NAMES
            else None
        )
        return SecurityGroupRule(
            sec_group_rule,
            sec_group,
            remote_group=remote_group,
            default_security_group=default_group_id,
        )

    @assure_security_groups_support
    def delete_security_group_rule(self, security_group_rule_id):
        self.ovn_north.remove_security_group_rule(security_group_rule_id)

    def are_security_groups_supported(self):
        return ovnconst.TABLE_PORT_GROUP in self.idl.tables
