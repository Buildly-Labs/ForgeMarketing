#!/usr/bin/env python3
"""Neutral runtime outreach service used by dashboard endpoints."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from unified_email_service import UnifiedEmailService


@dataclass
class OutreachUser:
    email: str
    name: str = 'Sample User'
    company: str = 'Sample Company'
    account_type: str = 'Free'
    last_login: str = ''
    signup_date: str = ''
    features_used: str = ''
    subscription_status: str = 'Active'
    usage_level: str = 'Medium'


class BrandOutreachService:
    """Brand-agnostic outreach message generation and campaign execution."""

    def __init__(self, brand_name: Optional[str] = None):
        self.brand_name = brand_name or 'brand'
        self.email_service = UnifiedEmailService()

    def generate_outreach_message(
        self,
        user: OutreachUser,
        template_name: str,
        custom_subject: str = '',
        custom_message: str = '',
    ) -> Dict[str, str]:
        brand_label = self.brand_name.replace('_', ' ').title()
        subject = custom_subject or f'{brand_label} | {template_name.replace("_", " ").title()}'
        body = custom_message or (
            f'Hi {user.name},\n\n'
            f'I\'m reaching out on behalf of {brand_label}. '
            f'We thought {user.company} might be a strong fit for a {template_name.replace("_", " ")} conversation.\n\n'
            f'Account type: {user.account_type}\n'
            f'Subscription status: {user.subscription_status}\n'
            f'Usage level: {user.usage_level}\n\n'
            'If this is relevant, reply and we can share more details.\n\n'
            f'Best,\n{brand_label} Team'
        )
        return {
            'subject': subject,
            'body': body,
            'template_used': template_name,
        }

    def run_outreach_campaign(
        self,
        csv_file: str,
        template_name: str,
        preview_only: bool = False,
        custom_subject: str = '',
        custom_message: str = '',
        skip_recent: bool = True,
        max_emails: Optional[int] = None,
        bcc_email: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, str, str], None]] = None,
    ) -> Dict[str, Any]:
        rows = self._load_csv_rows(csv_file)
        users = [self._row_to_user(row) for row in rows if row.get('email')]
        if max_emails is not None:
            users = users[:max_emails]

        sent = 0
        failed = 0
        previews: List[Dict[str, str]] = []

        for index, user in enumerate(users):
            if progress_callback:
                progress_callback(index, len(users), user.email, 'processing')

            message = self.generate_outreach_message(user, template_name, custom_subject, custom_message)
            if preview_only:
                previews.append({'email': user.email, **message})
                if progress_callback:
                    progress_callback(index, len(users), user.email, 'sent')
                sent += 1
                continue

            try:
                self.email_service.send_email(
                    brand=self.brand_name,
                    to_email=user.email,
                    subject=message['subject'],
                    body=message['body'],
                    is_html=False,
                    bcc_email=bcc_email,
                )
                sent += 1
                if progress_callback:
                    progress_callback(index, len(users), user.email, 'sent')
            except Exception:
                failed += 1
                if progress_callback:
                    progress_callback(index, len(users), user.email, 'failed')

        return {
            'total_users': len(users),
            'emails_sent': sent,
            'emails_failed': failed,
            'skipped_opted_out': 0,
            'skipped_recent': 0,
            'preview_messages': previews,
            'preview_only': preview_only,
            'skip_recent': skip_recent,
        }

    def _load_csv_rows(self, csv_file: str) -> List[Dict[str, str]]:
        path = Path(csv_file)
        with path.open('r', encoding='utf-8', newline='') as handle:
            return list(csv.DictReader(handle))

    def _row_to_user(self, row: Dict[str, str]) -> OutreachUser:
        full_name = row.get('name') or ' '.join(
            part for part in [row.get('first_name', ''), row.get('last_name', '')] if part
        ).strip() or 'Valued User'
        return OutreachUser(
            email=row.get('email', ''),
            name=full_name,
            company=row.get('company', 'Sample Company'),
            account_type=row.get('account_type', row.get('plan', 'Free')),
            last_login=row.get('last_login', row.get('last_active', '')),
            signup_date=row.get('signup_date', row.get('created_at', '')),
            features_used=row.get('features_used', row.get('modules', '')),
            subscription_status=row.get('subscription_status', row.get('status', 'Active')),
            usage_level=row.get('usage_level', row.get('tier', 'Medium')),
        )