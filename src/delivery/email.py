"""
Email delivery via Gmail SMTP.
Reads subscriber list from data/subscribers.csv.
Credentials come from environment variables (set as GitHub Secrets).
"""

import os
import csv
import logging
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

logger = logging.getLogger(__name__)

SUBSCRIBERS_PATH = Path('data/subscribers.csv')
FROM_NAME = 'L&A Actuarial Intelligence'


def _load_subscribers() -> list[str]:
    """Read subscriber email addresses from CSV."""
    if not SUBSCRIBERS_PATH.exists():
        logger.warning("No subscribers.csv found at %s", SUBSCRIBERS_PATH)
        return []

    emails = []
    with open(SUBSCRIBERS_PATH, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            email = (row.get('email') or row.get('Email') or '').strip()
            if email and '@' in email:
                emails.append(email)

    logger.info("Loaded %d subscribers", len(emails))
    return emails


def _build_message(subject: str, html_body: str, to_email: str) -> MIMEMultipart:
    """Build a MIME email message."""
    smtp_user = os.environ['SMTP_USER']
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = formataddr((FROM_NAME, smtp_user))
    msg['To'] = to_email
    msg['X-Mailer'] = 'LA-Intelligence/1.0'
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))
    return msg


def send_daily_digest(html: str, article_count: int) -> dict:
    """
    Send the daily digest to all subscribers.
    Returns {'sent': N, 'failed': M}.
    """
    smtp_user = os.environ.get('SMTP_USER')
    smtp_password = os.environ.get('SMTP_PASSWORD')
    smtp_host = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
    smtp_port = int(os.environ.get('SMTP_PORT', '587'))

    if not smtp_user or not smtp_password:
        logger.error("SMTP_USER or SMTP_PASSWORD not set — skipping email")
        return {'sent': 0, 'failed': 0}

    subscribers = _load_subscribers()
    if not subscribers:
        logger.warning("No subscribers — nothing to send")
        return {'sent': 0, 'failed': 0}

    today_str = date.today().strftime('%B %-d, %Y')
    subject = f"L&A Actuarial Intelligence — {today_str} ({article_count} items)"

    stats = {'sent': 0, 'failed': 0}

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_password)

            for email in subscribers:
                try:
                    msg = _build_message(subject, html, email)
                    server.sendmail(smtp_user, email, msg.as_string())
                    stats['sent'] += 1
                    logger.info("Sent to %s", email)
                except smtplib.SMTPException as exc:
                    logger.error("Failed to send to %s: %s", email, exc)
                    stats['failed'] += 1

    except Exception as exc:
        logger.error("SMTP connection failed: %s", exc)
        stats['failed'] = len(subscribers)

    logger.info("Email delivery complete: %s", stats)
    return stats
