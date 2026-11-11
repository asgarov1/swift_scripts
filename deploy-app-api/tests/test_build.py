import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import deploy_app_store as deploy


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "Example.xcodeproj").mkdir()
        (self.root / "build").mkdir()
        (self.root / "build" / "Example.ipa").touch()
        self.client = deploy.Deployer.__new__(deploy.Deployer)
        self.client.root = self.root
        self.client.api = Mock()

    def test_allows_provisioning_updates_during_archive_and_export(self):
        self.client.cfg = {
            "build": {
                "createIpa": True,
                "projectPath": "Example.xcodeproj",
                "scheme": "Example",
                "ipaPath": "build/Example.ipa",
                "archivePath": "build/Example.xcarchive",
                "exportPath": "build",
                "allowProvisioningUpdates": True,
            }
        }

        with patch.object(deploy.subprocess, "run") as run:
            self.client.prepare_ipa()

        archive_command = run.call_args_list[0].args[0]
        export_command = run.call_args_list[1].args[0]
        self.assertIn("-allowProvisioningUpdates", archive_command)
        self.assertIn("-allowProvisioningUpdates", export_command)


if __name__ == "__main__":
    unittest.main()
