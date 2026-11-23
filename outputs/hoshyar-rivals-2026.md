# Rival features, 2026 — what Hoshyar adopted

Research date: 23 November 2026. The goal is not to copy a marketplace; it is to give one office
the tools its advisors now expect after using these products.

| # | Feature in Hoshyar | Seen in | What the rival does | What Hoshyar does differently |
|---|---|---|---|---|
| 1 | Rahn ⇄ rent converter | Divar filing tools, Sheypoor agency tooling | Converts a deposit/rent mix into a single figure using the one-sixth convention | Same maths, but exposed next to the advisor's own files and quotable by API |
| 2 | Commission quote | Kilid agency tools, office practice | Shows the office fee for a deal | Split per side, with the rate stated explicitly so it can be handed to the buyer |
| 3 | Affordability engine | Zillow BuyAbility (Nov 2026) | Home budget from credit, debt and daily rates | Cash + income + profit rate → monthly payment; for rentals it shows the gap and the rent the cash affords |
| 4 | Saved searches with instant alerts | Zillow saved homes, Redfin alerts | New listings matching a saved search notify the buyer | A standing request is tied to a real lead, and the advisor sees whose request a new file satisfies |
| 5 | Viewing scheduling + reminders | Zillow tours, Kilid visits | Book a tour in-product | Booking must reference a real lead and a real file; 24-hour reminders sit on the follow-up desk |
| 6 | Persian reply drafting | Divar AI sales assistant (Oct 2025) | Negotiates and answers in chat on the marketplace | Drafts only from the extracted intent and real matches; an advisor reviews and records it |
| 7 | Neighbourhood price trend | Kilid price information, Zillow market data | External market averages | Built from the office's own files and their price-change history, with the change percent shown |
| 8 | Suspicious-price detection | Divar fraud controls, Zoomila comparison | Flags bait or inconsistent ads | Flags files far under peers and files whose sale price is below their own deposit |
| 9 | Freshness, verification and review queue | Divar "confirmed on site" (2025) | Verification badge on ads | Verification carries the advisor's identity, and freshness is a separate action from a price edit |
| 10 | Listing comparison and channel health | Zillow home comparison (Nov 2026) | Compares homes side by side | Price and rent per meter, freshness and verification, plus unanswered/conversion per source channel |

## Sources

- Zillow, "Zillow launches tools to help answer moving's hardest questions" (17 Nov 2026): <https://www.zillow.com/news/zillow-launches-tools-to-help-answer-movings-hardest-questions/>
- Zillow, "Zillow debuts AI mode" (25 Mar 2026): <https://www.zillow.com/news/zillow-debuts-ai-mode/>
- Real Estate News, "Zillow adds listing agent, home comparison tools" (17 Nov 2026): <https://www.realestatenews.com/2026/11/17/zillow-adds-listing-agent-home-comparison-tools-for-consumers>
- Divar newsroom: <https://divar.news/>
- ICTNA, "دیوار از دستیار فروش هوش مصنوعی با قابلیت چانه‌زنی خودکار رونمایی کرد" (Oct 2025): <https://ictna.ir/id/204877/>
- Living in Tehran, "Tehran Property Websites 2026: Divar, Sheypoor & More": <https://livingintehran.com/2022/03/13/top-websites-for-renting-and-buying-in-tehran>
- NVR Nexus, "AI in Real Estate: Search, Valuation and Property Management" (Jul 2026): <https://www.nvrnexus.com/blog/how-ai-is-changing-real-estate>

## Deliberate non-goals

- **Automatic negotiation on behalf of the office.** Divar's AI salesman bargains on a public ad;
  an office selling other owners' files needs an advisor in the loop.
- **AVM (automated valuation).** A defensible estimate needs comparables the office does not have
  yet; the trend and suspicious-price tools make the office's own evidence visible instead.
- **Virtual tours and mortgage pre-approval.** Both need partners (capture hardware, a lender) and
  are outside a stdlib-only pilot.
