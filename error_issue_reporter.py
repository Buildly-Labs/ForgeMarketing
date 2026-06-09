"""Automatic GitHub issue reporter for server errors.

Routes issues to ForgeMarketing upstream or custom-module repository based on error path/trace.
Safe fail: never raises, never blocks request handling for long.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import traceback
from typing import Optional

import requests

FORGE_REPO = "Buildly-Marketplace/ForgeMarketing"
COOLDOWN_HOURS = 6

PROJECT_ROOT = Path(__file__).resolve().parent
CACHE_FILE = PROJECT_ROOT / "data" / "auto_issue_cache.json"
LOG_DIR = PROJECT_ROOT / "logs"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _github_token() -> str:
    return (os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or "").strip()


def _detect_current_repo() -> str:
    env_repo = (os.getenv("GITHUB_REPOSITORY") or "").strip()
    if env_repo and "/" in env_repo:
        return env_repo

    try:
        remote = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=str(PROJECT_ROOT),
            text=True,
            timeout=2,
        ).strip()
        if remote.startswith("git@github.com:"):
            slug = remote.split("git@github.com:", 1)[1]
        elif "github.com/" in remote:
            slug = remote.split("github.com/", 1)[1]
        else:
            return FORGE_REPO
        if slug.endswith(".git"):
            slug = slug[:-4]
        return slug if "/" in slug else FORGE_REPO
    except Exception:
        return FORGE_REPO


def _custom_repo() -> str:
    return (os.getenv("CUSTOM_MODULE_ISSUES_REPO") or _detect_current_repo()).strip()


def _is_custom_module_error(path: str, trace_text: str) -> bool:
    custom_prefixes = (
        "/api/the-index",
        "/api/index-submissions",
        "/the-index",
        "/api/custom-",
    )
    if path.startswith(custom_prefixes):
        return True
    return "custom_modules/" in (trace_text or "")


def _load_cache() -> dict:
    try:
        if CACHE_FILE.exists():
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_cache(cache: dict) -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=True, indent=2), encoding="utf-8")
    except Exception:
        pass


def _should_skip(signature: str) -> bool:
    cache = _load_cache()
    entry = cache.get(signature)
    if not entry:
        return False
    try:
        ts = datetime.fromisoformat(entry.get("last_reported_at"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return _now_utc() - ts < timedelta(hours=COOLDOWN_HOURS)
    except Exception:
        return False


def _extract_issue_number(issue_url: str) -> Optional[int]:
    try:
        return int((issue_url or "").rstrip("/").split("/")[-1])
    except Exception:
        return None


def _safe_text(value: object, limit: int = 1200) -> str:
    text = str(value or "")
    text = text.replace("\x00", "")
    if len(text) > limit:
        text = text[:limit] + "..."
    return text


def _build_trace_text(exception: Exception) -> str:
    try:
        tb = traceback.TracebackException.from_exception(exception)
        formatted = "".join(tb.format())
        if formatted.strip():
            return formatted
    except Exception:
        pass

    try:
        formatted = traceback.format_exc()
        if formatted and not formatted.strip().endswith("NoneType: None"):
            return formatted
    except Exception:
        pass
    return ""


def _collect_request_context() -> str:
    try:
        from flask import has_request_context, request

        if not has_request_context():
            return "Request context unavailable"

        headers = {
            "Host": request.headers.get("Host", ""),
            "X-Forwarded-For": request.headers.get("X-Forwarded-For", ""),
            "X-Real-IP": request.headers.get("X-Real-IP", ""),
            "User-Agent": request.headers.get("User-Agent", ""),
            "Referer": request.headers.get("Referer", ""),
            "Origin": request.headers.get("Origin", ""),
            "Content-Type": request.headers.get("Content-Type", ""),
        }
        query = dict(request.args.items())
        body_preview = request.get_data(cache=False, as_text=True) or ""
        body_preview = _safe_text(body_preview, limit=1200)

        lines = [
            f"- Full Path: {_safe_text(request.full_path, 800)}",
            f"- Remote Addr: {_safe_text(request.remote_addr, 200)}",
            f"- Query Params: {_safe_text(json.dumps(query, ensure_ascii=True), 1200)}",
            f"- Headers: {_safe_text(json.dumps(headers, ensure_ascii=True), 2000)}",
            f"- Body Preview: {_safe_text(body_preview, 1200)}",
        ]
        return "\n".join(lines)
    except Exception as exc:
        return f"Request context unavailable: {_safe_text(exc, 400)}"


def _tail_lines(path: Path, max_lines: int = 600) -> list[str]:
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    lines = raw.splitlines()
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return lines


def _recent_log_excerpt(path: str, exc_type: str, exc_message: str) -> str:
    keywords = [
        (path or "").strip(),
        (exc_type or "").strip(),
        (exc_message or "").strip(),
        "lead-radar",
        "ERROR",
        "Traceback",
    ]
    keywords = [k for k in keywords if k]
    pattern = re.compile("|".join(re.escape(k) for k in keywords), re.IGNORECASE) if keywords else None

    candidates: list[Path] = []
    if LOG_DIR.exists():
        candidates.extend(sorted(LOG_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True))
        candidates.extend(sorted(LOG_DIR.glob("*.out"), key=lambda p: p.stat().st_mtime, reverse=True))

    # Include top-level log files as fallback.
    candidates.extend(
        sorted(PROJECT_ROOT.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    )

    seen = set()
    snippets = []
    for log_path in candidates:
        if log_path in seen:
            continue
        seen.add(log_path)

        lines = _tail_lines(log_path)
        if not lines:
            continue

        hits = []
        for idx, line in enumerate(lines):
            if pattern and not pattern.search(line):
                continue
            start = max(0, idx - 2)
            end = min(len(lines), idx + 3)
            chunk = "\n".join(lines[start:end])
            hits.append(chunk)
            if len(hits) >= 3:
                break

        if not hits:
            # Fallback: provide last few lines from newest logs for context.
            hits = ["\n".join(lines[-12:])]

        snippet_text = "\n\n---\n\n".join(hits)
        snippets.append(f"## {log_path.name}\n```\n{_safe_text(snippet_text, 5000)}\n```")
        if len(snippets) >= 2:
            break

    return "\n\n".join(snippets) if snippets else "No log files found."


def _mark_reported(signature: str, repo: str, issue_url: str) -> None:
    issue_number = _extract_issue_number(issue_url)
    cache = _load_cache()
    cache[signature] = {
        "last_reported_at": _now_utc().isoformat(),
        "repo": repo,
        "issue_url": issue_url,
        "issue_number": issue_number,
        "repeat_count": 1,
        "comments_posted": 0,
        "reaction_added": False,
    }
    _save_cache(cache)


def _post_repeat_comment(repo: str, issue_number: int, token: str, repeat_count: int, detail_block: str) -> bool:
    try:
        message = (
            f"Automated repeat detection: this error occurred again. "
            f"Occurrence count: {repeat_count}.\n\n"
            f"{detail_block}"
        )
        response = requests.post(
            f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={"body": message},
            timeout=8,
        )
        return response.status_code in (200, 201)
    except Exception:
        return False


def _add_issue_vote(repo: str, issue_number: int, token: str) -> bool:
    try:
        response = requests.post(
            f"https://api.github.com/repos/{repo}/issues/{issue_number}/reactions",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={"content": "+1"},
            timeout=8,
        )
        # 201 created, 200 already exists for this actor in some API behaviors.
        return response.status_code in (200, 201)
    except Exception:
        return False


def _handle_repeat(signature: str, token: str, detail_block: str) -> bool:
    """Handle repeated occurrences by commenting (up to 4) then adding a vote reaction."""
    cache = _load_cache()
    entry = cache.get(signature)
    if not entry:
        return False

    repo = entry.get("repo") or ""
    issue_number = entry.get("issue_number")
    if not repo or not issue_number:
        return False

    repeat_count = int(entry.get("repeat_count") or 1) + 1
    comments_posted = int(entry.get("comments_posted") or 0)
    reaction_added = bool(entry.get("reaction_added"))

    acted = False
    if comments_posted < 4:
        if _post_repeat_comment(repo, int(issue_number), token, repeat_count, detail_block):
            comments_posted += 1
            acted = True
    elif not reaction_added:
        if _add_issue_vote(repo, int(issue_number), token):
            reaction_added = True
            acted = True

    entry.update(
        {
            "last_reported_at": _now_utc().isoformat(),
            "repeat_count": repeat_count,
            "comments_posted": comments_posted,
            "reaction_added": reaction_added,
        }
    )
    cache[signature] = entry
    _save_cache(cache)
    return acted


def report_server_error(exception: Exception, path: str, method: str, component: str = "app") -> Optional[str]:
    """Create a GitHub issue for an unhandled server error.

    Returns created issue URL, or None when skipped/failed.
    """
    token = _github_token()
    if not token:
        return None

    # Build traceback text safely.
    trace_text = _build_trace_text(exception)

    exc_type = type(exception).__name__ if exception else "Exception"
    exc_message = str(exception) if exception else ""

    repo = _custom_repo() if _is_custom_module_error(path or "", trace_text) else FORGE_REPO

    request_context = _collect_request_context()
    log_excerpt = _recent_log_excerpt(path, exc_type, exc_message)
    detail_block = (
        "Request context:\n"
        f"{request_context}\n\n"
        "Recent server logs:\n"
        f"{log_excerpt}"
    )

    signature_input = f"{repo}|{component}|{path}|{method}|{exc_type}|{exc_message[:180]}"
    signature = hashlib.sha256(signature_input.encode("utf-8")).hexdigest()
    if _should_skip(signature):
        _handle_repeat(signature, token, detail_block)
        return None

    title = f"[Auto][{component}] {exc_type} at {path}"
    body = (
        "An unhandled server error occurred and was auto-reported.\n\n"
        f"- Time (UTC): {_now_utc().isoformat()}\n"
        f"- Method: {method}\n"
        f"- Path: {path}\n"
        f"- Component: {component}\n"
        f"- Exception: {exc_type}: {exc_message}\n\n"
        "Traceback:\n"
        "```\n"
        f"{trace_text or 'Traceback unavailable'}\n"
        "```\n"
        "\n"
        f"{detail_block}\n"
    )

    try:
        response = requests.post(
            f"https://api.github.com/repos/{repo}/issues",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={"title": title, "body": body},
            timeout=8,
        )
        if response.status_code not in (200, 201):
            return None
        issue_url = response.json().get("html_url")
        if issue_url:
            _mark_reported(signature, repo, issue_url)
        return issue_url
    except Exception:
        return None
