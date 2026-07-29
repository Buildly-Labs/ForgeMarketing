#!/usr/bin/env python3
"""
Twitter Content Loader
Provides tweet text templates for the scheduler.

This file no longer posts automatically. Use tweet_scheduler.py with
--dry-run or --run instead.
"""


def get_tweets():
    return [
        "Plan content, approvals, and scheduling in one place. A calm workflow keeps marketing moving.",
        "Turn campaign ideas into drafts, review notes, and next steps without losing track of the work.",
        "Use simple checklists for manual posting, account setup, and weekly performance review.",
        "Keep brand voice, assets, and platform drafts together so your team can move faster.",
        "Human-in-the-loop marketing works better than automation when approval matters.",
        "Track what is drafted, approved, scheduled, posted, and ready for performance checks.",
        "A marketing command center for interns and founder-led teams.",
        "Create platform-specific drafts, attach assets, and keep humans responsible for publishing.",
        "Manage campaigns with clear owners, due dates, and notes for every manual task.",
        "Keep content organized across platforms without risky automation.",
    ]
