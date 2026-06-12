from pathlib import Path

import automation.influencer_discovery as inf


class FakeSearcher:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def search_influencers(self, brand, keywords, max_results=10):
        return [
            inf.SocialMediaProfile(
                platform="bluesky",
                username="creator.one",
                display_name="Creator One",
                profile_url="https://bsky.app/profile/creator.one",
                followers=320,
                engagement_rate=4.2,
                bio="startup automation creator",
            )
        ]


def test_discovery_saves_profiles_with_stubbed_platform(monkeypatch, tmp_path):
    monkeypatch.setattr(inf, "project_root", Path(tmp_path))

    discovery = inf.BrandInfluencerDiscovery()
    discovery.platforms = {"bluesky": FakeSearcher()}

    import asyncio

    results = asyncio.run(discovery.discover_brand_influencers("buildly", max_per_platform=3))

    assert "bluesky" in results
    assert len(results["bluesky"]) == 1

    saved = discovery.get_brand_influencers(brand="buildly")
    assert len(saved) == 1
    assert saved[0]["name"] == "Creator One"


def test_discovery_unknown_brand_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(inf, "project_root", Path(tmp_path))
    discovery = inf.BrandInfluencerDiscovery()

    import asyncio

    results = asyncio.run(discovery.discover_brand_influencers("brand_that_does_not_exist_123", max_per_platform=2))
    assert results == {}
