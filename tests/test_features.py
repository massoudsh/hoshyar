import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hoshyar import features
from hoshyar.api import HoshyarApi
from hoshyar.service import HoshyarService
from hoshyar.store import SqliteStore


NOW = datetime(2026, 11, 23, 12, tzinfo=timezone.utc)


class RahnToolsTests(unittest.TestCase):
    def test_rahn_equivalent_and_both_conversions(self) -> None:
        result = features.convert_rahn(300_000_000, 18_000_000)
        self.assertEqual(result["rahn_equivalent"], 408_000_000)
        self.assertEqual(result["rent_if_deposit_is_zero"], 68_000_000)
        self.assertEqual(result["deposit_if_rent_is_zero"], 408_000_000)

    def test_moving_the_deposit_moves_the_rent_by_one_sixth(self) -> None:
        result = features.convert_rahn(300_000_000, 18_000_000, target_deposit=408_000_000)
        self.assertEqual(result["rent"], 0)
        result = features.convert_rahn(300_000_000, 18_000_000, target_deposit=108_000_000)
        self.assertEqual(result["rent"], 50_000_000)

    def test_both_targets_or_bad_amounts_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            features.convert_rahn(1, 1, target_deposit=1, target_rent=1)
        with self.assertRaises(ValueError):
            features.convert_rahn(-1, 1)


class CommissionTests(unittest.TestCase):
    def test_sale_commission_is_split_between_both_sides(self) -> None:
        quote = features.commission("sale", price=20_000_000_000)
        self.assertEqual(quote["per_side"], 50_000_000)
        self.assertEqual(quote["total"], 100_000_000)

    def test_rent_commission_is_a_quarter_from_each_side(self) -> None:
        quote = features.commission("rent", deposit=500_000_000, rent=40_000_000)
        self.assertEqual(quote["per_side"], 10_000_000)
        self.assertEqual(quote["total"], 20_000_000)

    def test_missing_amounts_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            features.commission("sale")
        with self.assertRaises(ValueError):
            features.commission("rent", deposit=1_000_000)


class AffordabilityTests(unittest.TestCase):
    def test_sale_budget_prices_the_financed_part(self) -> None:
        result = features.affordability(max_price=10_000_000_000, savings=4_000_000_000, monthly_income=200_000_000)
        self.assertEqual(result["financed"], 6_000_000_000)
        self.assertEqual(result["monthly_payment"], 115_000_000)

    def test_rental_budget_shows_the_gap_and_the_rent_that_fits(self) -> None:
        result = features.affordability(deal_type="rent", max_deposit=300_000_000, max_rent=20_000_000, savings=160_000_000)
        self.assertEqual(result["deposit_gap"], 140_000_000)
        # 420M equivalent minus 160M of cash leaves 260M of rent-equivalent.
        self.assertEqual(result["rent_with_savings"], 43_333_333)


class TrendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = HoshyarService()
        self.tenant = self.service.create_tenant("دفتر")

    def test_a_price_drop_moves_the_history_but_not_the_past_month(self) -> None:
        listing = self.service.add_listing(
            self.tenant.id, "ونک", "ونک", 2, deal_type="sale", price=10_000_000_000
        )
        listing.created_at = datetime(2026, 8, 10, tzinfo=timezone.utc)
        listing.price_history = [{"at": listing.created_at, "price": 10_000_000_000}]
        self.service.update_listing(self.tenant.id, listing.id, price=8_000_000_000)
        # Pin the change to this month instead of "now" so the assertion is stable.
        listing.price_history[-1]["at"] = datetime(2026, 11, 20, tzinfo=timezone.utc)

        trend = features.price_trend([listing], self.tenant.id, months=4, now=NOW)
        by_month = {point["month"]: point["average"] for point in trend["points"]}
        self.assertEqual(by_month["2026-08"], 10_000_000_000)
        self.assertEqual(by_month["2026-11"], 8_000_000_000)
        self.assertEqual(trend["change_percent"], -20.0)

    def test_months_without_files_are_omitted(self) -> None:
        listing = self.service.add_listing(self.tenant.id, "ونک", "ونک", 2, deal_type="sale", price=9_000_000_000)
        listing.created_at = datetime(2026, 11, 1, tzinfo=timezone.utc)
        trend = features.price_trend([listing], self.tenant.id, months=6, now=NOW)
        self.assertEqual([point["month"] for point in trend["points"]], ["2026-11"])


class SavedSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = HoshyarService()
        self.tenant = self.service.create_tenant("دفتر")

    def test_a_new_listing_alerts_every_matching_saved_search(self) -> None:
        lead = self.service.ingest_message(self.tenant.id, "0912", "خرید در ونک تا ۱۰ میلیارد", "manual")
        search = self.service.add_saved_search(
            self.tenant.id, "خرید ونک", "sale", max_price=10_000_000_000, neighborhood="ونک", lead_id=lead.id
        )
        listing = self.service.add_listing(self.tenant.id, "ونک", "ونک", 2, price=9_500_000_000)
        too_expensive = self.service.add_listing(self.tenant.id, "ونک", "ونک", 2, price=12_000_000_000)

        alerts = self.service.new_listing_alerts(listing.id)
        self.assertEqual([alert["search"].id for alert in alerts], [search.id])
        self.assertEqual(alerts[0]["lead_contact"], "0912")
        self.assertEqual(self.service.new_listing_alerts(too_expensive.id), [])

    def test_a_sale_search_cannot_carry_rent_and_a_rental_search_needs_an_amount(self) -> None:
        with self.assertRaises(ValueError):
            self.service.add_saved_search(self.tenant.id, "x", "sale", max_price=1, max_rent=1)
        with self.assertRaises(ValueError):
            self.service.add_saved_search(self.tenant.id, "y", "rent")


class ViewingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = HoshyarService()
        self.tenant = self.service.create_tenant("دفتر")
        self.agent = self.service.add_agent(self.tenant.id, "سارا")
        self.lead = self.service.ingest_message(self.tenant.id, "0912", "اجاره در ونک", "manual", name="مینا")
        self.listing = self.service.add_listing(self.tenant.id, "ونک", "ونک", 2, deal_type="rent", rent=20_000_000)

    def test_a_viewing_within_the_window_is_reminded_once(self) -> None:
        self.service.schedule_viewing(
            self.tenant.id, self.lead.id, self.listing.id,
            NOW + timedelta(hours=3), agent_id=self.agent.id,
        )
        self.service.schedule_viewing(
            self.tenant.id, self.lead.id, self.listing.id, NOW + timedelta(days=3)
        )
        reminders = self.service.reminders(self.tenant.id, now=NOW)
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0]["lead_name"], "مینا")
        self.assertEqual(reminders[0]["agent_name"], "سارا")

    def test_a_cancelled_viewing_is_not_reminded(self) -> None:
        viewing = self.service.schedule_viewing(
            self.tenant.id, self.lead.id, self.listing.id, NOW + timedelta(hours=2)
        )
        self.service.update_viewing(self.tenant.id, viewing.id, "cancelled")
        self.assertEqual(self.service.reminders(self.tenant.id, now=NOW), [])

    def test_a_viewing_across_offices_is_refused(self) -> None:
        other = self.service.create_tenant("دفتر دیگر")
        with self.assertRaises(ValueError):
            self.service.schedule_viewing(other.id, self.lead.id, self.listing.id, NOW)


class DraftTests(unittest.TestCase):
    def test_the_draft_quotes_only_what_the_lead_said(self) -> None:
        service = HoshyarService()
        tenant = service.create_tenant("دفتر")
        lead = service.ingest_message(tenant.id, "0912", "خرید فوری در پونک تا ۸ میلیارد", "manual", name="رضا")
        service.add_listing(tenant.id, "پونک", "پونک", 2, price=7_500_000_000)
        draft = service.followup_draft(tenant.id, lead.id)["text"]
        self.assertIn("رضا عزیز", draft)
        self.assertIn("خرید", draft)
        self.assertIn("پونک", draft)
        self.assertIn("۸ میلیارد", draft)
        self.assertIn("عجله", draft)
        self.assertIn("یک فایل مناسب", draft)

class ListingQualityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = HoshyarService()
        self.tenant = self.service.create_tenant("دفتر")
        self.agent = self.service.add_agent(self.tenant.id, "سارا")

    def test_suspicious_prices_catch_a_bait_listing(self) -> None:
        for price in (10_000_000_000, 11_000_000_000, 12_000_000_000):
            self.service.add_listing(self.tenant.id, "ونک", "ونک", 2, price=price)
        cheap = self.service.add_listing(self.tenant.id, "ونک", "ونک", 2, price=3_000_000_000)
        findings = self.service.suspicious_listings(self.tenant.id)
        self.assertEqual([finding["listing"].id for finding in findings], [cheap.id])
        self.assertGreaterEqual(findings[0]["discount_percent"], 60)

    def test_a_sale_price_below_its_own_deposit_is_flagged(self) -> None:
        listing = self.service.add_listing(self.tenant.id, "ونک", "ونک", 2, deal_type="rent", deposit=500_000_000, rent=1)
        listing.price = 100_000_000  # impossible mix, left over from an import
        findings = self.service.suspicious_listings(self.tenant.id)
        self.assertEqual(findings[0]["reason"], "sale price below its own deposit")

    def test_verify_and_touch_keep_freshness_real(self) -> None:
        listing = self.service.add_listing(self.tenant.id, "ونک", "ونک", 2, price=9_000_000_000)
        listing.updated_at = NOW - timedelta(days=30)
        listing.created_at = listing.updated_at
        self.assertEqual(len(self.service.review_queue(self.tenant.id, days=14)), 1)

        self.service.touch_listing(self.tenant.id, listing.id)
        self.assertEqual(features.freshness_days(listing), 0)
        self.assertEqual(self.service.review_queue(self.tenant.id, days=14), [])

        self.service.verify_listing(self.tenant.id, listing.id, self.agent.id)
        self.assertEqual(listing.verified_by, self.agent.id)

    def test_compare_shows_price_per_meter_between_two_and_four_files(self) -> None:
        first = self.service.add_listing(self.tenant.id, "الف", "ونک", 2, price=8_000_000_000, area=100)
        second = self.service.add_listing(self.tenant.id, "ب", "ونک", 3, price=9_000_000_000, area=120)
        rows = self.service.compare_listings(self.tenant.id, [first.id, second.id])
        self.assertEqual([row["price_per_meter"] for row in rows], [80_000_000, 75_000_000])
        with self.assertRaises(ValueError):
            self.service.compare_listings(self.tenant.id, [first.id])

    def test_source_health_counts_the_channel_that_brought_the_lead(self) -> None:
        self.service.ingest_message(self.tenant.id, "1", "خرید در ونک", "divar")
        self.service.ingest_message(self.tenant.id, "2", "خرید در پونک", "divar")
        self.service.ingest_message(self.tenant.id, "3", "اجاره", "telegram")
        health = self.service.source_health(self.tenant.id)
        self.assertEqual(health["channels"][0]["channel"], "divar")
        self.assertEqual(health["channels"][0]["leads"], 2)
        self.assertEqual(health["channels"][0]["unanswered_rate"], 1.0)


class FeatureApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.store = SqliteStore(Path(self.temp.name) / "hoshyar.sqlite3")
        self.api = HoshyarApi(self.store, bootstrap_key="bootstrap-secret")
        status, response = self.api.handle(
            "POST", "/v1/tenants", {"x-bootstrap-key": "bootstrap-secret"}, json.dumps({"name": "دفتر"}).encode()
        )
        self.assertEqual(status, 201)
        self.tenant_id = response["tenant"]["id"]
        self.headers = {"x-api-key": response["api_key"]}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def call(self, method: str, path: str, payload: dict | None = None):
        return self.api.handle(method, path, self.headers, json.dumps(payload or {}).encode())

    def test_the_new_tools_round_trip_through_the_api(self) -> None:
        base = f"/v1/tenants/{self.tenant_id}"
        self.assertEqual(self.call("POST", f"{base}/convert-rahn", {"deposit": 300_000_000, "rent": 18_000_000})[0], 200)
        self.assertEqual(self.call("POST", f"{base}/commission", {"deal_type": "sale", "price": 10_000_000_000})[1]["total"], 50_000_000)
        self.assertEqual(self.call("POST", f"{base}/budget", {"deal_type": "rent", "max_rent": 20_000_000})[0], 200)

        _, lead = self.call("POST", f"{base}/messages", {"contact": "0912", "body": "خرید در ونک", "channel": "manual"})
        lead_id = lead["lead"]["id"]
        status, search = self.call("POST", f"{base}/saved-searches", {
            "name": "ونک", "deal_type": "sale", "max_price": 10_000_000_000, "lead_id": lead_id,
        })
        self.assertEqual(status, 201)
        status, listing = self.call("POST", f"{base}/listings", {
            "title": "ونک", "neighborhood": "ونک", "bedrooms": 2, "price": 9_000_000_000, "area": 90,
        })
        self.assertEqual(status, 201)
        self.assertEqual(len(listing["alerts"]), 1)
        listing_id = listing["listing"]["id"]

        self.assertEqual(self.call("GET", f"{base}/saved-searches/{search['saved_search']['id']}/matches")[1]["matches"][0]["listing"]["id"], listing_id)
        self.assertEqual(self.call("POST", f"{base}/listings/{listing_id}/touch")[0], 200)
        self.assertEqual(self.call("GET", f"{base}/market-trend?months=3")[0], 200)
        self.assertEqual(self.call("GET", f"{base}/suspicious-listings")[0], 200)
        self.assertEqual(self.call("GET", f"{base}/source-health")[1]["channels"][0]["channel"], "manual")
        self.assertEqual(self.call("GET", f"{base}/leads/{lead_id}/draft")[1]["lead_id"], lead_id)

        starts_at = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()
        status, viewing = self.call("POST", f"{base}/viewings", {
            "lead_id": lead_id, "listing_id": listing_id, "starts_at": starts_at,
        })
        self.assertEqual(status, 201)
        _, workspace = self.call("GET", f"{base}/workspace")
        self.assertEqual(len(workspace["reminders"]), 1)
        self.assertEqual(self.call("PATCH", f"{base}/viewings/{viewing['viewing']['id']}", {"status": "done"})[0], 200)

    def test_a_bad_budget_request_is_a_400(self) -> None:
        status, _ = self.call("POST", f"/v1/tenants/{self.tenant_id}/budget", {"deal_type": "sale"})
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
