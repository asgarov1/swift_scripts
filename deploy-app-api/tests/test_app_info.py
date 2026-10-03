import copy
import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import deploy_app_store as deploy


def info(ident, state, field="state"):
    return {"id": ident, "attributes": {field: state}}


class AppInfoTests(unittest.TestCase):
    def setUp(self):
        self.client = deploy.Deployer.__new__(deploy.Deployer)
        self.client.app = {"id": "app"}
        self.client.cfg = copy.deepcopy(deploy.EXAMPLE)
        self.client.api = Mock()

    def test_selects_draft_regardless_of_order_or_state_field(self):
        for field in ("state", "appStoreState"):
            draft = info("draft", "PREPARE_FOR_SUBMISSION", field)
            live = info("live", "READY_FOR_SALE", field)
            for records in ([live, draft], [draft, live], [draft]):
                with self.subTest(field=field, records=records):
                    self.client.api.collection.return_value = records
                    self.assertEqual(self.client.editable_app_info(), draft)

    def test_no_fallback_to_live_unknown_or_ambiguous_info(self):
        for records in ([], [info("live", "READY_FOR_DISTRIBUTION")],
                        [info("unknown", None)],
                        [info("a", "REJECTED"), info("b", "PREPARE_FOR_SUBMISSION")]):
            self.client.api.collection.return_value = records
            with self.assertRaises(deploy.DeployError):
                self.client.editable_app_info()
            self.client.api.mutate.assert_not_called()

    def test_current_state_takes_precedence_over_legacy_state(self):
        self.client.api.collection.return_value = [
            {"id": "live", "attributes": {"state": "READY_FOR_DISTRIBUTION", "appStoreState": "PREPARE_FOR_SUBMISSION"}}]
        with self.assertRaises(deploy.DeployError):
            self.client.editable_app_info()

    def test_category_and_localizations_use_draft(self):
        refreshed = [{"id": "new", "attributes": {"locale": "en-US"}}]
        version_reads = 0
        def collection(path):
            nonlocal version_reads
            if path == "/v1/apps/app/appInfos?limit=200":
                return [info("live", "READY_FOR_SALE"), info("draft", "PREPARE_FOR_SUBMISSION")]
            self.assertIn(path, ["/v1/appInfos/draft/appInfoLocalizations?limit=200",
                                 "/v1/appStoreVersions/v21/appStoreVersionLocalizations?limit=200"])
            if path == "/v1/appStoreVersions/v21/appStoreVersionLocalizations?limit=200":
                version_reads += 1
                if version_reads == 2:
                    return refreshed
            return []
        self.client.api.collection.side_effect = collection
        self.client.api.request.return_value = {"data": {"id": "OTHER"}}
        self.client.api.mutate.return_value = {"data": {"id": "new"}}
        self.client.ensure_primary_category()
        self.assertEqual(self.client.api.mutate.call_args.args[1], "/v1/appInfos/draft")
        self.client.upsert_localizations({"id": "v21"}, {"en-US": {"appInformation": {"name": "German A1"}}})
        calls = self.client.api.mutate.call_args_list
        self.assertEqual(calls[1].args[2]["data"]["relationships"]["appInfo"]["data"]["id"], "draft")
        self.assertEqual(calls[2].args[2]["data"]["relationships"]["appStoreVersion"]["data"]["id"], "v21")

    def test_bulgarian_is_reserved_for_product_localizations(self):
        refreshed = [{"id": "en", "attributes": {"locale": "en-US"}}]
        version_reads = 0

        def collection(path):
            nonlocal version_reads
            if path.endswith("/appInfoLocalizations?limit=200"):
                return []
            if path.endswith("/appStoreVersionLocalizations?limit=200"):
                version_reads += 1
                return refreshed if version_reads == 2 else []
            self.fail(f"unexpected collection path: {path}")

        self.client.editable_app_info = Mock(return_value={"id": "draft"})
        self.client.api.collection.side_effect = collection
        self.client.api.mutate.return_value = {"data": {"id": "en"}}
        locales = {
            "en-US": {"appInformation": {"name": "Jlingo German A1"}},
            "bg-BG": {"appInformation": {"name": "Jlingo German A1"}},
        }

        result = self.client.upsert_localizations({"id": "v21"}, locales)

        self.assertEqual(set(result), {"en-US"})
        posted_locales = [call.args[2]["data"]["attributes"]["locale"] for call in self.client.api.mutate.call_args_list]
        self.assertEqual(posted_locales, ["en-US", "en-US"])

    def test_existing_version_supports_current_state_field(self):
        version = {"id": "v21", "attributes": {"platform": "IOS", "versionString": "1.0", "appVersionState": "PREPARE_FOR_SUBMISSION"}}
        self.client.api.collection.return_value = [version]
        self.assertEqual(self.client.ensure_version(), version)
        self.client.api.mutate.assert_not_called()

    def test_latest_editable_version_uses_numeric_order_and_platform(self):
        def version(number, state="PREPARE_FOR_SUBMISSION", platform="IOS"):
            return {"id": number + platform, "attributes": {"versionString": number, "appVersionState": state, "platform": platform}}
        latest = version("3.10")
        records = [version("3.9"), version("8.0", "READY_FOR_DISTRIBUTION"), latest, version("9.0", platform="MAC_OS")]
        for ordered in (records, list(reversed(records))):
            self.client.api.collection.return_value = ordered
            self.assertEqual(self.client.ensure_version(), latest)
            self.assertEqual(self.client.build_coordinates()[1], "3.10")
        self.client.api.mutate.assert_not_called()

    def test_no_editable_version_creates_configured_release(self):
        self.client.api.collection.return_value = []
        self.client.api.mutate.return_value = {"data": {"id": "new"}}
        self.assertEqual(self.client.ensure_version(), {"id": "new"})
        self.assertFalse(self.client.version_is_update)
        self.assertEqual(self.client.api.mutate.call_args.args[2]["data"]["attributes"]["versionString"], "1.0")

    def test_existing_release_marks_new_version_as_update(self):
        self.client.api.collection.return_value = [
            {"id": "live", "attributes": {"platform": "IOS", "versionString": "1.0", "appVersionState": "READY_FOR_DISTRIBUTION"}}
        ]
        self.client.cfg["version"]["versionString"] = "2.0"
        self.client.api.mutate.return_value = {"data": {"id": "new"}}

        self.client.ensure_version()

        self.assertTrue(self.client.version_is_update)

    def test_update_localization_requires_whats_new(self):
        self.client.version_is_update = True
        self.client.editable_app_info = Mock(return_value={"id": "draft"})
        self.client.api.collection.side_effect = [[], []]

        with self.assertRaisesRegex(deploy.DeployError, "appStoreVersion.whatsNew is required"):
            self.client.upsert_localizations(
                {"id": "v2"},
                {"en-US": {"appInformation": {"name": "Jlingo German A1"}}},
            )

    def test_update_localization_maps_legacy_release_notes_to_whats_new(self):
        self.client.version_is_update = True
        self.client.editable_app_info = Mock(return_value={"id": "draft"})
        refreshed = [{"id": "en", "attributes": {"locale": "en-US"}}]
        self.client.api.collection.side_effect = [[], [], refreshed]
        self.client.api.mutate.return_value = {"data": {"id": "en"}}

        self.client.upsert_localizations(
            {"id": "v2"},
            {"en-US": {"appInformation": {"name": "Jlingo German A1", "releaseNotes": "Improved reliability."}}},
        )

        version_create = self.client.api.mutate.call_args_list[1]
        self.assertEqual(version_create.args[2]["data"]["attributes"]["whatsNew"], "Improved reliability.")

    def test_first_release_omits_whats_new(self):
        self.client.version_is_update = False
        self.client.editable_app_info = Mock(return_value={"id": "draft"})
        refreshed = [{"id": "en", "attributes": {"locale": "en-US"}}]
        self.client.api.collection.side_effect = [[], [], refreshed]
        self.client.api.mutate.return_value = {"data": {"id": "en"}}

        self.client.upsert_localizations(
            {"id": "v1"},
            {"en-US": {
                "appInformation": {"name": "Jlingo German A1"},
                "appStoreVersion": {"whatsNew": "Should not be sent."},
            }},
        )

        version_create = self.client.api.mutate.call_args_list[1]
        self.assertNotIn("whatsNew", version_create.args[2]["data"]["attributes"])

    def test_no_editable_version_does_not_duplicate_existing_release(self):
        self.client.api.collection.return_value = [{"id": "live", "attributes": {"platform": "IOS", "versionString": "1.0", "appVersionState": "READY_FOR_DISTRIBUTION"}}]
        with self.assertRaises(deploy.DeployError):
            self.client.ensure_version()
        self.client.api.mutate.assert_not_called()

    def test_explicit_build_version_must_match_selected_version(self):
        self.client.cfg["build"]["shortVersion"] = "1.0"
        self.client.api.collection.return_value = [{"id": "draft", "attributes": {"platform": "IOS", "versionString": "4.0", "appVersionState": "PREPARE_FOR_SUBMISSION"}}]
        with self.assertRaises(deploy.DeployError):
            self.client.ensure_version()
        self.client.api.mutate_editable_fields.assert_not_called()

    def test_version_is_created_before_category(self):
        events = []
        names = ("ensure_app", "ensure_age_ratings", "app_price", "app_availability", "uploaded_build", "prepare_ipa",
                 "ensure_version", "ensure_primary_category", "ensure_review_details", "locales",
                 "upsert_localizations", "media", "ensure_products", "upload_build", "save")
        for name in names:
            setattr(self.client, name, Mock(side_effect=lambda *args, name=name: events.append(name)))
        self.client.run()
        self.assertLess(events.index("ensure_version"), events.index("ensure_primary_category"))
        self.assertLess(events.index("ensure_version"), events.index("uploaded_build"))
        self.assertLess(events.index("ensure_version"), events.index("prepare_ipa"))


