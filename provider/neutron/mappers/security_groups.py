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

from collections import namedtuple
from netaddr import AddrFormatError
from netaddr import IPNetwork
from netaddr import __version__ as netaddr_version
import neutron.constants as neutron_constants
from handlers.base_handler import BadRequestError
from neutron.mappers.base import Mapper
from neutron.mappers.base import RestDataError
from neutron.mappers.base import UUID_LENGTH
from neutron.mappers.base import to_rest_timestamp


SecurityGroup = namedtuple('SecurityGroup', ['sec_group', 'sec_group_rules'])


netaddr_major_version = int(netaddr_version.split('.')[0])


class SecurityGroupRule(object):
    default_group_id = None

    def __init__(
        self,
        rule,
        security_group,
        remote_group=None,
        default_security_group=None,
    ):
        self.__rule = rule
        self.__sec_group = security_group
        self.__remote_group = remote_group
        self._set_default_sec_group_id(default_security_group)

    @property
    def rule(self):
        return self.__rule

    @property
    def security_group(self):
        return self.__sec_group

    @property
    def remote_group(self):
        return self.__remote_group

    @staticmethod
    def _set_default_sec_group_id(default_security_group):
        # default security group remains unchanged once created
        if default_security_group and not SecurityGroupRule.default_group_id:
            SecurityGroupRule.default_group_id = default_security_group

    @staticmethod
    def get_default_group_id():
        return SecurityGroupRule.default_group_id


class SecurityGroupMandatoryDataMissing(RestDataError):
    message = 'Mandatory data {} is missing'

    def __init__(self, missing_elements):
        super(SecurityGroupMandatoryDataMissing, self).__init__(
            self.message.format(', '.join(missing_elements))
        )


class SecurityGroupInvalidRestData(RestDataError):
    message = 'Invalid data found: {}'

    def __init__(self, invalid_elements):
        super(SecurityGroupInvalidRestData, self).__init__(
            self.message.format(', '.join(invalid_elements))
        )


