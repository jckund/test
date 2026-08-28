#!/usr/bin/env python3
"""Send the weekly Caliber changes email over Gmail/Workspace SMTP.

Uses only the Python standard library (smtplib) so there is no third-party
GitHub Action dependency. Reads the message produced by caliber_report.py and
the credentials from the environment:

  MAIL_USERNAME  full Google address that authenticates + appears as From
  MAIL_PASSWORD  a Google *app password* (not the normal account password)
  MAIL_TO        recipient (optional; defaults to justin@vivecollision.com)

Gmail SMTP: smtp.gmail.com:465 (implicit TLS). An app password requires 2-Step
Verification enabled on the Google account. Exits non-zero on failure so the
workflow surfaces a delivery problem instead of silently dropping it.
"""
import os
import re
import smtplib
import ssl
import sys
from email.message import EmailMessage

SUBJECT_PATH = "email_subject.txt"
BODY_PATH = "email_body.html"
TO_DEFAULT = "justin@vivecollision.com"
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))


def html_to_text(h):
    t = re.sub(r"(?s)<(script|style).*?</\1>", "", h)
    t = re.sub(r"(?i)<br\s*/?>", "\n", t)
    t = re.sub(r"(?i)</(li|p|h1|h2|h3|div|ul)>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"&middot;", "-", t)
    t = re.sub(r"&nbsp;", " ", t)
    t = re.sub(r"&amp;", "&", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def main():
    user = os.environ.get("MAIL_USERNAME", "").strip()
    pw = os.environ.get("MAIL_PASSWORD", "").strip()
    to = os.environ.get("MAIL_TO", "").strip() or TO_DEFAULT
    if not user or not pw:
        print("ERROR: MAIL_USERNAME / MAIL_PASSWORD not set — cannot send email.",
              file=sys.stderr)
        return 2
    if not (os.path.exists(SUBJECT_PATH) and os.path.exists(BODY_PATH)):
        print("ERROR: email_subject.txt / email_body.html missing — nothing to send.",
              file=sys.stderr)
        return 2

    subject = open(SUBJECT_PATH).read().strip()
    body_html = open(BODY_PATH).read()

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"Gerber Location Watch <{user}>"
    msg["To"] = to
    msg.set_content(html_to_text(body_html))
    msg.add_alternative(body_html, subtype="html")

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=60) as s:
        s.login(user, pw)
        s.send_message(msg)
    print(f"Sent '{subject}' to {to}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
