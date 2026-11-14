import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import deploy_app_store as deploy


def point(ident, territory=None):
    result = {"id": ident, "attributes": {"customerPrice": "4.99"}}
    if territory:
        result["relationships"] = {"territory": deploy.relationship("territories", territory)}
    return result


class PricingTests(unittest.TestCase):
    def setUp(self):
        self.client = deploy.Deployer.__new__(deploy.Deployer)
        self.client.cfg = {}
        self.client.app = {"id": "app"}
        self.client.api = Mock(dry_run=False)
        self.client.subscription_availability = Mock()
        self.client.iap_availability = Mock()
        self.client._territory_links = [{"type": "territories", "id": t} for t in ("AUT", "USA", "CAN")]
        self.existing = []
        self.equalizations = [point("aut", "AUT"), point("can", "CAN")]
        self.written = []
        self.persist = True

        def collection(path):
            if "/prices?" in path:
                return self.existing + (self.written if self.persist else [])
            if "/pricePoints?" in path or "/appPricePoints?" in path:
                self.assertIn("filter[territory]=" + self.client.cfg.get("pricing", {}).get("baseTerritory", "USA"), path)
                return [point("base")]
            if "/equalizations?" in path:
                return self.equalizations
            self.fail("Unexpected collection: " + path)

        def mutate(method, path, body):
            self.assertEqual((method, path), ("POST", "/v1/subscriptionPrices"))
            ident = body["data"]["relationships"]["subscriptionPricePoint"]["data"]["id"]
            territory = self.client.cfg.get("pricing", {}).get("baseTerritory", "USA") if ident == "base" else ident.upper()
            self.written.append(point(ident, territory))

        self.client.api.collection.side_effect = collection
        self.client.api.mutate.side_effect = mutate

    def run_price(self):
        self.client.subscription_price({"id": "sub"}, {"price": 4.99})

    def test_base_without_territory_relationship_is_written(self):
        self.run_price()
        self.assertEqual({p["id"] for p in self.written}, {"base", "aut", "can"})
        self.assertEqual(len(self.written), 3)
        self.client.api.mutate.reset_mock()
        self.run_price()
        self.client.api.mutate.assert_not_called()

    def test_austria_base_and_duplicate_equalization(self):
        self.client.cfg = {"pricing": {"baseTerritory": "AUT"}}
        self.equalizations = [point("usa", "USA"), point("can", "CAN"), point("aut", "AUT"), point("can", "CAN")]
        self.run_price()
        self.assertEqual({p["id"] for p in self.written}, {"base", "usa", "can"})
        self.assertEqual(len(self.written), 3)

    def test_existing_prices_preserved_and_base_repaired(self):
        self.existing = [point("old-aut", "AUT"), point("old-can", "CAN")]
        self.run_price()
        self.assertEqual([p["id"] for p in self.written], ["base"])

    def test_incomplete_equalizations_fail_before_price_writes(self):
        self.equalizations = [point("aut", "AUT")]
        with self.assertRaisesRegex(deploy.DeployError, "no equalized price.*CAN"):
            self.run_price()
        self.client.api.mutate.assert_not_called()

    def test_missing_prices_after_write_reported(self):
        self.persist = False
        with self.assertRaisesRegex(deploy.DeployError, "still missing in: AUT, CAN, USA"):
            self.run_price()

    def test_base_defaults_overrides_and_validation(self):
        self.assertEqual(self.client.base_territory({}), "USA")
        self.client.cfg = {"pricing": {"baseTerritory": "AUT"}}
        self.assertEqual(self.client.base_territory({}), "AUT")
        self.assertEqual(self.client.base_territory({"baseTerritory": "CAN"}), "CAN")
        with self.assertRaisesRegex(deploy.DeployError, "Invalid pricing baseTerritory"):
            self.client.base_territory({"baseTerritory": "AT"})

    def test_app_and_iap_schedules_use_austria(self):
        self.client.cfg = {"pricing": {"baseTerritory": "AUT"}, "app": {"price": 4.99}}
        self.client.api.request.return_value = None
        self.client.api.mutate.side_effect = None
        self.client.app_price()
        self.client.iap_price({"id": "iap"}, {"price": 4.99})
        for call in self.client.api.mutate.call_args_list:
            self.assertEqual(call.args[2]["data"]["relationships"]["baseTerritory"]["data"]["id"], "AUT")
        self.assertEqual(self.client.api.mutate.call_count, 2)


if __name__ == "__main__":
    unittest.main()
