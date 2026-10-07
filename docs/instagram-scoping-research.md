# Scoping Research: Instagram Giveaways as an Extension to the Radio Competition Enterer

**Prepared for:** Adán (personal project)
**Date:** 7 October 2026
**Stage:** Hypothesis research only. Nothing is built yet, and this follows the same pause-and-review gate the radio scoping went through.

## Why look at this at all

There are two reasons, one from you and one from the build log.

You see Instagram giveaways targeted at you constantly, which suggests a large pool of free-to-enter competitions that the radio pipeline doesn't touch. And the build log's 10 September "strategic reckoning" concluded that the system's proven value is **discovery and visibility, not automation**: zero genuinely free, automatable web-form entries were ever found in radio production data. Several of the local stations in the geographic passes ran *social-media-only* competitions that the current pipeline could see but had to drop. An Instagram extension leans into what the system is already good at (finding things, filtering them, reminding you) and doesn't depend on the thing that hasn't worked (unattended entry).

## Research method and caveats

Three parallel research passes covered (1) platform rules and UK law, (2) the competition landscape and discovery sources, and (3) evidence on entrant volumes and win rates. Unlike the original radio session, web search worked this time. Some primary sources still needed workarounds: Instagram's help centre only rendered when fetched as a search-engine crawler, the CAP Code section 8 page returned a 404 (CAP rules below come from the ASA's own guidance and rulings instead), and SuperLucky and MoneySavingExpert's competition pages sit behind bot challenges. The aggregator findings in section 4 come from live fetches on 6 and 7 October 2026. Where a figure comes from background knowledge rather than a retrieved source, it's marked **[BK]**.

The biggest caveat matches the radio report's: **nobody publishes entrant counts or win rates.** The one quantitative engagement study is a 2020 US vendor study. Everything in section 5 is a reasoned range, not a measurement. Unlike radio, though, Instagram exposes a cheap partial signal (comment counts on public posts) that we can collect ourselves (section 8).

## 1. The hard constraint: Instagram forbids automation, logged in or not

This shapes everything else, so it comes first.

Instagram's current Terms of Use (effective 4 March 2026) say: *"You can't attempt to create accounts or access or collect information in unauthorized ways. This includes creating accounts or accessing or collecting information in an automated way without our express permission, regardless of whether such automated access or collection is undertaken while logged-in to an Instagram account."* That last clause looks aimed directly at the 2024 *Meta v. Bright Data* ruling, where logged-off scraping of public data was found not to breach Meta's terms. Meta's Spam Community Standard separately prohibits *"engaging with content… either manually or automatically, at very high frequencies"*. Note the word **manually**: even hand-tapped entry at high volume can trip spam restrictions.

What that means in practice:

- **No automated entry.** Liking, following, commenting or story-sharing by script is out. This already matches CLAUDE.md's human-in-the-loop default, but here it's a platform rule, not just a preference. It also matches the radio T&C finding: promoters' T&Cs ban fake and duplicate accounts, and some explicitly void "competition accounts".
- **No scraping Instagram itself.** Instagram's robots.txt is `Disallow: /` for all agents, and plain fetches of hashtag and post pages return only a JavaScript shell anyway. The realistic downside of breaching this is losing your personal Instagram account, which is a worse outcome than any one prize is worth.
- **The official API is too narrow to be a primary source.** The Graph API's hashtag search requires a Business or Creator account plus Meta app review for "Instagram Public Content Access". It allows 30 unique hashtags per rolling 7 days, only returns posts from the last 24 hours, and can't return the poster's username. The Basic Display API was shut down on 4 December 2024. At best, the Graph API could be a later supplementary source.

The design consequence: **discovery has to come from human-curated aggregators and from you, and entry stays manual.** The tool's job is to make each manual entry quick and well-chosen, not to make it for you.

## 2. Legal and regulatory framework

**Gambling law makes most Instagram giveaways straightforwardly free draws.** Under Gambling Act 2005 Schedule 2, communicating "at a normal rate" isn't payment, and the Gambling Commission's guidance treats proportionate personal data the same way. So like, follow and comment to win is a free draw, not a lottery. The exception is "must buy" or "must be a customer" giveaways, which need either a genuine skill element (s.14) or an equal free route. Those should land in the review queue with `is_free_route=None`, exactly as the radio classifier already does.

