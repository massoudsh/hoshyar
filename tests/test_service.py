from datetime import datetime, timedelta, timezone
import unittest

from hoshyar import HoshyarService
from hoshyar.intent import extract_intent


NOW = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)


class HoshyarServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = HoshyarService()
        self.office = self.service.create_tenant("املاک آفتاب")
        self.agent = self.service.add_agent(self.office.id, "سارا")

    def test_pilot_is_limited_to_five_offices(self) -> None:
        self.service.enroll_pilot(self.office.id)
        for index in range(4):
            self.service.enroll_pilot(self.service.create_tenant(f"دفتر {index}").id)
        sixth = self.service.create_tenant("دفتر ششم")
        with self.assertRaisesRegex(ValueError, "limited to 5"):
            self.service.enroll_pilot(sixth.id)

    def test_ingestion_combines_channels_and_extracts_intent(self) -> None:
        lead = self.service.ingest_message(
            self.office.id, "09120000000", "برای خرید فوری در پونک تا ۸ میلیارد می‌خوام",
            "telegram", sent_at=NOW, name="مینا",
        )
        same_lead = self.service.ingest_message(
            self.office.id, "09120000000", "آیا فایل مناسب دارید؟", "whatsapp", sent_at=NOW,
        )
        self.assertEqual(lead.id, same_lead.id)
        self.assertEqual(lead.intent.purpose, "buy")
        self.assertEqual(lead.intent.price, 8_000_000_000)
        self.assertEqual(lead.intent.neighborhood, "پونک")
        self.assertEqual(lead.intent.urgency, "high")
        self.assertEqual(len(lead.messages), 2)

    def test_manager_dashboard_flags_overdue_unanswered_leads(self) -> None:
        lead = self.service.ingest_message(
            self.office.id, "09120000000", "اجاره در ونک", "sms", sent_at=NOW - timedelta(hours=25)
        )
        dashboard = self.service.dashboard(self.office.id, now=NOW)
        self.assertEqual(dashboard["at_risk_leads"][0]["id"], lead.id)
        self.assertEqual(dashboard["unassigned_leads"][0]["id"], lead.id)

    def test_agent_reply_removes_lead_from_at_risk(self) -> None:
        lead = self.service.ingest_message(
            self.office.id, "09120000000", "خرید در پونک", "telegram", sent_at=NOW - timedelta(hours=25)
        )
        self.service.ingest_message(
            self.office.id, "09120000000", "چند فایل مناسب دارم", "telegram", "outbound", NOW, self.agent.id
        )
        self.assertEqual(self.service.dashboard(self.office.id, now=NOW)["at_risk_leads"], [])
        self.assertEqual(lead.assigned_agent_id, self.agent.id)

    def test_followup_queue_orders_late_leads_first_and_skips_answered_ones(self) -> None:
        overdue = self.service.ingest_message(
            self.office.id, "0911", "خرید در پونک تا ۸ میلیارد", "telegram", sent_at=NOW - timedelta(hours=80)
        )
        fresh = self.service.ingest_message(
            self.office.id, "0912", "اجاره در ونک", "sms", sent_at=NOW - timedelta(hours=2)
        )
        answered = self.service.ingest_message(
            self.office.id, "0913", "سلام", "sms", sent_at=NOW - timedelta(hours=90)
        )
        self.service.ingest_message(
            self.office.id, "0913", "در خدمتم", "sms", "outbound", NOW - timedelta(hours=89), self.agent.id
        )
        assigned = self.service.ingest_message(
            self.office.id, "0914", "خرید فوری در ونک", "sms", sent_at=NOW, agent_id=self.agent.id
        )
        self.service.add_listing(self.office.id, "پونکی", "پونک", 2, price=7_000_000_000)

        queue = self.service.followups(self.office.id, now=NOW)
        self.assertEqual([item["lead"]["id"] for item in queue[:2]], [overdue.id, fresh.id])
        self.assertEqual(queue[0]["bucket"], "critical")
        self.assertEqual(queue[0]["match_count"], 1)
        self.assertEqual(queue[1]["bucket"], "unassigned")
        self.assertIn(assigned.id, [item["lead"]["id"] for item in queue])
        self.assertNotIn(answered.id, [item["lead"]["id"] for item in queue])

        only_mine = self.service.followups(self.office.id, agent_id=self.agent.id, now=NOW)
        self.assertEqual([item["lead"]["id"] for item in only_mine], [assigned.id])

    def test_listing_can_be_edited_and_deleted_within_its_tenant(self) -> None:
        listing = self.service.add_listing(self.office.id, "دوخوابه", "ونک", 2, price=5_000_000_000)
        edited = self.service.update_listing(self.office.id, listing.id, price=4_500_000_000)
        self.assertEqual(edited.price, 4_500_000_000)
        self.assertEqual(edited.title, "دوخوابه")
        self.assertIsNotNone(edited.updated_at)

        with self.assertRaisesRegex(ValueError, "deposit or a monthly rent"):
            self.service.update_listing(self.office.id, listing.id, deal_type="rent")
        with self.assertRaisesRegex(ValueError, "only a sale price"):
            self.service.update_listing(self.office.id, listing.id, deposit=100_000_000)
        with self.assertRaisesRegex(ValueError, "positive"):
            self.service.update_listing(self.office.id, listing.id, price=-1)

        other = self.service.create_tenant("املاک دیگر")
        with self.assertRaisesRegex(ValueError, "cross-tenant"):
            self.service.delete_listing(other.id, listing.id)
        self.service.delete_listing(self.office.id, listing.id)
        self.assertNotIn(listing.id, self.service.listings)
        with self.assertRaisesRegex(ValueError, "unknown listing"):
            self.service.delete_listing(self.office.id, listing.id)

    def test_stale_listings_are_oldest_first_and_tenant_scoped(self) -> None:
        old = self.service.add_listing(self.office.id, "قدیمی", "ونک", 1, price=1_000_000_000)
        fresh = self.service.add_listing(self.office.id, "تازه", "ونک", 1, price=2_000_000_000)
        old.updated_at = NOW - timedelta(days=40)
        fresh.updated_at = NOW - timedelta(days=2)
        other = self.service.create_tenant("املاک دیگر")
        foreign = self.service.add_listing(other.id, "دیگری", "ونک", 1, price=1_000_000_000)
        foreign.updated_at = NOW - timedelta(days=90)

        stale = self.service.stale_listings(self.office.id, days=14, now=NOW)
        self.assertEqual([item["listing"].id for item in stale], [old.id])
        self.assertEqual(stale[0]["age_days"], 40.0)

    def test_matching_and_competitive_pricing_alerts_are_tenant_scoped(self) -> None:
        lead = self.service.ingest_message(
            self.office.id, "09120000000", "برای خرید در پونک تا ۸ میلیارد", "divar", sent_at=NOW
        )
        match = self.service.add_listing(self.office.id, "دوخوابه پونک", "پونک", 2, price=7_500_000_000)
        self.service.add_listing(self.office.id, "نمونه یک", "پونک", 2, price=12_000_000_000)
        self.service.add_listing(self.office.id, "نمونه دو", "پونک", 2, price=11_000_000_000)
        other = self.service.create_tenant("املاک دیگر")
        self.service.add_listing(other.id, "فایل دیگر", "پونک", 2, price=1_000_000_000)

        self.assertEqual(self.service.matching_listings(self.office.id, lead.id)[0]["listing"].id, match.id)
        self.assertEqual(self.service.pricing_alerts(self.office.id)[0]["listing"].id, match.id)

    def test_rental_lead_matches_only_affordable_rentals(self) -> None:
        lead = self.service.ingest_message(
            self.office.id, "09120000000",
            "برای اجاره در ونک تا ۳۰۰ میلیون رهن و ۲۰ میلیون اجاره می‌خوام", "whatsapp", sent_at=NOW,
        )
        self.assertEqual(lead.intent.deposit, 300_000_000)
        self.assertEqual(lead.intent.rent, 20_000_000)
        self.assertIsNone(lead.intent.price)

        too_expensive = self.service.add_listing(
            self.office.id, "رهن بالا", "ونک", 1, deal_type="rent", deposit=500_000_000, rent=15_000_000
        )
        affordable = self.service.add_listing(
            self.office.id, "مناسب", "ونک", 1, deal_type="rent", deposit=250_000_000, rent=18_000_000
        )
        rental_miss = self.service.add_listing(
            self.office.id, "اجاره گران", "ونک", 1, deal_type="rent", deposit=250_000_000, rent=30_000_000
        )
        sale_in_same_neighborhood = self.service.add_listing(
            self.office.id, "فروش", "ونک", 1, price=2_000_000_000
        )

        matched = [match["listing"].id for match in self.service.matching_listings(self.office.id, lead.id)]
        self.assertEqual(matched, [affordable.id])
        self.assertNotIn(too_expensive.id, matched)
        self.assertNotIn(rental_miss.id, matched)
        self.assertNotIn(sale_in_same_neighborhood.id, matched)

    def test_buy_lead_never_matches_a_rental_listing(self) -> None:
        lead = self.service.ingest_message(
            self.office.id, "09120000000", "برای خرید در ونک تا ۸ میلیارد", "telegram", sent_at=NOW
        )
        self.service.add_listing(self.office.id, "اجاره ونک", "ونک", 1, deal_type="rent", deposit=100_000_000, rent=10_000_000)
        purchase = self.service.add_listing(self.office.id, "خرید ونک", "ونک", 1, price=7_000_000_000)

        matched = [match["listing"].id for match in self.service.matching_listings(self.office.id, lead.id)]
        self.assertEqual(matched, [purchase.id])

    def test_rental_listing_requires_an_amount_and_sale_rejects_rent(self) -> None:
        with self.assertRaisesRegex(ValueError, "deposit or a monthly rent"):
            self.service.add_listing(self.office.id, "خالی", "ونک", 1, deal_type="rent")
        with self.assertRaisesRegex(ValueError, "only a sale price"):
            self.service.add_listing(self.office.id, "ناقص", "ونک", 1, price=1_000, deposit=1_000)
        with self.assertRaisesRegex(ValueError, "deal_type"):
            self.service.add_listing(self.office.id, "نامعتبر", "ونک", 1, deal_type="swap")

    def test_pricing_alerts_do_not_mix_rental_and_sale_prices(self) -> None:
        self.service.add_listing(self.office.id, "رهن کم", "ونک", 1, deal_type="rent", deposit=20_000_000)
        self.service.add_listing(self.office.id, "رهن زیاد ۱", "ونک", 1, deal_type="rent", deposit=400_000_000)
        self.service.add_listing(self.office.id, "رهن زیاد ۲", "ونک", 1, deal_type="rent", deposit=420_000_000)
        self.service.add_listing(self.office.id, "فروش", "ونک", 1, price=100_000_000)

        alerts = self.service.pricing_alerts(self.office.id)
        self.assertEqual([alert["listing"].title for alert in alerts], [])

    def test_measurement_performance_and_referrals(self) -> None:
        lead = self.service.ingest_message(
            self.office.id, "09120000000", "فروش ملک در نیاوران", "instagram", sent_at=NOW
        )
        self.service.ingest_message(
            self.office.id, "09120000000", "تماس می‌گیرم", "instagram", "outbound", NOW + timedelta(hours=2), self.agent.id
        )
        self.service.mark_converted(self.office.id, lead.id)
        self.service.set_baseline(self.office.id, response_hours=4, conversion_rate=0.2)
        report = self.service.measurement_report(self.office.id)
        performance = self.service.agent_performance(self.office.id)
        referred = self.service.create_tenant("املاک معرفی‌شده")
        self.service.record_referral(self.office.id, referred.id)

        self.assertEqual(report["current"]["response_hours"], 2)
        self.assertEqual(report["change"]["response_hours"], -2)
        self.assertEqual(performance[0]["conversion_rate"], 1.0)
        self.assertIn(referred.id, self.service.referrals[self.office.id])

    def test_tenant_isolation_blocks_cross_tenant_agent_assignment(self) -> None:
        other = self.service.create_tenant("املاک دیگر")
        foreign_agent = self.service.add_agent(other.id, "علی")
        lead = self.service.ingest_message(self.office.id, "09120000000", "اجاره", "sms", sent_at=NOW)
        with self.assertRaisesRegex(ValueError, "cross-tenant"):
            self.service.assign_agent(self.office.id, lead.id, foreign_agent.id)


