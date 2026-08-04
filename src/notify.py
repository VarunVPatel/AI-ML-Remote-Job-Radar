"""Stage 4: email the digest with tailored resumes attached."""
from __future__ import annotations

import json
import mimetypes
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"

MAX_ATTACH_MB = 20


def main():
    user = os.environ["SMTP_USER"]
    pw = os.environ["SMTP_PASS"]
    to = os.environ.get("MAIL_TO", user)
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))

    body = (OUT / "digest.html").read_text()
    attachments = []
    f = OUT / "attachments.json"
    if f.exists():
        attachments = [Path(p) for p in json.loads(f.read_text()) if Path(p).exists()]

    n = len(json.loads((ROOT / "work" / "screened.json").read_text())) \
        if (ROOT / "work" / "screened.json").exists() else 0

    msg = EmailMessage()
    msg["Subject"] = f"{n} AI/ML remote roles — {datetime.now().strftime('%d %b')}"
    msg["From"] = user
    msg["To"] = to
    msg.set_content("Your job digest is HTML. Open in an HTML-capable client.")
    msg.add_alternative(body, subtype="html")

    total = 0
    for p in attachments:
        size = p.stat().st_size
        if total + size > MAX_ATTACH_MB * 1024 * 1024:
            print(f"  skipping {p.name} (attachment size cap)")
            continue
        total += size
        ctype, _ = mimetypes.guess_type(p.name)
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        msg.add_attachment(p.read_bytes(), maintype=maintype,
                           subtype=subtype, filename=p.name)

    with smtplib.SMTP_SSL(host, port) as s:
        s.login(user, pw)
        s.send_message(msg)

    print(f"Sent to {to}: {n} jobs, {len(attachments)} attachments")


if __name__ == "__main__":
    main()