class SecurityGroupMapper(Mapper):
    REST_SEC_GROUP_ID = 'id'
    REST_SEC_GROUP_NAME = 'name'

    REST_SEC_GROUP_DESC = 'description'

    REST_SEC_GROUP_CREATED_AT = 'created_at'
    REST_SEC_GROUP_UPDATED_AT = 'updated_at'
    REST_SEC_GROUP_REVISION_NR = 'revision_number'
    REST_SEC_GROUP_RULES = 'security_group_rules'
    REST_SEC_GROUP_TAGS = 'tags'

    OVN_SECURITY_GROUP_CREATE_TS = 'ovirt_created_at'
    OVN_SECURITY_GROUP_DESCRIPTION = 'ovirt_description'
    OVN_SECURITY_GROUP_NAME = 'ovirt_sec_group_name'
    OVN_SECURITY_GROUP_PROJECT = 'ovirt_project_id'
    OVN_SECURITY_GROUP_REV_NUMBER = 'ovirt_revision_number'
    OVN_SECURITY_GROUP_TENANT = 'ovirt_tenant_id'
    OVN_SECURITY_GROUP_UPDATE_TS = 'ovirt_updated_at'

    _mandatory_add_data = {REST_SEC_GROUP_NAME}
    _optional_add_data = {
        REST_SEC_GROUP_DESC,
        Mapper.REST_TENANT_ID,
        Mapper.REST_PROJECT_ID,
    }
    _mandatory_update_data = set()
    _optional_update_data = {REST_SEC_GROUP_NAME, REST_SEC_GROUP_DESC}
    optional_attr_ext_id_mapper = {
        REST_SEC_GROUP_CREATED_AT: OVN_SECURITY_GROUP_CREATE_TS,
        REST_SEC_GROUP_UPDATED_AT: OVN_SECURITY_GROUP_UPDATE_TS,
        Mapper.REST_PROJECT_ID: OVN_SECURITY_GROUP_PROJECT,
        Mapper.REST_TENANT_ID: OVN_SECURITY_GROUP_TENANT,
        REST_SEC_GROUP_DESC: OVN_SECURITY_GROUP_DESCRIPTION,
    }

    DEFAULT_PG_NAME = 'Default'
    DROP_ALL_IP_PG_NAME = 'DropAll'
    WHITE_LIST_GROUP_NAMES = [DEFAULT_PG_NAME, DROP_ALL_IP_PG_NAME]

    @staticmethod
    def row2rest(security_group):
        if not security_group:
            return {}

        group_data = security_group.sec_group
        result = {
            SecurityGroupMapper.REST_SEC_GROUP_ID: str(group_data.uuid),
            SecurityGroupMapper.REST_SEC_GROUP_RULES: [
                SecurityGroupRuleMapper.row2rest(rule)
                for rule in security_group.sec_group_rules
            ],
            SecurityGroupMapper.REST_SEC_GROUP_TAGS: [],
            SecurityGroupMapper.REST_SEC_GROUP_REVISION_NR: int(
                group_data.external_ids[
                    SecurityGroupMapper.OVN_SECURITY_GROUP_REV_NUMBER
                ]
            ),
        }
        rest_optional_values = SecurityGroupMapper.set_from_external_ids(
            group_data.external_ids,
            SecurityGroupMapper.optional_attr_ext_id_mapper,
        )
        for key in (
            SecurityGroupMapper.REST_SEC_GROUP_CREATED_AT,
            SecurityGroupMapper.REST_SEC_GROUP_UPDATED_AT,
        ):
            rest_optional_values[key] = to_rest_timestamp(
                rest_optional_values[key]
            )
        result.update(rest_optional_values)
        result[SecurityGroupMapper.REST_SEC_GROUP_NAME] = (
            group_data.external_ids.get(
                SecurityGroupMapper.OVN_SECURITY_GROUP_NAME
            )
        )

        return result

    @staticmethod
    def create_port_group_name(security_group_id):
        return 'ovirt_{}'.format(security_group_id.replace('-', '_'))

    @staticmethod
    def _extract_security_group_id(port_group_name):
        return port_group_name[-UUID_LENGTH:].replace('_', '-')

    @staticmethod
    def rest2row(wrapped_self, func, rest_sec_group_data, security_group_id):
        if security_group_id:
            return func(
                wrapped_self,
                security_group_id,
                rest_sec_group_data[SecurityGroupMapper.REST_SEC_GROUP_NAME],
                rest_sec_group_data.get(
                    SecurityGroupMapper.REST_SEC_GROUP_DESC
                ),
            )
        else:
            return func(
                wrapped_self,
                rest_sec_group_data[SecurityGroupMapper.REST_SEC_GROUP_NAME],
                rest_sec_group_data.get(SecurityGroupMapper.REST_PROJECT_ID),
                rest_sec_group_data.get(SecurityGroupMapper.REST_TENANT_ID),
                rest_sec_group_data.get(
                    SecurityGroupMapper.REST_SEC_GROUP_DESC
                ),
            )

    @classmethod
    def validate_add_rest_input(cls, rest_data):
        cls.validate_keys(
            set(rest_data.keys()),
            cls._mandatory_add_data,
            cls._optional_add_data,
        )

    @classmethod
    def validate_update_rest_input(cls, rest_data):
        cls.validate_keys(
            set(rest_data.keys()),
            cls._mandatory_update_data,
            cls._optional_update_data,
        )


