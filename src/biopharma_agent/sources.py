"""Default source catalog for feed-based collection."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from biopharma_agent.contracts import SourceRef


@dataclass(frozen=True)
class SourceProfile:
    """Named source bundle for common collection workflows."""

    name: str
    label: str
    category: str
    source_names: list[str]
    default_limit: int = 1
    analyze: bool = True
    fetch_details: bool = True
    clean_html_details: bool = True
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def feed_source(
    name: str,
    kind: str,
    url: str,
    *,
    region: str,
    publisher: str | None = None,
    authority: str | None = None,
    category: str,
    priority: int = 100,
    poll_interval_minutes: int = 60,
    request_delay_seconds: float = 0.0,
    respect_robots_txt: bool = True,
    notes: str = "",
) -> SourceRef:
    metadata = {
        "region": region,
        "category": category,
        "priority": priority,
        "poll_interval_minutes": poll_interval_minutes,
        "request_delay_seconds": request_delay_seconds,
        "respect_robots_txt": respect_robots_txt,
    }
    if publisher:
        metadata["publisher"] = publisher
    if authority:
        metadata["authority"] = authority
    if notes:
        metadata["notes"] = notes
    return SourceRef(name=name, kind=kind, url=url, metadata=metadata)


def html_listing_source(
    name: str,
    kind: str,
    url: str,
    *,
    region: str,
    category: str,
    include_url_patterns: list[str],
    publisher: str | None = None,
    authority: str | None = None,
    exclude_url_patterns: list[str] | None = None,
    title_keywords: list[str] | None = None,
    priority: int = 100,
    poll_interval_minutes: int = 120,
    request_delay_seconds: float = 1.0,
    respect_robots_txt: bool = True,
    max_links: int = 50,
    enabled: bool = True,
    disabled_reason: str = "",
    notes: str = "",
) -> SourceRef:
    source = feed_source(
        name=name,
        kind=kind,
        url=url,
        region=region,
        publisher=publisher,
        authority=authority,
        category=category,
        priority=priority,
        poll_interval_minutes=poll_interval_minutes,
        request_delay_seconds=request_delay_seconds,
        respect_robots_txt=respect_robots_txt,
        notes=notes,
    )
    metadata = dict(source.metadata)
    metadata["collector"] = "html_listing"
    metadata["html_listing"] = {
        "include_url_patterns": include_url_patterns,
        "exclude_url_patterns": exclude_url_patterns or [],
        "title_keywords": title_keywords or [],
        "max_links": max_links,
    }
    metadata["enabled"] = enabled
    if disabled_reason:
        metadata["disabled_reason"] = disabled_reason
    return SourceRef(name=source.name, kind=source.kind, url=source.url, metadata=metadata)


DEFAULT_FEED_SOURCES: list[SourceRef] = [
    feed_source(
        name="fda_press_releases",
        kind="regulatory_feed",
        url="https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml",
        region="US",
        authority="FDA",
        category="regulatory_press_release",
        priority=10,
        poll_interval_minutes=30,
    ),
    feed_source(
        name="fda_medwatch",
        kind="regulatory_feed",
        url="http://www.fda.gov/AboutFDA/ContactFDA/StayInformed/RSSFeeds/MedWatch/rss.xml",
        region="US",
        authority="FDA",
        category="safety_alert",
        priority=15,
        poll_interval_minutes=30,
    ),
    feed_source(
        name="mhra_drug_device_alerts",
        kind="regulatory_feed",
        url="https://www.gov.uk/drug-device-alerts.atom",
        region="UK",
        authority="MHRA",
        category="safety_alert",
        priority=16,
        poll_interval_minutes=30,
        notes="Official GOV.UK Atom feed for MHRA medicine and medical-device alerts, recalls, and safety information.",
    ),
    feed_source(
        name="ema_news",
        kind="regulatory_feed",
        url="https://www.ema.europa.eu/en/news.xml",
        region="EU",
        authority="EMA",
        category="regulatory_news",
        priority=20,
        poll_interval_minutes=60,
    ),
    feed_source(
        name="sec_press_releases",
        kind="market_regulatory_feed",
        url="https://www.sec.gov/news/pressreleases.rss",
        region="US",
        authority="SEC",
        category="market_regulatory_press_release",
        priority=20,
        poll_interval_minutes=60,
    ),
    feed_source(
        name="biopharma_dive_news",
        kind="industry_news_feed",
        url="https://www.biopharmadive.com/feeds/news/",
        region="global",
        publisher="BioPharma Dive",
        category="industry_news",
        priority=30,
        poll_interval_minutes=60,
    ),
    feed_source(
        name="medtech_dive_news",
        kind="industry_news_feed",
        url="https://www.medtechdive.com/feeds/news/",
        region="global",
        publisher="MedTech Dive",
        category="medtech_news",
        priority=35,
        poll_interval_minutes=60,
    ),
    feed_source(
        name="labiotech_news",
        kind="industry_news_feed",
        url="https://www.labiotech.eu/feed/",
        region="EU/global",
        publisher="Labiotech",
        category="biotech_news",
        priority=40,
        poll_interval_minutes=120,
    ),
    feed_source(
        name="biospace_all_news",
        kind="industry_news_feed",
        url="https://www.biospace.com/all-news.rss",
        region="global",
        publisher="BioSpace",
        category="life_science_news",
        priority=35,
        poll_interval_minutes=60,
    ),
    feed_source(
        name="biospace_business",
        kind="industry_news_feed",
        url="https://www.biospace.com/business.rss",
        region="global",
        publisher="BioSpace",
        category="life_science_business",
        priority=35,
        poll_interval_minutes=60,
    ),
    feed_source(
        name="biospace_fda",
        kind="industry_news_feed",
        url="https://www.biospace.com/fda.rss",
        region="US/global",
        publisher="BioSpace",
        category="fda_news",
        priority=30,
        poll_interval_minutes=60,
    ),
    feed_source(
        name="nasdaq_inc_news",
        kind="market_news_feed",
        url="https://www.nasdaq.com/feed/rssoutbound?category=Nasdaq",
        region="US/global",
        publisher="Nasdaq",
        category="exchange_operator_news",
        priority=40,
        poll_interval_minutes=120,
        notes="Nasdaq RSS category for Nasdaq Inc. news and insights.",
    ),
]


DEFAULT_HTML_SOURCES: list[SourceRef] = [
    html_listing_source(
        name="news_medical_life_sciences",
        kind="industry_news_html",
        url="https://www.news-medical.net/category/Life-Sciences-News.aspx",
        region="global",
        publisher="News-Medical.net",
        category="life_science_news",
        include_url_patterns=[r"news-medical\.net/news/"],
        exclude_url_patterns=[r"/whitepaper/", r"/supplier/"],
        priority=45,
        poll_interval_minutes=120,
        request_delay_seconds=1.0,
        enabled=False,
        disabled_reason="robots.txt disallows this listing page; keep as adapter candidate pending an allowed feed/API.",
        notes="HTML listing adapter candidate; site does not expose a stable general RSS feed.",
    ),
    html_listing_source(
        name="investegate_announcements",
        kind="market_announcement_html",
        url="https://www.investegate.co.uk/today-announcements",
        region="UK",
        publisher="Investegate",
        category="market_announcement",
        include_url_patterns=[r"investegate\.co\.uk/announcement/"],
        priority=25,
        poll_interval_minutes=30,
        request_delay_seconds=1.0,
        notes="HTML listing adapter verified against today-announcements page.",
    ),
    html_listing_source(
        name="asx_announcements",
        kind="market_announcement_html",
        url="https://www.asx.com.au/markets/trade-our-cash-market/announcements",
        region="AU",
        publisher="ASX",
        category="market_announcement",
        include_url_patterns=[r"asx\.com\.au"],
        title_keywords=["announcement", "market"],
        priority=30,
        poll_interval_minutes=30,
        request_delay_seconds=1.0,
        enabled=False,
        disabled_reason="ASX listing appears client-rendered and likely needs a dedicated API adapter.",
        notes="HTML adapter placeholder; may need a dedicated API-backed adapter if listing is client-rendered.",
    ),
]


DEFAULT_API_SOURCES: list[SourceRef] = [
    SourceRef(
        name="asx_biopharma_announcements",
        kind="market_announcement_api",
        url="https://www.asx.com.au/asx/v2/statistics/announcements.do",
        metadata={
            "region": "AU",
            "category": "market_announcement",
            "priority": 28,
            "poll_interval_minutes": 30,
            "request_delay_seconds": 1.0,
            "collector": "asx_announcements",
            "publisher": "ASX",
            "watchlist": ["CSL", "COH", "RMD"],
            "period": "W",
            "enabled": True,
            "notes": "Dedicated ASX announcements adapter for a biopharma/medtech watchlist.",
        },
    ),
    SourceRef(
        name="sec_biopharma_filings",
        kind="market_regulatory_api",
        url="https://data.sec.gov/submissions/",
        metadata={
            "region": "US",
            "category": "market_regulatory_filing",
            "priority": 18,
            "poll_interval_minutes": 60,
            "request_delay_seconds": 0.2,
            "collector": "sec_submissions",
            "authority": "SEC",
            "ciks": [
                "0000078003",
                "0001682852",
                "0000318154",
                "0000882095",
                "0000872589",
            ],
            "companies": ["Pfizer", "Moderna", "Amgen", "Gilead", "Regeneron"],
            "forms": ["8-K", "10-K", "10-Q", "S-1", "424B"],
            "enabled": True,
            "notes": "Dedicated SEC EDGAR submissions adapter for large biopharma issuers.",
        },
    ),
]


DEFAULT_SOURCES: list[SourceRef] = [*DEFAULT_FEED_SOURCES, *DEFAULT_HTML_SOURCES, *DEFAULT_API_SOURCES]


DEFAULT_SOURCE_PROFILES: list[SourceProfile] = [
    SourceProfile(
        name="core_intelligence",
        label="Core Intelligence",
        category="mixed",
        source_names=[
            "fda_press_releases",
            "fda_medwatch",
            "mhra_drug_device_alerts",
            "ema_news",
            "sec_biopharma_filings",
            "asx_biopharma_announcements",
            "biopharma_dive_news",
        ],
        notes="Balanced regulatory, safety, market filing, and industry news sources for daily monitoring.",
    ),
    SourceProfile(
        name="global_safety_alerts",
        label="Global Safety Alerts",
        category="safety_alert",
        source_names=[
            "fda_medwatch",
            "mhra_drug_device_alerts",
        ],
        notes="Official safety alert feeds for medicine and medical-device monitoring.",
    ),
    SourceProfile(
        name="market_filings",
        label="Market Filings",
        category="market",
        source_names=[
            "sec_biopharma_filings",
            "asx_biopharma_announcements",
            "investegate_announcements",
            "nasdaq_inc_news",
        ],
        notes="Capital-market announcements, exchange news, and regulatory filing sources.",
    ),
    SourceProfile(
        name="industry_news",
        label="Industry News",
        category="industry_news",
        source_names=[
            "biopharma_dive_news",
            "medtech_dive_news",
            "labiotech_news",
            "biospace_business",
            "biospace_fda",
        ],
        notes="Industry publication feeds for pipeline, business, FDA, and medtech updates.",
    ),
]


def list_default_sources(kind: str | None = None, category: str | None = None) -> list[SourceRef]:
    sources = DEFAULT_SOURCES
    if kind:
        sources = [source for source in sources if source.kind == kind]
    if category:
        sources = [source for source in sources if source.metadata.get("category") == category]
    return sorted(sources, key=lambda source: int(source.metadata.get("priority", 100)))


def get_default_source(name: str) -> SourceRef:
    for source in DEFAULT_SOURCES:
        if source.name == name:
            return source
    names = ", ".join(source.name for source in DEFAULT_SOURCES)
    raise KeyError(f"Unknown source '{name}'. Available sources: {names}")


def list_source_profiles() -> list[SourceProfile]:
    available_enabled = {
        source.name
        for source in DEFAULT_SOURCES
        if source.metadata.get("enabled", True)
    }
    profiles: list[SourceProfile] = []
    for profile in DEFAULT_SOURCE_PROFILES:
        enabled_names = [name for name in profile.source_names if name in available_enabled]
        profiles.append(
            SourceProfile(
                name=profile.name,
                label=profile.label,
                category=profile.category,
                source_names=enabled_names,
                default_limit=profile.default_limit,
                analyze=profile.analyze,
                fetch_details=profile.fetch_details,
                clean_html_details=profile.clean_html_details,
                notes=profile.notes,
            )
        )
    return profiles


def get_source_profile(name: str) -> SourceProfile:
    for profile in list_source_profiles():
        if profile.name == name:
            return profile
    names = ", ".join(profile.name for profile in DEFAULT_SOURCE_PROFILES)
    raise KeyError(f"Unknown source profile '{name}'. Available profiles: {names}")