**CAP Code rules give us free quality signals.** The ASA's social-media prize draw guidance requires the following:

- All significant conditions in the initial post: how to enter, closing date, prize and eligibility (rule 8.17).
- Prizes awarded as described, normally within 30 days (8.15.1).
- Winners' details (ordinarily surname and county) made available (8.28.5).
- A random selection the promoter can verify.

A giveaway with no closing date, no T&Cs or no history of announcing winners is non-compliant, and in practice it's also the type least likely to pay out. The ASA has upheld complaints against Instagram giveaways repeatedly: Molly-Mae Hague's £8k giveaway (2021, winner drawn from an unexplained shortlist), Briley Powell (2021, a £250 voucher withheld), PrettyLittleThing (2021, unverifiable story-share entries), Collab House (2022, no winners announced, prizes not evidenced) and Nasty Gal (2024, winner only announced deep in the comments).

**Instagram's Promotion Guidelines** put all responsibility on the promoter. Every promotion must carry a release of Instagram and a "not sponsored by Instagram" acknowledgement, and promoters must not encourage inaccurate tagging. A missing disclaimer is another weak quality signal.

**Tax.** UK competition prizes are not chargeable gains (TCGA 1992 s.51(1)), and casual hobby winnings aren't trading income. HMRC's BIM22017 echoes *Graham v Green*: "there is no tax on a habit". Prizes would only become taxable if comping turned into supplying services, such as paid content in exchange for prizes, or into reselling prizes as a business. That doesn't apply at this scale.

## 3. Scams: a much bigger factor here than in radio

Radio stations are licensed broadcasters. Instagram promoters can be anyone, and fake giveaways are the leading consumer scam pattern right now. Which? ranked "big brand giveaways" the number one most convincing scam of 2025: a fake Currys TV giveaway charged a £15 "delivery fee", then harvested card and address details. Cloned brand and influencer accounts that reply "you've won, click here" to every commenter are endemic. No UK figure isolates giveaway scams specifically.

Two consequences:

1. **The "targeted at you" giveaways you see are the riskiest slice.** Sponsored posts and cloned accounts are how many of these scams reach people. That's an argument for aggregator curation as the first filter, not against including Instagram at all.
2. **The tool needs a scam and quality screen before anything reaches you**, in the same conservative spirit as the free-route classifier. Usable red flags:
   - Any fee to claim ("delivery", "verification").
   - A "you've won" message from an account other than the promoter's verified one.
   - Off-platform claim links, or moving the conversation to WhatsApp or Telegram.
   - A lookalike handle, a new account, or a low-follower account.
   - Requests for card details or login codes.
   - Urgency ("first 500").
   - Cash or gift-card prizes offered for likes or follows. Meta's own spam policy bans these, so their presence signals a low-quality or fraudulent promoter.

The notification layer should also carry a standing rule: **the real promoter never asks for money or card details to release a prize.**

## 4. The landscape and where to discover from

**Who runs them.** A live pull of ThePrizeFinder's Instagram category (104 open listings, 7 October 2026) was dominated by **small and mid-size UK businesses**: gift boxes, candles, jewellery, lodges and hotels. There were also some national brands (Dreams, FatFace, Kwik Fit, Marmite, Thompson & Morgan), magazines (Cosmopolitan, Muddy Cotswolds), influencers and review accounts. 100 of the 104 were UK-residents-only. Prizes are mostly product bundles, hampers and overnight stays. Only 14 titles stated a value, ranging from £10 Amazon cards up to about £1,450 for a travel system. **Typical prizes are roughly £30–£300, much smaller than radio's.**

**Mechanics.** Follow, like and comment tagging friends is standard. Variants include extra entries per extra tag, story shares, keyword or answer comments, and occasionally photo or creative entries. Typical T&C terms:

- One comment per account, or one entry per unique person tagged.
- 18+, UK only, and a public profile for some mechanics.
- **A 24–72 hour claim window by DM** (48 hours confirmed directly in one set of T&Cs), after which the prize is redrawn.

