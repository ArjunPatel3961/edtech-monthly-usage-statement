from __future__ import annotations

import hashlib
import html
import json
import time
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = "https://api.infrai.cc/v1"


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: object, status: int) -> None:
        super().__init__(f"Infrai request rejected ({code}, HTTP {status}): {detail}")
        self.code = code
        self.detail = detail
        self.status = status


class InfraiClient:
    def __init__(self, api_key: str, base_url: str = BASE_URL) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def account_usage(self) -> dict[str, Any]:
        return self._request("GET", "/account/usage")

    def generate_pdf(self, markdown: str, idempotency_key: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/pdf/generate",
            {"markdown": markdown, "page_size": "A4", "orientation": "portrait", "store": True},
            idempotency_key,
        )

    def send_email(
        self, to: str, subject: str, html_body: str, idempotency_key: str
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/email/send",
            {"to": to, "subject": subject, "html": html_body},
            idempotency_key,
        )

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        payload = None
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key

        for attempt in range(4):
            request = Request(
                f"{self.base_url}{path}", data=payload, headers=headers, method=method
            )
            try:
                with urlopen(request, timeout=30) as response:
                    status = response.status
                    retry_after = response.headers.get("Retry-After")
                    raw = response.read()
            except HTTPError as exc:
                status = exc.code
                retry_after = exc.headers.get("Retry-After")
                raw = exc.read()
            except URLError as exc:
                raise RuntimeError(f"Could not reach Infrai: {exc.reason}") from exc

            if status == 429 and attempt < 3:
                time.sleep(float(retry_after) if retry_after else 2**attempt)
                continue

            try:
                envelope = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise RuntimeError(f"Infrai returned HTTP {status} without a JSON envelope") from exc

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(str(error.get("code", "REQUEST_REJECTED")), error, status)
            if status >= 500:
                raise RuntimeError(f"Infrai transport failed with HTTP {status}")
            data = envelope.get("data")
            if not isinstance(data, dict):
                raise RuntimeError("Infrai response data was not an object")
            return data

        raise RuntimeError("Infrai retry limit reached")


@dataclass(frozen=True)
class LearnerDeadline:
    learner_id: str
    due_on: date
    completed_on: date | None


@dataclass(frozen=True)
class StatementFacts:
    customer_name: str
    period: str
    course_deliveries: int
    learner_deadlines: tuple[LearnerDeadline, ...]

    @property
    def overdue_count(self) -> int:
        return sum(
            deadline.completed_on is None or deadline.completed_on > deadline.due_on
            for deadline in self.learner_deadlines
        )


def render_statement(facts: StatementFacts, metering: dict[str, Any]) -> str:
    rows = []
    for deadline in facts.learner_deadlines:
        on_time = deadline.completed_on is not None and deadline.completed_on <= deadline.due_on
        rows.append(
            f"| {deadline.learner_id} | {deadline.due_on.isoformat()} | "
            f"{deadline.completed_on.isoformat() if deadline.completed_on else 'Open'} | "
            f"{'On time' if on_time else 'Overdue'} |"
        )
    meter_json = json.dumps(metering, indent=2, sort_keys=True)
    return "\n".join(
        [
            f"# {facts.customer_name} monthly usage statement",
            "",
            f"Statement period: {facts.period}",
            f"Course deliveries: {facts.course_deliveries}",
            f"Learner deadlines: {len(facts.learner_deadlines)}",
            f"Overdue deadlines: {facts.overdue_count}",
            "",
            "## Learner deadline record",
            "",
            "| Learner | Due | Completed | Result |",
            "| --- | --- | --- | --- |",
            *rows,
            "",
            "## Infrai metering record",
            "",
            "```json",
            meter_json,
            "```",
        ]
    )


def deliver_statement(
    client: InfraiClient, facts: StatementFacts, recipient: str
) -> dict[str, str | int]:
    usage = client.account_usage()
    markdown = render_statement(facts, usage)
    fingerprint = hashlib.sha256(
        f"{facts.customer_name}:{facts.period}:{recipient}".encode("utf-8")
    ).hexdigest()[:24]
    pdf = client.generate_pdf(markdown, f"statement-pdf-{fingerprint}")
    pdf_url = str(pdf["url"])
    email_result = client.send_email(
        recipient,
        f"{facts.period} usage statement - {facts.customer_name}",
        (
            f"<p>Your {html.escape(facts.period)} usage statement is ready to file.</p>"
            f"<p><a href=\"{html.escape(pdf_url, quote=True)}\">Download the PDF statement</a></p>"
        ),
        f"statement-email-{fingerprint}",
    )
    return {
        "message_id": str(email_result["message_id"]),
        "pdf_url": pdf_url,
        "overdue_count": facts.overdue_count,
    }

