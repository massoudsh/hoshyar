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
        self.assertEqual(lead.intent.budget, 8_000_000_000)
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

    def test_matching_and_competitive_pricing_alerts_are_tenant_scoped(self) -> None:
        lead = self.service.ingest_message(
            self.office.id, "09120000000", "برای خرید در پونک تا ۸ میلیارد", "divar", sent_at=NOW
        )
        match = self.service.add_listing(self.office.id, "دوخوابه پونک", "پونک", 7_500_000_000, 2)
        self.service.add_listing(self.office.id, "نمونه یک", "پونک", 12_000_000_000, 2)
        self.service.add_listing(self.office.id, "نمونه دو", "پونک", 11_000_000_000, 2)
        other = self.service.create_tenant("املاک دیگر")
        self.service.add_listing(other.id, "فایل دیگر", "پونک", 1_000_000_000, 2)

        self.assertEqual(self.service.matching_listings(self.office.id, lead.id)[0]["listing"].id, match.id)
        self.assertEqual(self.service.pricing_alerts(self.office.id)[0]["listing"].id, match.id)

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


if __name__ == "__main__":
    unittest.main()