Since Meta removed "log in with Instagram" for personal accounts in December 2024, some draw platforms (Easypromos) now require the **winner to send a keyword DM** to claim, rather than just replying to one. Missing a winner's DM, which often lands in Message Requests from accounts you don't follow, is a real and avoidable way to lose prizes.

**Discovery sources, ranked:**

| Source | Instagram listing | Plain httpx? | Verdict |
|---|---|---|---|
| **ThePrizeFinder** | `/competitions/instagram-competitions?page=0..10` (~104 live) | Yes, no login | **Best option.** Rows link directly to `instagram.com/p/...` and carry the promoter, closing date, instructions and UK restriction. Robots.txt only blocks admin and user paths, and the ToS allows personal non-commercial use. This is a near-drop-in variant of the existing `theprizefinder.py`. |
| Loquax | `/competitions/instagram-competitions.php` | Yes, but only the 10 newest; thread pages are login-gated (403) | Weak. It also already blocks Cloud Run IPs (see build log). |
| Competition Database | Instagram filter (~137 live) | Shows 5 of 137 anonymously, then needs registration | Possible later, with a free account. |
| SuperLucky, MSE, Facebook groups | n/a | Captcha, Cloudflare, or login-only | Not viable. |
| Instagram hashtags | n/a | No (robots, JS shell, ToS) | Not viable. Graph API is a possible later supplement only. |
| **You, forwarding posts** | n/a | n/a | **The one source of low-competition, unlisted giveaways.** See below. |

**Volume.** ThePrizeFinder and Competition Database each list on the order of 100–140 open Instagram giveaways, with closing dates spread over about three weeks. That implies roughly **35–50 new listings a week per aggregator** (my inference, not a published figure), with heavy overlap between the two.

**The structural catch.** The giveaways we can discover via aggregators are, by definition, the ones every other comper sees too. A Loquax thread from January 2025 shows a small business's £45 giveaway getting **500+ entries from Loquax users alone**. Being listed on a comping site probably matters more for entrant count than the promoter's follower count. The genuinely low-competition giveaways are the unlisted ones: small local businesses whose posts reach mostly their own followers, including the ones Instagram's algorithm shows *you*. The tool can't legitimately discover those, but you can, by sharing a post link to the Telegram bot, which the bot can then track (deadline, reminders, outcome) like any other promotion. That "you find it, the tool tracks it" path is cheap to build and is where the model says the better odds sit.

## 5. Sizing the opportunity: a Fermi model

Same approach as the radio report: wide low/high ranges per tier, with pessimistic and optimistic bounds and a geometric-mean base case. Three extra adjustments apply here that radio didn't need:

- **Prize value factor:** product prizes are worth less to you than their RRP. I used 65% for product tiers and 80% for big-brand prizes **[BK]**.
- **Non-award rate:** some giveaways never pay out. I assumed 5–20% for small or unverified promoters and 1–5% for brands (an assumption; no measured rate exists).
- **Claim loss:** a missed DM or a lapsed claim window, assumed at 1–5%.

| Tier | Prize range | Unique entrants | Available per week |
|---|---|---|---|
| S: small and local businesses, aggregator-listed | £25–£150 | 150–1,500 | ~25 |
| M: mid-size brands and influencers | £100–£1,000 | 1,000–20,000 | ~12 |
| L: big brands, holidays, tech | £1,000–£8,000 | 10,000–100,000 | ~3 |
| U: unlisted giveaways you forward yourself | £25–£150 | 30–300 | ~5 |

*Unique entrants are comment counts divided by roughly 1–3, to allow for "tag N friends" producing several comments per person. Tier S's range is set deliberately higher than "small business" alone would suggest, because aggregator listing pulls in compers.*

**Results (per year, entering everything in each tier, about 45 entries a week):**

| Case | Aggregator-listed only (S+M+L) | Including forwarded (U) | Expected wins/yr |
|---|---|---|---|
| Pessimistic | ~£14 | ~£24 | ~2 |
| **Base** | **~£130** | **~£230** | **~6** |
| Optimistic | ~£1,290 | ~£2,090 | ~18 |

