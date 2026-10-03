import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import deploy_app_store as deploy


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.client = deploy.Deployer.__new__(deploy.Deployer)
        self.client.root = Path(self.temporary.name)
        self.client.cfg = {"media": {"screenshots": [], "previews": []}}
        self.client.api = Mock()
        self.client.api.collection.return_value = []

    def test_each_locale_uses_its_own_localization_and_set(self):
        for locale in ("en", "fr"):
            folder = self.client.root / "screenshots" / "iphone" / locale
            folder.mkdir(parents=True)
            (folder / "01.png").write_bytes(locale.encode())
        localizations = {
            "en-US": {"id": "localization-en", "attributes": {"locale": "en-US"}},
            "fr-FR": {"id": "localization-fr", "attributes": {"locale": "fr-FR"}},
        }
        self.client.ensure_set = Mock(side_effect=lambda localization, kind, display: {
            "id": "set-" + localization["id"]
        })
        self.client.upload_asset = Mock()

        self.client.media(localizations)

        self.assertEqual(
            [call.args[0]["id"] for call in self.client.ensure_set.call_args_list],
            ["localization-en", "localization-fr"],
        )
        self.assertEqual(
            [call.args[0] for call in self.client.upload_asset.call_args_list],
            ["set-localization-en", "set-localization-fr"],
        )

    def test_rejects_more_than_ten_screenshots_before_upload(self):
        folder = self.client.root / "screenshots" / "iphone" / "en"
        folder.mkdir(parents=True)
        for number in range(11):
            (folder / f"{number:02}.png").write_bytes(bytes([number]))
        self.client.ensure_set = Mock(return_value={"id": "set-en"})
        self.client.upload_asset = Mock()

        with self.assertRaisesRegex(deploy.DeployError, "permits at most 10"):
            self.client.media({"en-US": {"id": "localization-en"}})
        self.client.upload_asset.assert_not_called()

    def test_only_uploads_screenshot_names_missing_from_remote_set(self):
        folder = self.client.root / "screenshots" / "iphone" / "en"
        folder.mkdir(parents=True)
        (folder / "01-main-page.png").write_bytes(b"new main page")
        missing = folder / "02-verbs-original.png"
        missing.write_bytes(b"verbs")
        self.client.ensure_set = Mock(return_value={"id": "set-en"})
        self.client.api.collection.return_value = [{
            "attributes": {"fileName": "01-main-page.png", "fileSize": 1}
        }]
        self.client.upload_asset = Mock()

        self.client.media({"en-US": {"id": "localization-en"}})

        self.client.upload_asset.assert_called_once_with(
            "set-en", "screenshot", missing, existing_names={"01-main-page.png"}
        )

    def test_upload_asset_treats_filename_as_existing_when_size_changed(self):
        screenshot = self.client.root / "01-main-page.png"
        screenshot.write_bytes(b"replacement with a different size")
        self.client.api.collection.return_value = [{
            "attributes": {"fileName": screenshot.name, "fileSize": 1}
        }]

        self.client.upload_asset("set-en", "screenshot", screenshot)

        self.client.api.mutate.assert_not_called()


    def _folder_with(self, count):
        folder = self.client.root / "screenshots" / "iphone" / "en"
        folder.mkdir(parents=True)
        for number in range(count):
            (folder / f"local-{number:02}.png").write_bytes(bytes([number]))
        self.client.ensure_set = Mock(return_value={"id": "set-en"})
        self.client.upload_asset = Mock(return_value=True)

    def test_skips_upload_when_remote_set_already_has_ten_screenshots(self):
        self._folder_with(10)
        self.client.api.collection.return_value = [
            {"attributes": {"fileName": f"remote-{n}.png"}} for n in range(10)
        ]

        self.client.media({"en-US": {"id": "localization-en"}})

        self.client.upload_asset.assert_not_called()

    def test_uploads_only_into_remaining_free_slots(self):
        self._folder_with(5)
        self.client.api.collection.return_value = [
            {"attributes": {"fileName": f"remote-{n}.png"}} for n in range(8)
        ]

        self.client.media({"en-US": {"id": "localization-en"}})

        self.assertEqual(
            [call.args[2].name for call in self.client.upload_asset.call_args_list],
            ["local-00.png", "local-01.png"],
        )

    def test_unnamed_remote_assets_count_toward_limit(self):
        self._folder_with(3)
        self.client.api.collection.return_value = [{"attributes": {}} for _ in range(10)]

        self.client.media({"en-US": {"id": "localization-en"}})

        self.client.upload_asset.assert_not_called()

    def test_upload_asset_returns_false_when_apple_reports_full_set(self):
        screenshot = self.client.root / "01.png"
        screenshot.write_bytes(b"x")
        self.client.journal = {"assets": {}}
        self.client.api.dry_run = False
        body = json.dumps({"errors": [{"code": "STATE_ERROR.SCREENSHOT_TOO_MANY"}]})
        self.client.api.mutate.side_effect = deploy.APIRequestError("POST", "url", 409, body)

        self.assertFalse(self.client.upload_asset("set-en", "screenshot", screenshot))

class ScreenshotLimitErrorTests(unittest.TestCase):
    def test_screenshot_limit_conflict_is_recognized(self):
        body = json.dumps({"errors": [{"code": "STATE_ERROR.SCREENSHOT_TOO_MANY"}]})
        error = deploy.APIRequestError("POST", "url", 409, body)
        self.assertTrue(error.screenshot_too_many())


if __name__ == "__main__":
    unittest.main()