class IntentTests(unittest.TestCase):
    def test_intent_without_signals_is_low_confidence(self) -> None:
        self.assertEqual(extract_intent("سلام، اطلاعات می‌خواستم").confidence, 0)

    def test_rental_phrases_keep_deposit_and_rent_apart(self) -> None:
        cases = {
            "رهن کامل ۷۰۰ میلیون در ونک": (700_000_000, None),
            "اجاره ۱۲ میلیون با رهن ۲۰۰ میلیون": (200_000_000, 12_000_000),
            "می‌خوام تا ۶۰۰ میلیون رهن بدم و ۱۸ میلیون اجاره": (600_000_000, 18_000_000),
            "رهن ۵۰۰ میلیون، اجاره ۱۵ میلیون، در پونک": (500_000_000, 15_000_000),
            "اجاره تا ۲۰ میلیون، رهن ۳۰۰ میلیون": (300_000_000, 20_000_000),
            "برای اجاره در ونک تا ۳۰۰ میلیون رهن و ۲۰ میلیون اجاره": (300_000_000, 20_000_000),
        }
        for phrase, (deposit, rent) in cases.items():
            with self.subTest(phrase=phrase):
                intent = extract_intent(phrase)
                self.assertEqual((intent.deposit, intent.rent), (deposit, rent))
                self.assertIsNone(intent.price)

    def test_sale_phrase_sets_price_not_rent(self) -> None:
        intent = extract_intent("برای خرید فوری در پونک تا ۸ میلیارد می‌خوام")
        self.assertEqual(intent.price, 8_000_000_000)
        self.assertIsNone(intent.deposit)
        self.assertIsNone(intent.rent)


if __name__ == "__main__":
    unittest.main()
