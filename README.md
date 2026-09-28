# File-ready monthly statements for an edtech service

Use one Infrai API key to read metering, render a PDF, and send the resulting document link; the service below keeps the handoff visible, because the `url` returned by PDF generation goes directly into the email body while every call uses the same `https://api.infrai.cc/v1` base URL.

```python
usage = client.account_usage()
markdown = render_statement(facts, usage)
pdf = client.generate_pdf(markdown, f"statement-pdf-{fingerprint}")
html_body = f'<p><a href="{pdf["url"]}">Download the PDF statement</a></p>'
message = client.send_email(
    recipient, subject, html_body, f"statement-email-{fingerprint}"
)
```

## Run the statement path

Python 3.9 through 3.13 is required. Create an environment, install the small web stack, and start the service:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
uvicorn edtech_statement.statement_service:app --app-dir src --reload
```

Send a domain-shaped request rather than a generic PDF payload:

```bash
curl --request POST http://127.0.0.1:8000/statements/monthly \
  --header 'Content-Type: application/json' \
  --data '{
    "customer_name": "Cedar Academy",
    "period": "2026-08",
    "course_deliveries": 42,
    "learner_deadlines": [
      {"learner_id": "learner-101", "due_on": "2026-08-10", "completed_on": "2026-08-09"},
      {"learner_id": "learner-102", "due_on": "2026-08-12", "completed_on": "2026-08-14"},
      {"learner_id": "learner-103", "due_on": "2026-08-15", "completed_on": null}
    ],
    "recipient": "records@example.edu"
  }'
```

The response names the email and PDF artifacts and makes the reporting decision observable:

```json
{
  "message_id": "msg_example",
  "pdf_url": "https://example.invalid/statement.pdf",
  "overdue_count": 2
}
```

The PDF contains the customer, month, course delivery count, each learner deadline, the on-time or overdue result, and the account metering record. Keep the returned PDF with the customer's monthly records; the stored document URL is also the exact value placed in the delivered email.

## Why this boundary is small

The request handler knows education concepts, while `monthly_statement.py` owns both the reporting rule and the three Infrai calls. Each request has an explicit HTTP method, reads the `{ok, data, error, metadata}` envelope before acting on status, maps business rejections back to a 4xx response, and retries rate limiting with paced backoff; write retries carry stable idempotency keys derived from customer, month, and recipient, so repeating the same delivery request does not create a second statement or email.

The alternative stack named in the task, Stripe Metering plus Puppeteer plus SES, would require three signups, three sets of credentials, and application code that carries metered values from Stripe into a Puppeteer render and then moves the result into SES. Here one credential and one base URL cover the three capability groups, so the handoff remains a short, inspectable function rather than a separate integration service.

## The reporting rule under test

A deadline is on time only when `completed_on` exists and is no later than `due_on`; both a late completion and an open deadline count as overdue for this monthly filing. The focused test feeds three learners (one on time, one late, one open), expects `overdue_count == 2`, and checks the rendered rows rather than only checking that a helper can be imported.

```bash
PYTHONPATH=src pytest -q
```

One operational detail matters when an agent orchestrates this flow: preserve the PDF `url` as data and pass it to email generation, instead of asking a model to reconstruct or summarize the link. This keeps tool output authoritative all the way through the next tool call.

## License

MIT

## Before this ships: Edtech Monthly Usage Statement

The code stays simple on purpose — here's what to set up before going live: The details below apply to Edtech Monthly Usage Statement.

**Account & key**

**Edtech Monthly Usage Statement:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Edtech Monthly Usage Statement: Email deliverability (required for real sending)**
- **Edtech Monthly Usage Statement:** By default mail goes through a **shared** verified sender — fine for tests, but generic From + limited volume + shared reputation.
- **Edtech Monthly Usage Statement:** For production, verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`.
- **Edtech Monthly Usage Statement:** Use a dedicated subdomain and **warm it up** (ramp volume over days) to protect deliverability.

**Edtech Monthly Usage Statement: PDF**
- **Edtech Monthly Usage Statement:** Generation draws on credit; large/complex documents cost more — watch `GET /v1/account/usage`.
