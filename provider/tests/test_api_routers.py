# coding=utf-8
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

import unittest.mock as mock
import pytest
import constants as ovnconst
from handlers.base_handler import ConflictError
from neutron.neutron_api import NeutronApi
from ovntestlib import OvnRouterPort
from ovntestlib import OvnRouterRow
from ovn_north_data import OvnNorthData


@mock.patch('ovsdbapp.backend.ovs_idl.connection', autospec=False)
class TestRoutersApi(OvnNorthData):
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.impl_idl.OvnNbApiIdlImpl.lookup',
    )
    def test_get_router(self, mock_lookup, mock_connection):
        mock_lookup.return_value = OvnNorthData.ROUTER_20
        ovn_north = NeutronApi()
        result = ovn_north.get_router(str(OvnNorthData.ROUTER_ID20))

        assert result['id'] == str(OvnNorthData.ROUTER_ID20)
        assert result['name'] == str(OvnNorthData.ROUTER_NAME20)

        assert mock_lookup.call_args == mock.call(
            ovnconst.TABLE_LR, str(OvnNorthData.ROUTER_ID20)
        )

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LrDelCommand', autospec=False
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.impl_idl.OvnNbApiIdlImpl.lookup',
    )
    def test_delete_router(
        self, mock_lookup, mock_del_command, mock_connection
    ):
        mock_lookup.return_value = OvnNorthData.ROUTER_20
        ovn_north = NeutronApi()

        ovn_north.delete_router(str(OvnNorthData.ROUTER_ID20))

        assert mock_lookup.call_args == mock.call(
            ovnconst.TABLE_LR, str(OvnNorthData.ROUTER_ID20)
        )

        assert mock_del_command.call_count == 1
        expected_del_call = mock.call(
            ovn_north.idl, str(OvnNorthData.ROUTER_ID20), False
        )
        assert mock_del_command.mock_calls[0] == expected_del_call

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LrDelCommand', autospec=False
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.impl_idl.OvnNbApiIdlImpl.lookup',
    )
    def test_delete_router_fail(
        self, mock_lookup, mock_del_command, mock_connection
    ):
        mock_lookup.return_value = OvnRouterRow(
            OvnNorthData.ROUTER_ID20, ports=[OvnRouterPort()]
        )
        ovn_north = NeutronApi()
        with pytest.raises(ConflictError):
            ovn_north.delete_router(str(OvnNorthData.ROUTER_ID20))

        assert mock_lookup.call_args == mock.call(
            ovnconst.TABLE_LR, str(OvnNorthData.ROUTER_ID20)
        )
        assert mock_del_command.call_count == 0


def test_lsp_id_from_lrp_name_supports_both_prefixes():
    from ovndb.ovn_north import lsp_id_from_lrp_name

    lsp_id = '6f8c2e7e-2d3c-4a4e-9f0e-1b7a3a9c5d11'
    assert lsp_id_from_lrp_name('lrp-' + lsp_id) == lsp_id
    assert lsp_id_from_lrp_name('lrp' + lsp_id) == lsp_id