**Calibration check.** The aggregator-listed base case implies about one win per 720 entries. That sits inside the only real benchmark found: Emily Parker of Competition Finder, quoted by Which? in 2022, said daily social-media compers "generally win a couple of times a month", which works out to roughly one win per 750–1,500 entries. Tier U isn't calibrated against anything (its implied odds are much better, at about 1 in 100). Treat it as the speculative part of the model, and the first thing to measure.

Almost all the value sits in **Tier S, plus Tier U if you feed it**. Mid and big brands contribute little, because their entrant counts outrun their prize sizes. That's the same shape as the radio finding (local beats flagship).

**Time cost.** At roughly 1.5 minutes per entry **[BK]** (30 seconds for like/follow/comment, up to 4 minutes with story shares and multiple co-host follows), 45 entries a week is about an hour a week, around 55 hours a year. The base case therefore works out to roughly **£2.50–£4 an hour**. That's better than the £1.14/hour MSE comper figure from the radio report, but nobody's idea of income. The realistic framing is *"a hobby that pays for itself, with an occasional nice win"*, not a money-maker.

## 6. Does the hypothesis hold up?

**Partly, and less strongly than for radio.** Instagram giveaways are plentiful, free and legally clean to enter. But they're the most heavily comped channel there is: aggregators, Facebook groups and hardcore compers entering 50–100 a day all converge on the same listed posts. The radio premise (few people enter) mostly doesn't hold for anything a tool like ours can discover. It probably *does* hold for the small, unlisted, local-business giveaways that only reach that business's followers, but those can only come from you.

What makes this worth doing anyway is that it's **cheap and fits what already exists**:

- The ThePrizeFinder Instagram adapter is a variant of an adapter already in the repo.
- The Telegram bot, dedup, reminders and outcome tracking all carry over.
- It gives the notification layer a steady stream of actually-enterable items, which radio hasn't managed.

It's also the one channel where we can **measure competitiveness directly**, by recording a post's comment count when you enter it, and so replace the model's guesses with data within a few weeks. Radio never offered that.

## 7. Risk summary

- **Account risk (most likely, most important).** Losing your personal Instagram account to spam action-blocks or a ToS breach would cost more than the system will ever win. Mitigations: no automation and no scraping of Instagram, and a **pacing cap on how many entries the bot suggests per day**, since the spam standard covers manual high-frequency activity and Meta publishes no thresholds. Comment text should vary naturally (you write it), and repeated bare "@friend @friend" comments are a known spam signal.
- **Scam risk.** This is new compared with radio. The scam screen and the "never pay to claim" rule cover it, along with only entering promoters that aggregators have listed or that you found yourself.
- **Social cost.** "Tag three friends" means repeatedly tagging real people, which gets old fast. Ideally the bot prefers giveaways without tagging, or you keep a small pool of friends who are happy to be tagged.
- **Identity.** Use your one real personal account. That's consistent with CLAUDE.md, and it's also what promoters prefer: some T&Cs explicitly void "competition accounts" or entrants who found the giveaway via listing sites. **Do not create a separate comping account.** It would breach the single-identity rule and some promoters' T&Cs.
- **Claim loss.** Short DM claim windows. The bot should remind you to check Message Requests during each entered giveaway's draw window. It can't watch your DMs for you, because that would be automated access.
- **Data quality.** Every range in section 5 is an assumption until section 8's measurement replaces it.

## 8. Recommended shape, if you want to proceed

This is not a spec, just enough to decide on.

1. **`theprizefinder_instagram` adapter.** Same pattern as `theprizefinder.py`, tested against a saved real fixture of the Instagram listing page. It stores the post URL, promoter, closing date and restriction. The entry mechanic isn't in the listing, so it stays unknown with `review_recommended=True`, per the existing conservative stance.
2. **Model changes.**
   - Add a new `EntryChannelType.INSTAGRAM`, manual-only like `POST`.
   - `Promotion.station_name_raw` and `Station` are radio-shaped. Either generalise them to a promoter, or add a parallel promoter field. This is a decision for the spec stage.
