"""Proof-based match eligibility for Quarterly Room intakes.

There is deliberately no score. Eligibility is a set of yes/no rules over
structured fields only; free-text descriptions (company_description etc.) are
never used to infer a match. Everything here is advisory input for a human
reviewer - nothing in this module contacts anyone or rewrites a statement.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List

from custom_modules.quarterly_room.validation import (
    CONNECTOR_EVIDENCE_KEYS,
    OWNER_COST_KEYS,
    SOLVER_PROOF_KEYS,
    SOLVER_RESULT_KEYS,
    first_present,
    has_content,
)


def quarter_label(moment: datetime) -> str:
    return f"{moment.year}-Q{(moment.month - 1) // 3 + 1}"


def _details(intake: Any) -> Dict[str, Any]:
    d = getattr(intake, "problem_details", None)
    return d if isinstance(d, dict) else {}


def in_matching_pool(intake: Any, quarter: str) -> bool:
    """Holds ("Not this quarter") are stored but never matched; so are
    submissions from other quarters and ones a reviewer declined."""
    return (
        not getattr(intake, "is_hold", False)
        and getattr(intake, "quarter_label", None) == quarter
        and getattr(intake, "review_status", "received") != "declined"
    )


def owner_eligible(intake: Any) -> bool:
    revenue = list(getattr(intake, "revenue_bands", None) or [])
    return (
        intake.seat == "problem_owner"
        and not intake.is_hold
        and bool(intake.problem_category)
        and len(revenue) == 1
        and has_content(first_present(_details(intake), OWNER_COST_KEYS))
    )


def solver_has_proof(intake: Any) -> bool:
    d = _details(intake)
    return has_content(first_present(d, SOLVER_RESULT_KEYS)) and has_content(first_present(d, SOLVER_PROOF_KEYS))


def solver_eligible(intake: Any) -> bool:
    return (
        intake.seat == "problem_solver"
        and not intake.is_hold
        and bool(intake.problem_category)
        and bool(getattr(intake, "revenue_bands", None))
        and solver_has_proof(intake)
    )


def connector_eligible(intake: Any) -> bool:
    return (
        intake.seat == "connector"
        and not intake.is_hold
        and bool(intake.problem_category)
        and has_content(first_present(_details(intake), CONNECTOR_EVIDENCE_KEYS))
    )


def room_builder_can_design(intake: Any) -> bool:
    """Room builders whose last room was mostly sellers can help design the next."""
    if intake.seat != "room_builder" or intake.is_hold:
        return False
    d = _details(intake)
    if d.get("last_room_mostly_sellers") is True:
        return True
    mix = d.get("last_room_mix")
    return isinstance(mix, str) and mix.strip().lower().replace(" ", "_") == "mostly_sellers"


def owner_solver_match(owner: Any, solver: Any) -> bool:
    """Same category, owner's revenue band among the solver's, plus the proof
    requirements on each side. People bands are context only."""
    if not (owner_eligible(owner) and solver_eligible(solver)):
        return False
    if owner.quarter_label != solver.quarter_label:
        return False
    if owner.problem_category != solver.problem_category:
        return False
    return owner.revenue_bands[0] in (solver.revenue_bands or [])


def may_contact(intake: Any) -> bool:
    return getattr(intake, "contact_permission", "no") == "yes"


def solvers_for(owner: Any, pool: Iterable[Any]) -> List[Any]:
    return [s for s in pool if owner_solver_match(owner, s)]


def connectors_for(owner: Any, pool: Iterable[Any]) -> List[Any]:
    return [c for c in pool if connector_eligible(c) and c.problem_category == owner.problem_category]


def eligibility(intake: Any) -> Dict[str, Any]:
    """Per-intake summary shown to reviewers."""
    return {
        "match_eligible": owner_eligible(intake) or solver_eligible(intake) or connector_eligible(intake),
        "in_current_matching": not intake.is_hold,
        "outreach_permitted": may_contact(intake),
        "room_design_contributor": room_builder_can_design(intake),
    }
