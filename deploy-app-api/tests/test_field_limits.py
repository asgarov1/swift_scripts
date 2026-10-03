import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import deploy_app_store as deploy


class TextLimitValidationTests(unittest.TestCase):
    def setUp(self):
        self.client = deploy.Deployer.__new__(deploy.Deployer)
        self.client.cfg = copy.deepcopy(deploy.EXAMPLE)
        self.client.cfg["purchases"]["inAppPurchases"] = [{"productId": "life"}]

    def locales(self, **products):
        return {"en-US": {"appInformation": {"name": "Jlingo German A1"}, "subscriptions": products}}

    def test_valid_text_passes(self):
        self.client.validate_text_limits(self.locales(month={"displayName": "Monthly", "description": "x" * 55},
                                                      life={"displayName": "Lifetime", "description": "x" * 45}))

    def test_over_long_text_is_reported_not_truncated(self):
        locales = self.locales(month={"displayName": "Monthly", "description": "x" * 56},
                               life={"displayName": "Lifetime", "description": "y" * 46})
        before = copy.deepcopy(locales)
        with self.assertRaises(deploy.DeployError) as ctx:
            self.client.validate_text_limits(locales)
        self.assertIn("month.description: 56 > 55", str(ctx.exception))
        self.assertIn("life.description: 46 > 45", str(ctx.exception))
        self.assertEqual(locales, before)

    def test_unsupported_locales_are_ignored(self):
        locales = self.locales()
        locales["bg-BG"] = {"appInformation": {"name": "x" * 99}}
        self.client.validate_text_limits(locales)


class TooLongResponseTests(unittest.TestCase):
    RESPONSE = json.dumps({"errors": [{
        "status": "409", "code": "ENTITY_ERROR.ATTRIBUTE.INVALID",
        "detail": "The field 'description' is too long. Max number of characters is 55.",
        "source": {"pointer": "/data/attributes/description"},
    }]})

    def test_error_is_parsed(self):
        error = deploy.APIRequestError("POST", "u", 409, self.RESPONSE)
        self.assertEqual(error.too_long_attribute(), ("description", 55))

    def test_mutate_does_not_retry_with_truncated_text(self):
        api = deploy.ASC.__new__(deploy.ASC)
        api.dry_run = False
        api.request = Mock(side_effect=deploy.APIRequestError("POST", "u", 409, self.RESPONSE))
        text = "z " * 30
        body = deploy.data("subscriptionLocalizations", {"locale": "pt-PT", "name": "x", "description": text})
        with self.assertRaises(deploy.DeployError) as ctx:
            api.mutate("POST", "/v2/subscriptionLocalizations", body)
        self.assertIn("do not truncate", str(ctx.exception))
        self.assertEqual(api.request.call_count, 1)
        self.assertEqual(body["data"]["attributes"]["description"], text)


if __name__ == "__main__":
    unittest.main()
