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

import abc
from functools import wraps
from handlers.base_handler import BadRequestError


OVN_PREFIX = 'ovirt_'


OVN_PREFIX_LENGTH = len(OVN_PREFIX)


UUID_LENGTH = 36


def to_rest_timestamp(value):
    """OVN keeps naive UTC timestamps, the REST API expects a 'Z' suffix."""
    if not value or value.endswith('Z'):
        return value
    return value + 'Z'


class Mapper(object, metaclass=abc.ABCMeta):

    REST_TENANT_ID = 'tenant_id'
    REST_PROJECT_ID = 'project_id'

    @classmethod
    def map_from_rest(cls, f):
        @wraps(f)
        def wrapper(wrapped_self, rest_data, entity_id=None):
            return cls.rest2row(wrapped_self, f, rest_data, entity_id)

        return wrapper

    @classmethod
    def validate_add(cls, f):
        return cls._validate(f, cls.validate_add_rest_input)

    @classmethod
    def validate_update(cls, f):
        return cls._validate(f, cls.validate_update_rest_input)

    @classmethod
    def _validate(cls, f, validate_rest_input):
        @wraps(f)
        def wrapper(wrapped_self, rest_data, entity_id=None):
            validate_rest_input(rest_data)
            return (
                f(wrapped_self, rest_data, entity_id)
                if entity_id
                else f(wrapped_self, rest_data)
            )

        return wrapper

    @classmethod
    def map_to_rest(cls, f):
        @wraps(f)
        def wrapper(wrapped_self, *args, **kwargs):
            data = f(wrapped_self, *args, **kwargs)
            if isinstance(data, list):
                return [cls.row2rest(row) for row in data]
            else:
                return cls.row2rest(data)

        return wrapper

    @staticmethod
    def rest2row(wrapped_self, func, rest_data, entity_id):
        raise NotImplementedError()

    @staticmethod
    def row2rest(row):
        raise NotImplementedError()

    @staticmethod
    def validate_keys(input_keys, mandatory_data, optional_data):
        missing_data = mandatory_data - input_keys
        all_allowed_data = mandatory_data | optional_data
        invalid_data = input_keys - all_allowed_data
        if missing_data:
            raise MandatoryDataMissing(missing_data)
        elif invalid_data:
            raise InvalidRestData(invalid_data)

    @staticmethod
    def validate_add_rest_input(rest_data):
        raise NotImplementedError()

    @staticmethod
    def validate_update_rest_input(rest_data):
        raise NotImplementedError()

    @staticmethod
    def _boolean_or_exception(attribute_name, boolean_value):
        if not isinstance(boolean_value, bool):
            raise RestDataError(
                '{attr} must be of type bool'.format(attr=attribute_name)
            )

    @staticmethod
    def _str2bool(boolean_string):
        return boolean_string.lower() == 'true'

    @staticmethod
    def set_from_external_ids(external_ids, mappings):
        return {
            rest_key: external_ids.get(ext_id_key)
            for rest_key, ext_id_key in mappings.items()
        }


class RestDataError(BadRequestError):
    pass


class MandatoryDataMissing(RestDataError):
    message = 'Mandatory data {attributes} is missing'

    def __init__(self, missing_elements):
        self._missing_elements = missing_elements

    def __str__(self):
        return self.message.format(
            attributes=', '.join(self._missing_elements)
        )


class InvalidRestData(RestDataError):
    message = 'Invalid data found: {attributes}'

    def __init__(self, invalid_elements):
        self._invalid_elements = invalid_elements

    def __str__(self):
        return self.message.format(
            attributes=', '.join(self._invalid_elements)
        )


class UnsupportedDataValueError(RestDataError):
    message = 'Setting {key} value to {value} is not supported'
    extra_msg = '. Allowed values are: {allowed_values}'

    def __init__(self, key, value, supported_values=None):
        self._key = key
        self._value = value
        self._supported_values = supported_values

    def __str__(self):
        return (
            self.message.format(key=self._key, value=self._value)
            + self.extra_msg.format(allowed_values=self._supported_values)
            if self._supported_values
            else ""
        )
