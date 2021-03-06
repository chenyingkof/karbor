# Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import collections
from karbor.common import constants
from karbor.context import RequestContext
from karbor.resource import Resource
from karbor.services.protection.bank_plugin import Bank
from karbor.services.protection.bank_plugin import BankPlugin
from karbor.services.protection.bank_plugin import BankSection
from karbor.services.protection import client_factory
from karbor.services.protection.protection_plugins. \
    share.share_snapshot_plugin import ManilaSnapshotProtectionPlugin
from karbor.services.protection.protection_plugins.share \
    import share_snapshot_plugin_schemas
from karbor.tests import base
import mock
from oslo_config import cfg
from oslo_config import fixture


class FakeBankPlugin(BankPlugin):
    def update_object(self, key, value):
        return

    def get_object(self, key):
        return

    def list_objects(self, prefix=None, limit=None, marker=None,
                     sort_dir=None):
        return

    def delete_object(self, key):
        return

    def get_owner_id(self):
        return


fake_bank = Bank(FakeBankPlugin())
fake_bank_section = BankSection(bank=fake_bank, section="fake")

ResourceNode = collections.namedtuple(
    "ResourceNode",
    ["value",
     "child_nodes"]
)

Share = collections.namedtuple(
    "Share",
    ["status"]
)

Snapshot = collections.namedtuple(
    "Snapshot",
    ["id", "status"]
)


def call_hooks(operation, checkpoint, resource, context, parameters, **kwargs):
    def noop(*args, **kwargs):
        pass

    hooks = (
        'on_prepare_begin',
        'on_prepare_finish',
        'on_main',
        'on_complete',
    )
    for hook_name in hooks:
        hook = getattr(operation, hook_name, noop)
        hook(checkpoint, resource, context, parameters, **kwargs)


class FakeCheckpoint(object):
    def __init__(self):
        self.bank_section = fake_bank_section

    def get_resource_bank_section(self, resource_id):
        return self.bank_section


class ManilaProtectionPluginTest(base.TestCase):
    def setUp(self):
        super(ManilaProtectionPluginTest, self).setUp()

        plugin_config = cfg.ConfigOpts()
        plugin_config_fixture = self.useFixture(fixture.Config(plugin_config))
        plugin_config_fixture.load_raw_values(
            group='manila_snapshot_plugin',
            poll_interval=0,
        )

        self.plugin = ManilaSnapshotProtectionPlugin(plugin_config)

        cfg.CONF.set_default('manila_endpoint',
                             'http://127.0.0.1:8774/v2.1',
                             'manila_client')
        service_catalog = [
            {'type': 'sharev2',
             'endpoints': [{'publicURL': 'http://127.0.0.1:8774/v2.1/abcd'}],
             },
        ]
        self.cntxt = RequestContext(user_id='demo',
                                    project_id='abcd',
                                    auth_token='efgh',
                                    service_catalog=service_catalog)
        self.manila_client = client_factory.ClientFactory.create_client(
            "manila", self.cntxt)
        self.checkpoint = FakeCheckpoint()

    def test_get_options_schema(self):
        options_schema = self.plugin.get_options_schema(
            constants.SHARE_RESOURCE_TYPE)
        self.assertEqual(options_schema,
                         share_snapshot_plugin_schemas.OPTIONS_SCHEMA)

    def test_get_restore_schema(self):
        options_schema = self.plugin.get_restore_schema(
            constants.SHARE_RESOURCE_TYPE)
        self.assertEqual(options_schema,
                         share_snapshot_plugin_schemas.RESTORE_SCHEMA)

    def test_get_saved_info_schema(self):
        options_schema = self.plugin.get_saved_info_schema(
            constants.SHARE_RESOURCE_TYPE)
        self.assertEqual(options_schema,
                         share_snapshot_plugin_schemas.SAVED_INFO_SCHEMA)

    @mock.patch('karbor.services.protection.protection_plugins.share.'
                'share_snapshot_plugin.utils.status_poll')
    @mock.patch('karbor.services.protection.clients.manila.create')
    def test_create_snapshot(self, mock_manila_create, mock_status_poll):
        resource = Resource(id="123",
                            type=constants.SHARE_RESOURCE_TYPE,
                            name='fake')

        fake_bank_section.update_object = mock.MagicMock()

        protect_operation = self.plugin.get_protect_operation(resource)
        mock_manila_create.return_value = self.manila_client

        self.manila_client.shares.get = mock.MagicMock()
        self.manila_client.shares.return_value = Share(
            status="available"
        )
        fake_bank_section.update_object = mock.MagicMock()
        self.manila_client.share_snapshots.create = mock.MagicMock()
        self.manila_client.share_snapshots.create.return_value = Snapshot(
            id="1234",
            status="available"
        )
        self.manila_client.share_snapshots.get = mock.MagicMock()
        self.manila_client.share_snapshots.get.return_value = Snapshot(
            id="1234",
            status="available"
        )
        mock_status_poll.return_value = True
        call_hooks(protect_operation, self.checkpoint, resource, self.cntxt,
                   {})

    @mock.patch('karbor.services.protection.protection_plugins.share.'
                'share_snapshot_plugin.utils.status_poll')
    @mock.patch('karbor.services.protection.clients.manila.create')
    def test_delete_snapshot(self, mock_manila_create, mock_status_poll):
        resource = Resource(id="123",
                            type=constants.SHARE_RESOURCE_TYPE,
                            name='fake')
        mock_manila_create.return_value = self.manila_client
        self.manila_client.share_snapshots.get = mock.MagicMock()
        self.manila_client.share_snapshots.get.return_value = Snapshot(
            id="1234",
            status="available"
        )
        self.manila_client.share_snapshots.delete = mock.MagicMock()

        fake_bank_section.get_object = mock.MagicMock()
        fake_bank_section.get_object.return_value = {
            "snapshot_id": "1234"}

        mock_status_poll.return_value = True
        delete_operation = self.plugin.get_delete_operation(resource)
        call_hooks(delete_operation, self.checkpoint, resource, self.cntxt,
                   {})

    @mock.patch('karbor.services.protection.protection_plugins.utils.'
                'update_resource_verify_result')
    @mock.patch('karbor.services.protection.clients.manila.create')
    def test_verify_snapshot(self, mock_manila_create, mock_update_verify):
        resource = Resource(id="123",
                            type=constants.SHARE_RESOURCE_TYPE,
                            name='fake')
        mock_manila_create.return_value = self.manila_client
        self.manila_client.share_snapshots.get = mock.MagicMock()
        self.manila_client.share_snapshots.get.return_value = Snapshot(
            id="1234",
            status="available"
        )

        fake_bank_section.get_object = mock.MagicMock()
        fake_bank_section.get_object.return_value = {
            "snapshot_id": "1234"}

        verify_operation = self.plugin.get_verify_operation(resource)
        call_hooks(verify_operation, self.checkpoint, resource, self.cntxt,
                   {})
        mock_update_verify.assert_called_with(
            None, resource.type, resource.id, 'available')

    def test_get_supported_resources_types(self):
        types = self.plugin.get_supported_resources_types()
        self.assertEqual([constants.SHARE_RESOURCE_TYPE], types)
