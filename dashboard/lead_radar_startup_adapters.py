"""
ForgeMarketing Startup Intel Plugin
====================================
Startup-focused lead source adapters and enrichment for Lead Radar.

PLUGIN_ID: startup_intel

This module is exclusive to ForgeMarketing. It discovers early-stage startups
from public government, developer, and investor data sources and enriches each
candidate with founder/social/contact details before human review.

Free sources (no API key):
  yc_companies   — YCombinator company directory (Algolia-powered)
  sbir_awards    — SBIR/STTR government award recipients
  nsf_awards     — NSF research award recipients
  sec_edgar      — SEC Form D equity fundraising filings

Paid/registered sources (free tier, API key required):
  product_hunt_api  — Product Hunt GraphQL API v2
  opencorporates    — OpenCorporates company search API
  companies_house   — UK Companies House API
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from html import unescape
from typing import Any, Dict, List
from urllib.parse import quote_plus, urlparse, unquote

import requests

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

from dashboard.lead_radar_adapters import BaseLeadSourceAdapter, DEFAULT_TIMEOUT, USER_AGENT

PLUGIN_ID = "startup_intel"
PLUGIN_LABEL = "Startup Intel"
PLUGIN_DESCRIPTION = (
    "Discovers early-stage startups from YCombinator, SBIR/STTR, NSF, "
    "SEC EDGAR Form D filings, Product Hunt, OpenCorporates, and Companies House."
)

# Keys stored in SystemConfig (or env fallback)
CONFIG_KEYS = {
    "product_hunt": ("startup_intel_product_hunt_token", "PRODUCTHUNT_TOKEN"),
    "opencorporates": ("startup_intel_opencorporates_key", "OPENCORPORATES_API_KEY"),
    "companies_house": ("startup_intel_companies_house_key", "COMPANIES_HOUSE_API_KEY"),
    "github": ("startup_intel_github_token", "GITHUB_TOKEN"),
}

SOURCE_TYPES = {
    "yc_companies", "sbir_awards", "nsf_awards", "sec_edgar",
    "product_hunt_api", "opencorporates", "companies_house",
}


def _cfg(key: str, env: str = "") -> str:
    """Read from SystemConfig first, then env variable."""
    import os
    try:
        from dashboard.models import SystemConfig
        row = SystemConfig.query.filter_by(key=key).first()
        if row and row.value:
            return row.value.strip()
    except Exception:
        pass
    return os.getenv(env or key, "").strip()


# ── YCombinator ────────────────────────────────────────────────────────────────

class YCombinatorAdapter(BaseLeadSourceAdapter):
    """YCombinator company directory — early-stage startups by batch/industry."""
    source_type = "yc_companies"
    _BASE = "https://api.ycombinator.com/v0.1/companies"

    _INDUSTRY_MAP = {
        "saas": "B2B Software and Services",
        "b2b": "B2B Software and Services",
        "developer": "Developer Tools",
        "devtool": "Developer Tools",
        "api": "Developer Tools",
        "ai": "Artificial Intelligence",
        "ml": "Artificial Intelligence",
        "fintech": "Fintech",
        "health": "Healthcare",
        "edtech": "Education",
        "climate": "Climate",
        "security": "Security",
        "infrastructure": "Infrastructure",
    }

    def fetch_candidates(self, lead_source, payload=None):
        payload = payload or {}
        manual = super().fetch_candidates(lead_source, payload)
        if manual:
            return manual

        keywords = self._keywords(lead_source, payload)
        limit = self._max_results(payload, default=25)
        params: Dict[str, Any] = {"per_page": min(limit * 2, 100)}

        notes = (getattr(lead_source, "notes", "") or "").lower()
        m = re.search(r"batch:([A-Z]\d+)", notes, re.IGNORECASE)
        if m:
            params["batch"] = m.group(1).upper()

        for kw in keywords:
            for k, v in self._INDUSTRY_MAP.items():
                if k in kw.lower():
                    params["industry"] = v
                    break
            else:
                continue
            break

        if keywords and "industry" not in params:
            params["q"] = " ".join(keywords[:2])

        try:
            resp = requests.get(
                self._BASE, params=params, timeout=DEFAULT_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            raise RuntimeError(f"YC API error ({self._BASE}): {exc}") from exc

        companies = data if isinstance(data, list) else (data.get("companies") or [])
        out = []
        for co in companies[:limit]:
            name = co.get("name", "")
            website = co.get("url", "") or co.get("website", "")
            desc = (co.get("one_liner", "") or co.get("long_description", "") or "")[:300]
            batch = co.get("batch", "")
            industry = co.get("industry", "")
            status = co.get("status", "")
            country = co.get("country", "")
            out.append(self.normalize_candidate({
                "company": name,
                "title": f"YC {batch} · {industry}",
                "url": website,
                "text": f"{desc} | Batch: {batch} | Industry: {industry} | Status: {status}",
                "segment": industry or "startup",
                "region": country,
            }))
        return out


# ── SBIR Awards ────────────────────────────────────────────────────────────────

class SBIRAdapter(BaseLeadSourceAdapter):
    """SBIR/STTR award recipients — deep-tech startups with government funding."""
    source_type = "sbir_awards"
    _BASE = "https://api.sbir.gov/public/awards"

    def fetch_candidates(self, lead_source, payload=None):
        payload = payload or {}
        keywords = self._keywords(lead_source, payload)
        if not keywords:
            return []
        limit = self._max_results(payload, default=20)
        out = []
        last_error = None
        for kw in keywords[:3]:
            try:
                resp = requests.get(
                    self._BASE,
                    params={"keyword": kw, "rows": min(limit, 25), "start": 0},
                    timeout=DEFAULT_TIMEOUT,
                    headers={"User-Agent": USER_AGENT},
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                last_error = exc
                continue
            for award in (data.get("data") or []):
                firm = award.get("firm") or {}
                company = firm.get("name") or award.get("firm_name", "")
                pi = f"{award.get('pi_first_name','')} {award.get('pi_last_name','')}".strip()
                title = award.get("award_title", "")
                abstract = (award.get("abstract", "") or "")[:350]
                amount = award.get("award_amount") or 0
                agency = award.get("agency", "")
                phase = award.get("phase", "")
                website = firm.get("website", "")
                state = firm.get("state_code", "") or award.get("state_code", "")
                out.append(self.normalize_candidate({
                    "name": pi,
                    "company": company,
                    "title": f"{agency} SBIR Phase {phase} — ${int(amount):,}",
                    "url": website,
                    "text": f"{title}. {abstract}",
                    "segment": "deep_tech",
                    "region": f"US-{state}" if state else "",
                }))
                if len(out) >= limit:
                    return out
        if not out and last_error:
            raise RuntimeError(f"SBIR API error: {last_error}")
        return out


# ── NSF Awards ─────────────────────────────────────────────────────────────────

class NSFAwardsAdapter(BaseLeadSourceAdapter):
    """NSF award recipients — research-backed startups and university spinouts."""
    source_type = "nsf_awards"
    _BASE = "https://api.research.gov/awardapi-service/v1/awards.json"
    _FIELDS = ",".join([
        "id", "title", "piFirstName", "piLastName", "awardeeName",
        "awardeeCity", "awardeeStateCode", "awardAmount", "startDate",
        "abstractText", "primaryProgram",
    ])

    def fetch_candidates(self, lead_source, payload=None):
        payload = payload or {}
        keywords = self._keywords(lead_source, payload)
        if not keywords:
            return []
        limit = self._max_results(payload, default=20)
        out = []
        last_error = None
        for kw in keywords[:2]:
            try:
                resp = requests.get(
                    self._BASE,
                    params={"keyword": kw, "printFields": self._FIELDS, "offset": 1},
                    timeout=DEFAULT_TIMEOUT,
                    headers={"User-Agent": USER_AGENT},
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                last_error = exc
                continue
            for award in (data.get("response", {}).get("award") or []):
                pi = f"{award.get('piFirstName','')} {award.get('piLastName','')}".strip()
                company = award.get("awardeeName", "")
                abstract = (award.get("abstractText", "") or "")[:350]
                amount = award.get("awardAmount", "")
                program = award.get("primaryProgram", "")
                nsf_id = award.get("id", "")
                state = award.get("awardeeStateCode", "")
                city = award.get("awardeeCity", "")
                out.append(self.normalize_candidate({
                    "name": pi,
                    "company": company,
                    "title": f"NSF Award — {program}",
                    "url": f"https://www.nsf.gov/awardsearch/showAward?AWD_ID={nsf_id}",
                    "text": f"{abstract} | Amount: {amount} | {city}, {state}",
                    "segment": "deep_tech",
                    "region": f"US-{state}" if state else "",
                }))
                if len(out) >= limit:
                    return out
        if not out and last_error:
            raise RuntimeError(f"NSF API error: {last_error}")
        return out


# ── SEC EDGAR Form D ───────────────────────────────────────────────────────────

class SECEdgarFormDAdapter(BaseLeadSourceAdapter):
    """SEC Form D equity fundraising filings — recent raises by private companies."""
    source_type = "sec_edgar"
    _BASE = "https://efts.sec.gov/LATEST/search-index"
    _SEARCH_BASE = "https://efts.sec.gov/LATEST/search-index"

    def fetch_candidates(self, lead_source, payload=None):
        payload = payload or {}
        keywords = self._keywords(lead_source, payload)
        limit = self._max_results(payload, default=20)
        query = " OR ".join(f'"{k}"' for k in keywords[:3]) if keywords else "software SaaS"
        start_dt = (datetime.utcnow() - timedelta(days=180)).strftime("%Y-%m-%d")
        try:
            resp = requests.get(
                self._BASE,
                params={
                    "q": query,
                    "dateRange": "custom",
                    "startdt": start_dt,
                    "forms": "D",
                },
                timeout=DEFAULT_TIMEOUT,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            raise RuntimeError(f"SEC EDGAR API error: {exc}") from exc

        out = []
        for hit in (data.get("hits", {}).get("hits") or [])[:limit]:
            src = hit.get("_source", {})
            entity = (src.get("entity_name") or src.get("issuer_name") or "").strip()
            if not entity:
                continue
            state = src.get("state_of_inc") or src.get("issuer_state") or ""
            amount = src.get("total_offering_amount") or ""
            date_filed = src.get("date_filed", "")
            cik = src.get("entity_id") or src.get("file_num") or ""
            out.append(self.normalize_candidate({
                "company": entity,
                "title": f"SEC Form D — {state} — raised ${amount}",
                "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=D",
                "text": f"Equity raise via Form D. State: {state}. Amount: ${amount}. Filed: {date_filed}.",
                "segment": "fundraising",
                "region": f"US-{state}" if state else "",
            }))
        return out


# ── Product Hunt API v2 ────────────────────────────────────────────────────────

class ProductHuntAPIAdapter(BaseLeadSourceAdapter):
    """Product Hunt GraphQL API v2 — newly launched products (requires Bearer token)."""
    source_type = "product_hunt_api"
    _GQL = "https://api.producthunt.com/v2/api/graphql"
    _QUERY = """
    query($first:Int,$query:String){
      posts(first:$first,order:VOTES,query:$query){
        edges{node{
          name tagline website votesCount
          makers{name twitterUsername}
          topics{edges{node{name}}}
        }}
      }
    }"""

    def validate_config(self, lead_source):
        if not _cfg(*CONFIG_KEYS["product_hunt"]):
            return [
                "Product Hunt API token not set. "
                "Get one at producthunt.com/v2/oauth/applications → create an app → get Bearer token. "
                "Then add it in Admin → System Config → Startup Intel."
            ]
        return []

    def fetch_candidates(self, lead_source, payload=None):
        token = _cfg(*CONFIG_KEYS["product_hunt"])
        if not token:
            return []
        payload = payload or {}
        keywords = self._keywords(lead_source, payload)
        limit = self._max_results(payload, default=20)
        try:
            resp = requests.post(
                self._GQL,
                json={"query": self._QUERY, "variables": {
                    "first": limit,
                    "query": keywords[0] if keywords else None,
                }},
                headers={
                    "Authorization": f"Bearer {token}",
                    "User-Agent": USER_AGENT,
                    "Content-Type": "application/json",
                },
                timeout=DEFAULT_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return []
        out = []
        for edge in (data.get("data", {}).get("posts", {}).get("edges") or []):
            node = edge.get("node", {})
            makers = node.get("makers") or []
            maker_name = makers[0].get("name", "") if makers else ""
            tw = ("@" + makers[0]["twitterUsername"]) if makers and makers[0].get("twitterUsername") else ""
            topics = [e.get("node", {}).get("name", "") for e in (node.get("topics", {}).get("edges") or [])]
            out.append(self.normalize_candidate({
                "name": maker_name,
                "company": node.get("name", ""),
                "title": node.get("tagline", ""),
                "url": node.get("website", ""),
                "text": (
                    f"{node.get('tagline','')} | Topics: {', '.join(topics[:3])} "
                    f"| Votes: {node.get('votesCount',0)}"
                    + (f" | Twitter: {tw}" if tw else "")
                ),
                "segment": topics[0] if topics else "startup",
            }))
        return out


# ── OpenCorporates ─────────────────────────────────────────────────────────────

class OpenCorporatesAdapter(BaseLeadSourceAdapter):
    """OpenCorporates — recently incorporated US/global companies (requires API key)."""
    source_type = "opencorporates"
    _BASE = "https://api.opencorporates.com/v0.4/companies/search"

    def validate_config(self, lead_source):
        if not _cfg(*CONFIG_KEYS["opencorporates"]):
            return [
                "OpenCorporates API key not set. "
                "Register free at opencorporates.com/api_accounts/new. "
                "Add key in Admin → System Config → Startup Intel."
            ]
        return []

    def fetch_candidates(self, lead_source, payload=None):
        api_key = _cfg(*CONFIG_KEYS["opencorporates"])
        if not api_key:
            return []
        payload = payload or {}
        keywords = self._keywords(lead_source, payload)
        if not keywords:
            return []
        limit = self._max_results(payload, default=20)
        out = []
        for kw in keywords[:2]:
            try:
                resp = requests.get(
                    self._BASE,
                    params={
                        "q": kw,
                        "api_token": api_key,
                        "country_code": "us",
                        "normalise_company_name": "true",
                    },
                    timeout=DEFAULT_TIMEOUT,
                    headers={"User-Agent": USER_AGENT},
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                continue
            for item in (data.get("results", {}).get("companies") or []):
                co = item.get("company", {})
                out.append(self.normalize_candidate({
                    "company": co.get("name", ""),
                    "title": f"{co.get('company_type','')} — {co.get('jurisdiction_code','').upper()}",
                    "url": co.get("opencorporates_url", ""),
                    "text": (
                        f"Incorporated: {co.get('incorporation_date','')}. "
                        f"Type: {co.get('company_type','')}. "
                        f"Status: {co.get('current_status','')}."
                    ),
                    "segment": "new_incorporation",
                }))
                if len(out) >= limit:
                    return out
        return out


# ── Companies House UK ─────────────────────────────────────────────────────────

class CompaniesHouseAdapter(BaseLeadSourceAdapter):
    """UK Companies House — newly formed UK companies (requires free API key)."""
    source_type = "companies_house"
    _BASE = "https://api.company-information.service.gov.uk/search/companies"

    def validate_config(self, lead_source):
        if not _cfg(*CONFIG_KEYS["companies_house"]):
            return [
                "Companies House API key not set. "
                "Register free at developer.company-information.service.gov.uk. "
                "Add key in Admin → System Config → Startup Intel."
            ]
        return []

    def fetch_candidates(self, lead_source, payload=None):
        api_key = _cfg(*CONFIG_KEYS["companies_house"])
        if not api_key:
            return []
        payload = payload or {}
        keywords = self._keywords(lead_source, payload)
        if not keywords:
            return []
        limit = self._max_results(payload, default=20)
        out = []
        for kw in keywords[:2]:
            try:
                resp = requests.get(
                    self._BASE,
                    params={"q": kw, "items_per_page": min(limit, 20)},
                    auth=(api_key, ""),
                    timeout=DEFAULT_TIMEOUT,
                    headers={"User-Agent": USER_AGENT},
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                continue
            for item in (data.get("items") or []):
                co_num = item.get("company_number", "")
                out.append(self.normalize_candidate({
                    "company": item.get("title", ""),
                    "title": f"{item.get('company_type','')} — {item.get('company_status','')}",
                    "url": f"https://find-and-update.company-information.service.gov.uk/company/{co_num}",
                    "text": (
                        f"Incorporated: {item.get('date_of_creation','')}. "
                        f"{item.get('address_snippet','')}."
                    ),
                    "segment": "uk_incorporation",
                    "region": "UK",
                }))
                if len(out) >= limit:
                    return out
        return out


# ── Startup Enricher ───────────────────────────────────────────────────────────

class StartupEnricher:
    """
    Enrichment pipeline for startup lead candidates.

    For each candidate, attempts to find:
      1. GitHub org — website, description, public email, repo count
      2. LinkedIn company URL — via DuckDuckGo
      3. Twitter/X handle — via DuckDuckGo
      4. Contact email — scraped from website homepage/contact page

    All enrichment is best-effort; failures are silent.
    """

    def enrich(self, candidate) -> dict:
        """Run enrichment and return a dict of found fields."""
        company = (candidate.raw_company or "").strip()
        url = (candidate.raw_url or "").strip()
        if not company:
            return {"enrichment_summary": "No company name — skipped"}

        signals = []
        result = {}

        # 1. GitHub org
        gh = self._github_org(company)
        if gh:
            result.update(gh)
            if gh.get("github_url"):
                signals.append(f"GitHub: {gh['github_url']}")
            if gh.get("github_email"):
                signals.append(f"GitHub email: {gh['github_email']}")
            if gh.get("github_website"):
                url = url or gh["github_website"]

        # 2. LinkedIn
        li = self._ddg_first(company, "site:linkedin.com/company")
        if li and "linkedin.com/company" in li:
            result["linkedin_url"] = li
            signals.append(f"LinkedIn: {li}")

        # 3. Twitter/X
        tw = self._ddg_first(company, "site:twitter.com OR site:x.com")
        if tw:
            m = re.search(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]{1,50})", tw)
            if m:
                result["twitter_handle"] = "@" + m.group(1)
                signals.append(f"Twitter: @{m.group(1)}")

        # 4. Contact email
        if url:
            email = self._find_email(url)
            if email:
                result["contact_email"] = email
                signals.append(f"Email: {email}")

        result["enrichment_summary"] = " | ".join(signals) if signals else "No additional signals found"
        return result

    def _github_org(self, company: str) -> dict:
        slug = re.sub(r"[^a-z0-9]", "", company.lower())[:30]
        if len(slug) < 3:
            return {}
        gh_token = _cfg(*CONFIG_KEYS["github"])
        headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github.v3+json"}
        if gh_token:
            headers["Authorization"] = f"token {gh_token}"
        try:
            r = requests.get(
                f"https://api.github.com/search/users?q={quote_plus(slug)}+type:org&per_page=5",
                timeout=DEFAULT_TIMEOUT, headers=headers,
            )
            if r.status_code != 200:
                return {}
            for item in (r.json().get("items") or []):
                login = (item.get("login") or "").lower()
                if slug[:5] in login or login[:5] in slug:
                    dr = requests.get(
                        f"https://api.github.com/orgs/{login}",
                        timeout=DEFAULT_TIMEOUT, headers=headers,
                    )
                    if dr.status_code == 200:
                        org = dr.json()
                        return {
                            "github_url": org.get("html_url", ""),
                            "github_email": org.get("email", ""),
                            "github_website": org.get("blog", ""),
                            "github_description": (org.get("description") or "")[:200],
                            "github_public_repos": org.get("public_repos", 0),
                        }
        except Exception:
            pass
        return {}

    def _ddg_first(self, company: str, site_query: str) -> str:
        if BeautifulSoup is None:
            return ""
        try:
            q = quote_plus(f"{company} {site_query}")
            r = requests.get(
                f"https://duckduckgo.com/html/?q={q}",
                timeout=DEFAULT_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
            )
            if r.status_code != 200:
                return ""
            soup = BeautifulSoup(r.text, "lxml")
            for a in soup.select("a.result__a")[:8]:
                href = a.get("href", "")
                if "linkedin.com/company/" in href or "twitter.com/" in href or "x.com/" in href:
                    if "uddg=" in href:
                        m = re.search(r"uddg=([^&]+)", href)
                        if m:
                            href = unquote(m.group(1))
                    return href
        except Exception:
            pass
        return ""

    def _find_email(self, base_url: str) -> str:
        try:
            parsed = urlparse(base_url)
            if not parsed.netloc:
                return ""
            root = f"{parsed.scheme or 'https'}://{parsed.netloc}"
            skip = {"example", "domain", "test", "noreply", "no-reply", "@png", "@jpg",
                    "@gif", "@svg", "@webp", "sentry", "wix", "cloudflare"}
            for path in ["/contact", "/about", "/team", "/"]:
                try:
                    r = requests.get(
                        root + path, timeout=8,
                        headers={"User-Agent": USER_AGENT}, allow_redirects=True,
                    )
                    if r.status_code == 200:
                        emails = re.findall(
                            r"[a-zA-Z0-9_.+-]{2,}@[a-zA-Z0-9-]+\.[a-zA-Z]{2,6}", r.text
                        )
                        for e in emails:
                            if len(e) < 80 and not any(s in e.lower() for s in skip):
                                return e
                except Exception:
                    continue
        except Exception:
            pass
        return ""
