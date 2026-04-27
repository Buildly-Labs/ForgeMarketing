#!/usr/bin/env python3
"""Runtime unified email service used by dashboard endpoints."""

from __future__ import annotations

import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

import requests


class UnifiedEmailService:
    """Route outbound email through MailerSend or Brevo based on brand."""

    def __init__(self) -> None:
        self.service_routing = {
            'buildly': 'mailersend',
            'foundry': 'brevo',
            'openbuild': 'brevo',
            'open_build': 'brevo',
            'oregonsoftware': 'brevo',
            'radical': 'brevo',
            'radical_therapy': 'brevo',
        }
        self.mailersend_config = {
            'api_token': os.getenv('MAILERSEND_API_TOKEN', ''),
            'api_url': 'https://api.mailersend.com/v1/email',
            'from_email': os.getenv('MAILERSEND_FROM_EMAIL', 'hello@buildly.io'),
            'from_name': os.getenv('MAILERSEND_FROM_NAME', 'Buildly'),
        }
        self.brevo_config = {
            'host': os.getenv('BREVO_SMTP_HOST', 'smtp-relay.brevo.com'),
            'port': int(os.getenv('BREVO_SMTP_PORT', '587')),
            'user': os.getenv('BREVO_SMTP_USER', ''),
            'password': os.getenv('BREVO_SMTP_PASSWORD', ''),
            'from_email': os.getenv('BREVO_FROM_EMAIL', 'team@open.build'),
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
        service_name = self.service_routing.get((brand or '').lower(), 'brevo')
        if service_name == 'mailersend':
            if self.mailersend_config['api_token']:
                return self._send_via_mailersend(to_email, subject, body, is_html, bcc_email)
            if self.brevo_config['user'] and self.brevo_config['password']:
                result = self._send_via_brevo(to_email, subject, body, is_html, bcc_email)
                result['service'] = 'brevo_fallback'
                result['routing_note'] = 'Brevo fallback used because MailerSend is not configured'
                return result
            raise RuntimeError('MailerSend API token not configured')
        return self._send_via_brevo(to_email, subject, body, is_html, bcc_email)

    def _send_via_mailersend(
        self,
        to_email: str,
        subject: str,
        body: str,
        is_html: bool,
        bcc_email: Optional[str],
    ) -> Dict[str, Any]:
        if not self.mailersend_config['api_token']:
            raise RuntimeError('MailerSend API token not configured')

        payload: Dict[str, Any] = {
            'from': {
                'email': self.mailersend_config['from_email'],
                'name': self.mailersend_config['from_name'],
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
            self.mailersend_config['api_url'],
            json=payload,
            headers={
                'Authorization': f"Bearer {self.mailersend_config['api_token']}",
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
    ) -> Dict[str, Any]:
        if not self.brevo_config['user'] or not self.brevo_config['password']:
            raise RuntimeError('Brevo SMTP credentials not configured')

        msg = MIMEMultipart('alternative')
        msg['From'] = self.brevo_config['from_email']
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

        server = smtplib.SMTP(self.brevo_config['host'], self.brevo_config['port'])
        server.starttls()
        server.login(self.brevo_config['user'], self.brevo_config['password'])
        server.sendmail(self.brevo_config['from_email'], recipients, msg.as_string())
        server.quit()

        return {
            'success': True,
            'service': 'brevo',
            'recipients': recipients,
            'routing_note': 'Brevo SMTP routing',
        }

    def _html_to_text(self, html: str) -> str:
        return re.sub(re.compile('<.*?>'), '', html).strip()