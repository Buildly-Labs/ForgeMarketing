#!/usr/bin/env python3
"""Runtime unified email service used by dashboard endpoints."""

from __future__ import annotations

import os
import re
import sqlite3
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, Optional

import requests


project_root = Path(__file__).resolve().parent


class UnifiedEmailService:
    """Route outbound email through MailerSend or Brevo based on brand."""

    def __init__(self) -> None:
        self.default_mailersend_config = {
            'api_token': os.getenv('MAILERSEND_API_TOKEN', ''),
            'api_url': 'https://api.mailersend.com/v1/email',
            'from_email': os.getenv('MAILERSEND_FROM_EMAIL', 'no-reply@example.invalid'),
            'from_name': os.getenv('MAILERSEND_FROM_NAME', 'Marketing Team'),
        }
        self.default_brevo_config = {
            'host': os.getenv('BREVO_SMTP_HOST', 'smtp-relay.brevo.com'),
            'port': int(os.getenv('BREVO_SMTP_PORT', '587')),
            'user': os.getenv('BREVO_SMTP_USER', ''),
            'password': os.getenv('BREVO_SMTP_PASSWORD', ''),
            'from_email': os.getenv('BREVO_FROM_EMAIL', 'no-reply@example.invalid'),
            'from_name': os.getenv('BREVO_FROM_NAME', 'Marketing Team'),
        }

    def send_email(
        self,
        brand: str,
        to_email: str,
        subject: str,
        body: str,
        is_html: bool = False,
        bcc_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        brand_config = self._load_brand_email_config(brand)
        service_name = (brand_config or {}).get('provider', 'brevo').lower()
        if service_name == 'mailersend':
            mailersend_config = self._build_mailersend_config(brand_config)
            if mailersend_config['api_token']:
                return self._send_via_mailersend(to_email, subject, body, is_html, bcc_email, mailersend_config)
            brevo_config = self._build_brevo_config(brand_config)
            if brevo_config['user'] and brevo_config['password']:
                result = self._send_via_brevo(to_email, subject, body, is_html, bcc_email, brevo_config)
                result['service'] = 'brevo_fallback'
                result['routing_note'] = 'Brevo fallback used because MailerSend is not configured'
                return result
            raise RuntimeError('MailerSend API token not configured')
        brevo_config = self._build_brevo_config(brand_config)
        return self._send_via_brevo(to_email, subject, body, is_html, bcc_email, brevo_config)

    def _normalize_brand_key(self, value: str) -> str:
        normalized = re.sub(r'[^a-z0-9]+', '_', (value or '').lower().strip())
        return normalized.strip('_')

    def _load_brand_email_config(self, brand: str) -> Optional[Dict[str, Any]]:
        db_path = project_root / 'data' / 'marketing_dashboard.db'
        if not db_path.exists() or not brand:
            return None

        requested_raw = (brand or '').strip().lower()
        requested_normalized = self._normalize_brand_key(brand)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT
                    b.name AS brand_name,
                    b.display_name AS brand_display_name,
                    c.provider,
                    c.api_key,
                    c.api_token,
                    c.smtp_host,
                    c.smtp_port,
                    c.smtp_user,
                    c.smtp_password,
                    c.from_email,
                    c.from_name,
                    c.reply_to_email,
                    c.reply_to_name,
                    c.is_primary
                FROM brands b
                JOIN brand_email_configs c ON c.brand_id = b.id
                WHERE b.is_active = 1
                ORDER BY c.is_primary DESC, c.updated_at DESC, c.created_at DESC
                """
            ).fetchall()

            for row in rows:
                row_dict = dict(row)
                candidates = {
                    (row_dict.get('brand_name') or '').lower(),
                    (row_dict.get('brand_display_name') or '').lower(),
                    self._normalize_brand_key(row_dict.get('brand_name') or ''),
                    self._normalize_brand_key(row_dict.get('brand_display_name') or ''),
                }
                if requested_raw in candidates or requested_normalized in candidates:
                    return row_dict
            return None
        finally:
            conn.close()

    def _build_mailersend_config(self, brand_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        config = dict(self.default_mailersend_config)
        if brand_config:
            config['api_token'] = brand_config.get('api_token') or brand_config.get('api_key') or config['api_token']
            config['from_email'] = brand_config.get('from_email') or config['from_email']
            config['from_name'] = brand_config.get('from_name') or brand_config.get('brand_display_name') or config['from_name']
        return config

    def _build_brevo_config(self, brand_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        config = dict(self.default_brevo_config)
        if brand_config:
            config['host'] = brand_config.get('smtp_host') or config['host']
            config['port'] = int(brand_config.get('smtp_port') or config['port'])
            config['user'] = brand_config.get('smtp_user') or config['user']
            config['password'] = brand_config.get('smtp_password') or config['password']
            config['from_email'] = brand_config.get('from_email') or config['from_email']
            config['from_name'] = brand_config.get('from_name') or brand_config.get('brand_display_name') or config['from_name']
        return config

    def _send_via_mailersend(
        self,
        to_email: str,
        subject: str,
        body: str,
        is_html: bool,
        bcc_email: Optional[str],
        mailersend_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not mailersend_config['api_token']:
            raise RuntimeError('MailerSend API token not configured')

        payload: Dict[str, Any] = {
            'from': {
                'email': mailersend_config['from_email'],
                'name': mailersend_config['from_name'],
            },
            'to': [{'email': to_email}],
            'subject': subject,
            'text': self._html_to_text(body) if is_html else body,
        }
        if is_html:
            payload['html'] = body
        if bcc_email and bcc_email.lower() != to_email.lower():
            payload['bcc'] = [{'email': bcc_email}]

        response = requests.post(
            mailersend_config['api_url'],
            json=payload,
            headers={
                'Authorization': f"Bearer {mailersend_config['api_token']}",
                'Content-Type': 'application/json',
            },
            timeout=30,
        )
        if response.status_code != 202:
            raise RuntimeError(f'MailerSend API error: {response.status_code} - {response.text}')

        return {
            'success': True,
            'service': 'mailersend',
            'message_id': response.headers.get('x-message-id', 'N/A'),
            'routing_note': 'MailerSend primary routing',
        }

    def _send_via_brevo(
        self,
        to_email: str,
        subject: str,
        body: str,
        is_html: bool,
        bcc_email: Optional[str],
        brevo_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not brevo_config['user'] or not brevo_config['password']:
            raise RuntimeError('Brevo SMTP credentials not configured')

        msg = MIMEMultipart('alternative')
        msg['From'] = brevo_config['from_email']
        msg['To'] = to_email
        msg['Subject'] = subject
        if bcc_email:
            msg['Bcc'] = bcc_email

        if is_html:
            msg.attach(MIMEText(self._html_to_text(body), 'plain'))
            msg.attach(MIMEText(body, 'html'))
        else:
            msg.attach(MIMEText(body, 'plain'))

        recipients = [to_email]
        if bcc_email:
            recipients.append(bcc_email)

        server = smtplib.SMTP(brevo_config['host'], brevo_config['port'])
        server.starttls()
        server.login(brevo_config['user'], brevo_config['password'])
        server.sendmail(brevo_config['from_email'], recipients, msg.as_string())
        server.quit()

        return {
            'success': True,
            'service': 'brevo',
            'recipients': recipients,
            'routing_note': 'Brevo SMTP routing',
        }

    def _html_to_text(self, html: str) -> str:
        return re.sub(re.compile('<.*?>'), '', html).strip()