3. **"Forward to bot" ingestion.** Share an Instagram post link to the Telegram bot and it becomes a tracked promotion. The bot stores only what you give it (link, and optionally closing date and prize); it doesn't fetch the post.
4. **Scam and quality flags** from section 3, applied to aggregator listings and forwarded posts alike.
5. **Daily digest, not per-item pings.** A capped number of suggestions per day, small-promoter-first, with a tap-through link. Claim-window reminders to check DMs are part of the same digest.
6. **Measurement built in from day one.** When you mark something entered, the bot asks for the comment count and later whether you won. After 30–50 entries that replaces section 5's entrant ranges with real numbers.

Explicitly out of scope: any automated liking, following, commenting or story-sharing; scraping instagram.com; reading your DMs; and multiple or comping accounts.

## 9. Open questions for you

- **Time budget.** Is roughly an hour a week (about 45 entries) the right scale, or smaller?
- **Tagging friends.** Are you comfortable doing it, or should the digest down-rank giveaways that require tags?
- **Forwarding.** Will you actually share the giveaways you see to the bot? Tier U is most of the upside but depends entirely on that habit.
- **Scope creep.** ThePrizeFinder has equivalent Facebook and TikTok categories. Keep v1 to Instagram only? (I'd recommend yes.)
- **Graph API.** Ignore it for v1? (I'd recommend yes; app review for a personal tool is unlikely to be worth the effort.)

## 10. Decisions (7 October 2026) and what they change

Adán's answers to section 9:

- **No tagging friends.** Giveaways that require tags are out of scope. ThePrizeFinder's listing doesn't reveal the mechanic (rows just say "Enter via Instagram"), so this can't be filtered before you open the post. The bot needs a one-tap "needs tags, skip" response that logs the mechanic. That gives us the real share of tag-required giveaways for free, and lets us down-rank promoters who always require tags.
- **Forwarding only if it's effortless.** The lowest-effort route needs nothing new on the phone: Instagram's share button → Telegram → the bot chat, about three taps. The bot recognises an `instagram.com/p/` or `/reel/` link and stores it as a tracked promotion, with a single optional follow-up (closing date as quick-pick buttons, or skip). If even that turns out to be too much friction in practice, Tier U simply drops out of the model.
- **Instagram only.** No Facebook or TikTok.
- **Graph API: not in v1, but one possible upside is noted.** It's the only legitimate way to *automatically* reach unlisted, low-entrant giveaways (Tier U), and it returns `comments_count`, a direct entrant signal for each post. Against that: 30 hashtags a week, a 24-hour window, no username, and it would need your account switched to a Creator account plus Meta's Public Content Access, which a personal app may not get. Worth at most a time-boxed spike *after* v1 has run for a few weeks, and only if forwarding doesn't happen in practice.
- **Under an hour a week.** Dropping tag and story-share giveaways leaves follow + like + comment, at roughly 30–60 seconds each. A digest capped at about 5 suggestions a day (~35 a week) comes to roughly 20–35 minutes a week.

**Revised model.** The share of listed giveaways that require tags hasn't been measured. Assuming about half do **[BK]**, the enterable pool roughly halves. With the digest prioritising small promoters, the aggregator-listed base case falls to about **£50–£100 a year**, around **2 wins a year**. Forwarding, if it happens, adds Tier U on top (uncalibrated, as before). At ~25 minutes a week that's still roughly £2–£4 an hour, but in absolute terms it's small.

**Recommendation.** Build it as a **time-boxed experiment, not a feature**:

- ThePrizeFinder Instagram adapter.
- Capped daily digest with "entered / needs tags / skip" buttons.
- Share-to-bot ingestion.
- Comment-count and outcome capture.

Run it for 4–6 weeks, then decide on real numbers (entrant counts, tag-required share, wins) rather than on section 5's ranges. If the measured numbers come in below the base case, stop. The adapter costs little to leave dormant.

## Key sources

- Instagram, [Terms of Use](https://help.instagram.com/581066165581870) and [Promotion Guidelines](https://help.instagram.com/179379842258600)
- Meta, [Spam Community Standard](https://transparency.meta.com/policies/community-standards/spam/)
- Meta for Developers, [Hashtag Search](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/hashtag-search); Zapier, [Instagram Basic Display deprecation (4 Dec 2024)](https://help.zapier.com/hc/en-us/articles/32429170578317-Instagram-app-deprecation-on-Dec-4-2024)
- *Meta v. Bright Data*: [Farella Braun + Martel summary](https://www.fbm.com/technology/publications/major-decision-affects-law-of-scraping-and-online-data-collection-meta-platforms-v-bright-data/); [TechCrunch, Meta drops suit (26 Feb 2024)](https://techcrunch.com/2024/02/26/meta-drops-lawsuit-against-web-scraping-firm-bright-data-that-sold-millions-of-instagram-records)
- ICO et al., [Joint statement on data scraping (Aug 2023)](https://cy.ico.org.uk/about-the-ico/media-centre/news-and-blogs/2023/08/joint-statement-on-data-scraping-and-data-protection)
- Gambling Act 2005, [Schedule 2](https://www.legislation.gov.uk/ukpga/2005/19/schedule/2)
- ASA, [Prize draws in social media](https://www.asa.org.uk/advice-online/promotional-marketing-prize-draws-in-social-media.html); rulings: [Collab House (2022)](https://www.asa.org.uk/rulings/collab-house-ltd-a22-1155578-collab-house-ltd.html), [Nasty Gal (2024)](https://asa.org.uk/rulings/nasty-gal-ltd-a24-1239263-nasty-gal-ltd.html), [Briley Powell](https://adlaw.lewissilkin.com/post/102h55b/briley-powell-sanctioned-by-asa-for-not-giving-away-in-her-giveaway), [Molly-Mae Hague](https://cms.law/en/gbr/legal-updates/asa-upholds-complaint-against-an-influencer-s-luxury-instagram-giveaway-in-support-of-her-own-personal-brand)
- TCGA 1992, [s.51](https://www.legislation.gov.uk/ukpga/1992/12/section/51); HMRC, [BIM22017](https://www.gov.uk/hmrc-internal-manuals/business-income-manual/bim22017)
- Which?, [5 most convincing scams of 2025](https://www.which.co.uk/news/article/5-most-convincing-scams-of-2025-arqkX0a9i0WK) and [fake social media giveaways](https://www.which.co.uk/news/article/scam-alert-dont-hand-over-your-data-in-fake-social-media-giveaway-aMXlZ3n7E7vT)
- Which?, [Winning habits: how much could you win from entering competitions](https://www.which.co.uk/news/article/winning-habits-how-much-could-you-win-from-entering-competitions-acGeX7p4dBqr) (Emily Parker win-rate quote)
- Tailwind, [Instagram contest study (2020)](https://www.tailwindapp.com/blog/instagram-contest-ideas-that-will-grow-your-followers-70-faster)
- Loquax forums, [Pro competition entrants: a promoter's view](https://www.loquax.co.uk/forums/threads/pro-competition-entrants-a-promoters-view.1180343/)
- ThePrizeFinder, [Instagram competitions](https://www.theprizefinder.com/competitions/instagram-competitions) and [terms](https://www.theprizefinder.com/terms/); Loquax, [Instagram competitions](https://www.loquax.co.uk/competitions/instagram-competitions.php); Competition Database, [Instagram filter](https://www.competitiondatabase.co.uk/filtered/by_entry_method/3/1/5/instagram-social-media-competitions-and-giveaways/)
- Easypromos, [Instagram winner verification after Dec 2024](https://soporte.easypromosapp.com/hc/en-us/articles/32480799326868) and [fake Instagram giveaways](https://www.easypromosapp.com/blog/en/fake-instagram-giveaways/)
- London Theatre Direct, [Instagram competition T&Cs](https://www.londontheatredirect.com/news/instagram-competition-terms-conditions) (48-hour claim window example)

*Gaps flagged for follow-up: no measured entrant counts, win rates by channel, non-award rate or bot share. Section 8 step 6 is the plan to measure these directly. Meta's action-block thresholds are unpublished. The live CAP Code section 8 text wasn't retrievable, and the status of DCMS's proposed prize-draw operator code is unverified.*