class SecurityGroupRuleMapper(Mapper):
    REST_SEC_GROUP_RULE_ID = 'id'
    REST_SEC_GROUP_RULE_DIRECTION = 'direction'
    REST_SEC_GROUP_RULE_PROTOCOL = 'protocol'
    REST_SEC_GROUP_RULE_ETHERTYPE = 'ethertype'
    REST_SEC_GROUP_RULE_PORT_RANGE_MAX = 'port_range_max'
    REST_SEC_GROUP_RULE_PORT_RANGE_MIN = 'port_range_min'
    REST_SEC_GROUP_RULE_IP_PREFIX = 'remote_ip_prefix'
    REST_SEC_GROUP_RULE_SEC_GROUP_ID = 'security_group_id'
    REST_SEC_GROUP_RULE_DESCRIPTION = 'description'
    REST_SEC_GROUP_RULE_REMOTE_GROUP = 'remote_group_id'

    OVN_SEC_GROUP_RULE_PROTOCOL = 'ovirt_protocol'
    OVN_SEC_GROUP_RULE_ETHERTYPE = 'ovirt_ethertype'
    OVN_SEC_GROUP_RULE_MAX_PORT = 'ovirt_max_port'
    OVN_SEC_GROUP_RULE_MIN_PORT = 'ovirt_min_port'
    OVN_SEC_GROUP_RULE_IP_PREFIX = 'ovirt_ip_prefix'
    OVN_SEC_GROUP_RULE_SEC_GROUP_ID = 'ovirt_port_group_id'
    OVN_SEC_GROUP_RULE_DESCRIPTION = 'ovirt_rule_description'
    OVN_SEC_GROUP_RULE_REMOTE_GROUP_ID = 'ovirt_remote_group_id'

    _mandatory_add_data = {
        REST_SEC_GROUP_RULE_DIRECTION,
        REST_SEC_GROUP_RULE_SEC_GROUP_ID,
    }
    _optional_add_data = {
        REST_SEC_GROUP_RULE_PROTOCOL,
        REST_SEC_GROUP_RULE_ETHERTYPE,
        REST_SEC_GROUP_RULE_PORT_RANGE_MAX,
        REST_SEC_GROUP_RULE_PORT_RANGE_MIN,
        REST_SEC_GROUP_RULE_IP_PREFIX,
        REST_SEC_GROUP_RULE_DESCRIPTION,
        REST_SEC_GROUP_RULE_REMOTE_GROUP,
    }
    optional_attr_ext_id_mapper = {
        REST_SEC_GROUP_RULE_DESCRIPTION: OVN_SEC_GROUP_RULE_DESCRIPTION,
        REST_SEC_GROUP_RULE_ETHERTYPE: OVN_SEC_GROUP_RULE_ETHERTYPE,
        REST_SEC_GROUP_RULE_IP_PREFIX: OVN_SEC_GROUP_RULE_IP_PREFIX,
        REST_SEC_GROUP_RULE_PORT_RANGE_MAX: OVN_SEC_GROUP_RULE_MAX_PORT,
        REST_SEC_GROUP_RULE_PORT_RANGE_MIN: OVN_SEC_GROUP_RULE_MIN_PORT,
        REST_SEC_GROUP_RULE_PROTOCOL: OVN_SEC_GROUP_RULE_PROTOCOL,
        REST_SEC_GROUP_RULE_REMOTE_GROUP: OVN_SEC_GROUP_RULE_REMOTE_GROUP_ID,
    }

    @staticmethod
    def row2rest(rule_wrapper):
        if not rule_wrapper:
            return {}

        rule = rule_wrapper.rule
        security_group = rule_wrapper.security_group
        remote_group = rule_wrapper.remote_group
        default_group_id = (
            str(SecurityGroupRule.get_default_group_id())
            if SecurityGroupRule.get_default_group_id()
            else None
        )
        sec_group_id = str(security_group.uuid)
        result = {
            SecurityGroupRuleMapper.REST_SEC_GROUP_RULE_ID: str(rule.uuid),
            SecurityGroupRuleMapper.REST_SEC_GROUP_RULE_DIRECTION: neutron_constants.OVN_TO_API_DIRECTION_MAPPER[  # noqa: E501
                rule.direction
            ],
            SecurityGroupRuleMapper.REST_SEC_GROUP_RULE_SEC_GROUP_ID: (
                sec_group_id  # noqa: E501
                if sec_group_id != SecurityGroupMapper.DEFAULT_PG_NAME
                else default_group_id
            ),
        }
        optional_rest_values = SecurityGroupRuleMapper.set_from_external_ids(
            rule.external_ids,
            SecurityGroupRuleMapper.optional_attr_ext_id_mapper,
        )
        port_max = optional_rest_values[
            SecurityGroupRuleMapper.REST_SEC_GROUP_RULE_PORT_RANGE_MAX
        ]
        optional_rest_values[
            SecurityGroupRuleMapper.REST_SEC_GROUP_RULE_PORT_RANGE_MAX
        ] = (int(port_max) if port_max is not None else port_max)
        port_min = optional_rest_values[
            SecurityGroupRuleMapper.REST_SEC_GROUP_RULE_PORT_RANGE_MIN
        ]
        optional_rest_values[
            SecurityGroupRuleMapper.REST_SEC_GROUP_RULE_PORT_RANGE_MIN
        ] = (int(port_min) if port_min is not None else port_min)
        if remote_group:
            optional_rest_values[
                SecurityGroupRuleMapper.REST_SEC_GROUP_RULE_REMOTE_GROUP
            ] = str(remote_group.uuid)

        result.update(optional_rest_values)
        return result

    @classmethod
    def validate_add_rest_input(cls, rest_data):
        cls.validate_keys(
            set(rest_data.keys()),
            cls._mandatory_add_data,
            cls._optional_add_data,
        )
        if rest_data.get(
            SecurityGroupRuleMapper.REST_SEC_GROUP_RULE_IP_PREFIX
        ) and rest_data.get(
            SecurityGroupRuleMapper.REST_SEC_GROUP_RULE_REMOTE_GROUP
        ):
            raise BadRequestError(
                'Only remote_ip_prefix or remote_group_id may be provided.'
            )
        prefix = rest_data.get(
            SecurityGroupRuleMapper.REST_SEC_GROUP_RULE_IP_PREFIX
        )
        if prefix:
            try:
                # pylint: disable=E1123
                if netaddr_major_version < 1:
                    addr_or_prefix = IPNetwork(prefix, implicit_prefix=True)
                else:
                    addr_or_prefix = IPNetwork(prefix, expand_partial=True)
                # pylint: enable=E1123
            except AddrFormatError as afe:
                raise BadRequestError(afe)

            ether_type = rest_data.get(
                SecurityGroupRuleMapper.REST_SEC_GROUP_RULE_ETHERTYPE
            )

            if ether_type != 'IPv{version}'.format(
                version=addr_or_prefix.version
            ):
                raise BadRequestError(
                    'Conflicting value ethertype '
                    '{ether_type} for CIDR {cidr}'.format(
                        ether_type=ether_type, cidr=prefix
                    )
                )

    @staticmethod
    def rest2row(wrapped_self, func, rest_data, entity_id):
        security_group_id = rest_data[
            SecurityGroupRuleMapper.REST_SEC_GROUP_RULE_SEC_GROUP_ID
        ]
        direction = rest_data[
            SecurityGroupRuleMapper.REST_SEC_GROUP_RULE_DIRECTION
        ]
        description = rest_data.get(
            SecurityGroupRuleMapper.REST_SEC_GROUP_RULE_DESCRIPTION
        )
        ether_type = rest_data.get(
            SecurityGroupRuleMapper.REST_SEC_GROUP_RULE_ETHERTYPE,
            neutron_constants.IPV4_ETHERTYPE,
        )
        rest_port_max = rest_data.get(
            SecurityGroupRuleMapper.REST_SEC_GROUP_RULE_PORT_RANGE_MAX
        )
        port_max = int(rest_port_max) if rest_port_max else None
        rest_port_min = rest_data.get(
            SecurityGroupRuleMapper.REST_SEC_GROUP_RULE_PORT_RANGE_MIN
        )
        port_min = int(rest_port_min) if rest_port_min else None
        protocol = rest_data.get(
            SecurityGroupRuleMapper.REST_SEC_GROUP_RULE_PROTOCOL
        )
        ip_prefix = rest_data.get(
            SecurityGroupRuleMapper.REST_SEC_GROUP_RULE_IP_PREFIX
        )
        remote_group_name = rest_data.get(
            SecurityGroupRuleMapper.REST_SEC_GROUP_RULE_REMOTE_GROUP
        )
        return func(
            wrapped_self,
            security_group_id,
            direction,
            description,
            ether_type,
            port_min,
            port_max,
            ip_prefix,
            protocol,
            remote_group_name,
        )
