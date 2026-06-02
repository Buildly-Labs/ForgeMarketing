"""Lead source adapters for Lead Radar research jobs.

Adapters are intentionally conservative and human-in-the-loop.
They may collect from approved/public/manual inputs but do not send outreach.
"""

from typing import Any, Dict, List


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
        # v1 manual-assisted: support payload.rss_items to avoid forcing feed parser deps.
        payload = payload or {}
        rss_items = payload.get("rss_items") or []
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


class GoogleManualSearchAdapter(ManualListAdapter):
    source_type = "google_search"


class WebsiteDirectoryAdapter(ManualListAdapter):
    source_type = "website_directory"


class GitHubAdapter(ManualListAdapter):
    source_type = "github"


class ManualSocialPostAdapter(ManualListAdapter):
    source_type = "social_manual"


ADAPTERS = {
    "manual": ManualListAdapter(),
    "csv_import": ManualListAdapter(),
    "rss_feed": RSSFeedAdapter(),
    "google_search": GoogleManualSearchAdapter(),
    "website_directory": WebsiteDirectoryAdapter(),
    "github": GitHubAdapter(),
    "linkedin_manual": ManualSocialPostAdapter(),
    "instagram_manual": ManualSocialPostAdapter(),
    "reddit": ManualSocialPostAdapter(),
    "hacker_news": ManualSocialPostAdapter(),
    "product_hunt": ManualSocialPostAdapter(),
    "podcast": ManualSocialPostAdapter(),
    "youtube": ManualSocialPostAdapter(),
    "newsletter": ManualSocialPostAdapter(),
    "other": ManualListAdapter(),
}


def get_adapter(source_type: str) -> BaseLeadSourceAdapter:
    return ADAPTERS.get(source_type or "manual", ManualListAdapter())