class ErrorTests(unittest.TestCase):
    def test_reported_error_does_not_retry(self):
        body = json.dumps({"errors": [{"code": "ENTITY_ERROR.ATTRIBUTE.INVALID.INVALID_STATE",
            "detail": "The field 'name' can not be modified in the current state.",
            "source": {"pointer": "/data/attributes/name"}}]})
        api = deploy.ASC(deploy.EXAMPLE, False)
        error = urllib.error.HTTPError(deploy.API, 409, "Conflict", {}, io.BytesIO(body.encode()))
        with patch.object(api, "token", return_value="test"), patch.object(deploy.urllib.request, "urlopen", side_effect=error) as request, patch.object(deploy.time, "sleep") as sleep:
            with self.assertRaises(deploy.APIRequestError) as caught:
                api.request("PATCH", "/v1/appInfoLocalizations/locale", {})
            self.assertEqual(caught.exception.unavailable_attribute(), "name")
            request.assert_called_once()
            sleep.assert_not_called()

    def test_unrelated_validation_error_is_not_a_locked_field(self):
        body = json.dumps({"errors": [{"code": "ENTITY_ERROR.ATTRIBUTE.INVALID", "source": {"pointer": "/data/attributes/name"}}]})
        self.assertIsNone(deploy.APIRequestError("PATCH", "url", 409, body).unavailable_attribute())

    def test_invalid_attribute_value_does_not_retry(self):
        body = json.dumps({"errors": [{"code": "ENTITY_ERROR.ATTRIBUTE.INVALID",
            "source": {"pointer": "/data/attributes/locale"}}]})
        api = deploy.ASC(deploy.EXAMPLE, False)
        error = urllib.error.HTTPError(deploy.API, 409, "Conflict", {}, io.BytesIO(body.encode()))
        with patch.object(api, "token", return_value="test"), patch.object(deploy.urllib.request, "urlopen", side_effect=error) as request, patch.object(deploy.time, "sleep") as sleep:
            with self.assertRaises(deploy.APIRequestError):
                api.request("POST", "/v1/appInfoLocalizations", {})
            request.assert_called_once()
            sleep.assert_not_called()

    def test_legacy_state_error_is_still_recognized(self):
        body = json.dumps({"errors": [{"code": "STATE_ERROR", "detail": "Attribute 'name' cannot be edited at this time"}]})
        self.assertEqual(deploy.APIRequestError("PATCH", "url", 409, body).unavailable_attribute(), "name")


if __name__ == "__main__":
    unittest.main()
