"""Lead source adapters for Lead Radar research jobs.

Adapters are intentionally conservative and human-in-the-loop.
They may collect from approved/public/manual inputs but do not send outreach.
"""

from __future__ import annotations

from html import unescape
from typing import Any, Dict, List
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import requests

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
    BeautifulSoup = None


DEFAULT_TIMEOUT = 12
DEFAULT_LIMIT = 20
USER_AGENT = "ForgeMarketingLeadRadar/1.0 (+https://market.firstcityfoundry.com)"


class BaseLeadSourceAdapter:
    source_type = "base"

    def validate_config(self, lead_source) -> List[str]:
        return []

    def fetch_candidates(self, lead_source, payload: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        return []

    def normalize_candidate(self, raw_item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "name": raw_item.get("name", ""),
            "company": raw_item.get("company", ""),
            "title": raw_item.get("title", ""),
            "url": raw_item.get("url", ""),
            "text": raw_item.get("text", ""),
            "segment": raw_item.get("segment", ""),
            "region": raw_item.get("region", ""),
        }

    def _keywords(self, lead_source, payload: Dict[str, Any] | None = None) -> List[str]:
        payload = payload or {}
        raw = payload.get("query_keywords")
        if raw is None:
            raw = getattr(lead_source, "query_keywords", None)

        if isinstance(raw, str):
            items = [x.strip() for x in raw.replace("\n", ",").split(",")]
            return [x for x in items if x]
        if isinstance(raw, list):
            return [str(x).strip() for x in raw if str(x).strip()]
        return []

    def _max_results(self, payload: Dict[str, Any] | None = None, default: int = 20) -> int:
        payload = payload or {}
        value = payload.get("max_results", default)
        try:
            value = int(value)
        except Exception:
            value = default
        return max(1, min(50, value))

    def _http_get_json(self, url: str) -> Dict[str, Any]:
        resp = requests.get(url, timeout=DEFAULT_TIMEOUT, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        return resp.json()

    def _http_get_text(self, url: str) -> str:
        resp = requests.get(url, timeout=DEFAULT_TIMEOUT, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        return resp.text


class ManualListAdapter(BaseLeadSourceAdapter):
    source_type = "manual"

    def fetch_candidates(self, lead_source, payload: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        payload = payload or {}
        # Supported user input keys:
        # - manual_items: [{name, company, title, url, text, segment, region}]
        # - text_blob: newline-delimited quick notes
        manual_items = payload.get("manual_items") or []
        if manual_items:
            return [self.normalize_candidate(item) for item in manual_items]

        text_blob = payload.get("text_blob", "")
        if not text_blob:
            return []

        items = []
        for line in text_blob.splitlines():
            line = line.strip()
            if not line:
                continue
            items.append(self.normalize_candidate({"text": line}))
        return items


class RSSFeedAdapter(BaseLeadSourceAdapter):
    source_type = "rss_feed"

    def validate_config(self, lead_source) -> List[str]:
        if not getattr(lead_source, "url", ""):
            return ["RSS source requires url"]
        return []

    def fetch_candidates(self, lead_source, payload: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        payload = payload or {}
        rss_items = payload.get("rss_items") or []
        if rss_items:
            return [
                self.normalize_candidate(
                    {
                        "name": i.get("author", ""),
                        "company": i.get("company", ""),
                        "title": i.get("title", ""),
                        "url": i.get("url", ""),
                        "text": i.get("summary", ""),
                        "segment": i.get("segment", ""),
                        "region": i.get("region", ""),
                    }
                )
                for i in rss_items
            ]

        if not getattr(lead_source, "url", ""):
            return []

        try:
            xml_text = self._http_get_text(lead_source.url)
            root = ET.fromstring(xml_text)
        except Exception:
            return []

        keywords = [k.lower() for k in self._keywords(lead_source, payload)]
        limit = self._max_results(payload, default=DEFAULT_LIMIT)
        out: List[Dict[str, Any]] = []

        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            summary = (item.findtext("description") or "").strip()
            author = (
                item.findtext("author")
                or item.findtext("{http://purl.org/dc/elements/1.1/}creator")
                or ""
            ).strip()
            blob = f"{title} {summary}".lower()
            if keywords and not any(k in blob for k in keywords):
                continue
            out.append(
                self.normalize_candidate(
                    {
                        "name": author,
                        "company": "",
                        "title": title,
                        "url": link,
                        "text": summary,
                    }
                )
            )
            if len(out) >= limit:
                break
        return out


class GoogleManualSearchAdapter(ManualListAdapter):
    source_type = "google_search"

    def fetch_candidates(self, lead_source, payload: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        payload = payload or {}
        manual = super().fetch_candidates(lead_source, payload)
        if manual:
            return manual

        keywords = self._keywords(lead_source, payload)
        if not keywords:
            return []

        limit = self._max_results(payload, default=10)
        out: List[Dict[str, Any]] = []
        for keyword in keywords[:3]:
            query = quote_plus(keyword)
            url = f"https://duckduckgo.com/html/?q={query}"
            try:
                html = self._http_get_text(url)
            except Exception:
                continue

            if BeautifulSoup is None:
                continue

            soup = BeautifulSoup(html, "lxml")
            for item in soup.select(".result")[:limit]:
                a = item.select_one("a.result__a")
                snippet = item.select_one(".result__snippet")
                if not a:
                    continue
                title = a.get_text(" ", strip=True)
                href = a.get("href") or ""
                text = snippet.get_text(" ", strip=True) if snippet else ""
                out.append(
                    self.normalize_candidate(
                        {
                            "name": "",
                            "company": "",
                            "title": title,
                            "url": href,
                            "text": text,
                        }
                    )
                )
                if len(out) >= limit:
                    return out
        return out


class WebsiteDirectoryAdapter(ManualListAdapter):
    source_type = "website_directory"

    def fetch_candidates(self, lead_source, payload: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        payload = payload or {}
        manual = super().fetch_candidates(lead_source, payload)
        if manual:
            return manual

        url = (getattr(lead_source, "url", "") or "").strip()
        if not url:
            return []
        if BeautifulSoup is None:
            return []

        keywords = [k.lower() for k in self._keywords(lead_source, payload)]
        limit = self._max_results(payload, default=20)

        try:
            html = self._http_get_text(url)
            soup = BeautifulSoup(html, "lxml")
        except Exception:
            return []

        out: List[Dict[str, Any]] = []
        for a in soup.find_all("a"):
            title = a.get_text(" ", strip=True)
            href = (a.get("href") or "").strip()
            if not title and not href:
                continue
            blob = f"{title} {href}".lower()
            if keywords and not any(k in blob for k in keywords):
                continue
            out.append(self.normalize_candidate({"title": title, "url": href, "text": title}))
            if len(out) >= limit:
                break
        return out


class GitHubAdapter(ManualListAdapter):
    source_type = "github"

    def fetch_candidates(self, lead_source, payload: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        payload = payload or {}
        manual = super().fetch_candidates(lead_source, payload)
        if manual:
            return manual

        keywords = self._keywords(lead_source, payload)
        if not keywords:
            return []

        limit = self._max_results(payload, default=15)
        out: List[Dict[str, Any]] = []
        for keyword in keywords[:3]:
            query = quote_plus(keyword)
            url = f"https://api.github.com/search/repositories?q={query}&sort=updated&order=desc&per_page=10"
            try:
                data = self._http_get_json(url)
            except Exception:
                continue

            for repo in data.get("items", []):
                owner = (repo.get("owner") or {}).get("login", "")
                out.append(
                    self.normalize_candidate(
                        {
                            "name": owner,
                            "company": owner,
                            "title": repo.get("full_name", ""),
                            "url": repo.get("html_url", ""),
                            "text": (repo.get("description") or "").strip(),
                        }
                    )
                )
                if len(out) >= limit:
                    return out
        return out


class ManualSocialPostAdapter(ManualListAdapter):
    source_type = "social_manual"


class HackerNewsAdapter(BaseLeadSourceAdapter):
    source_type = "hacker_news"

    def fetch_candidates(self, lead_source, payload: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        keywords = self._keywords(lead_source, payload)
        if not keywords:
            return []

        limit = self._max_results(payload, default=15)
        out: List[Dict[str, Any]] = []
        for keyword in keywords[:3]:
            query = quote_plus(keyword)
            url = f"https://hn.algolia.com/api/v1/search_by_date?query={query}&tags=story&hitsPerPage=15"
            try:
                data = self._http_get_json(url)
            except Exception:
                continue

            for hit in data.get("hits", []):
                title = (hit.get("title") or hit.get("story_title") or "").strip()
                href = (hit.get("url") or hit.get("story_url") or "").strip()
                author = (hit.get("author") or "").strip()
                out.append(
                    self.normalize_candidate(
                        {
                            "name": author,
                            "company": "",
                            "title": title,
                            "url": href,
                            "text": unescape((hit.get("_highlightResult", {}).get("title", {}).get("value") or "").strip()),
                        }
                    )
                )
                if len(out) >= limit:
                    return out
        return out


class RedditAdapter(BaseLeadSourceAdapter):
    source_type = "reddit"

    def fetch_candidates(self, lead_source, payload: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        keywords = self._keywords(lead_source, payload)
        if not keywords:
            return []

        limit = self._max_results(payload, default=15)
        out: List[Dict[str, Any]] = []
        for keyword in keywords[:3]:
            query = quote_plus(keyword)
            url = f"https://www.reddit.com/search.json?q={query}&sort=new&limit=15"
            try:
                data = self._http_get_json(url)
            except Exception:
                continue

            for child in ((data.get("data") or {}).get("children") or []):
                post = child.get("data") or {}
                title = (post.get("title") or "").strip()
                permalink = (post.get("permalink") or "").strip()
                href = f"https://www.reddit.com{permalink}" if permalink else ""
                author = (post.get("author") or "").strip()
                text = (post.get("selftext") or "").strip()[:500]
                out.append(
                    self.normalize_candidate(
                        {
                            "name": author,
                            "company": post.get("subreddit_name_prefixed", ""),
                            "title": title,
                            "url": href,
                            "text": text,
                        }
                    )
                )
                if len(out) >= limit:
                    return out
        return out


class ProductHuntAdapter(RSSFeedAdapter):
    source_type = "product_hunt"

    def fetch_candidates(self, lead_source, payload: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        if not getattr(lead_source, "url", ""):
            lead_source.url = "https://www.producthunt.com/feed"
        return super().fetch_candidates(lead_source, payload)


ADAPTERS = {
    "manual": ManualListAdapter(),
    "csv_import": ManualListAdapter(),
    "rss_feed": RSSFeedAdapter(),
    "google_search": GoogleManualSearchAdapter(),
    "website_directory": WebsiteDirectoryAdapter(),
    "github": GitHubAdapter(),
    "linkedin_manual": ManualSocialPostAdapter(),
    "instagram_manual": ManualSocialPostAdapter(),
    "reddit": RedditAdapter(),
    "hacker_news": HackerNewsAdapter(),
    "product_hunt": ProductHuntAdapter(),
    "podcast": ManualSocialPostAdapter(),
    "youtube": ManualSocialPostAdapter(),
    "newsletter": ManualSocialPostAdapter(),
    "other": ManualListAdapter(),
}

# ── Startup Intel Plugin ───────────────────────────────────────────────────────
# Registered here after base ADAPTERS so there's no circular import.
try:
    from dashboard.lead_radar_startup_adapters import (  # noqa: E402
        YCombinatorAdapter,
        SBIRAdapter,
        NSFAwardsAdapter,
        SECEdgarFormDAdapter,
        ProductHuntAPIAdapter,
        OpenCorporatesAdapter,
        CompaniesHouseAdapter,
    )
    ADAPTERS.update({
        "yc_companies":    YCombinatorAdapter(),
        "sbir_awards":     SBIRAdapter(),
        "nsf_awards":      NSFAwardsAdapter(),
        "sec_edgar":       SECEdgarFormDAdapter(),
        "product_hunt_api": ProductHuntAPIAdapter(),
        "opencorporates":  OpenCorporatesAdapter(),
        "companies_house": CompaniesHouseAdapter(),
    })
except Exception as _si_err:
    import logging
    logging.getLogger(__name__).warning("Startup Intel plugin not loaded: %s", _si_err)


def get_adapter(source_type: str) -> BaseLeadSourceAdapter:
    return ADAPTERS.get(source_type or "manual", ManualListAdapter())
