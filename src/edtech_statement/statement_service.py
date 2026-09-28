from __future__ import annotations

import os
from datetime import date

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .monthly_statement import (
    InfraiClient,
    InfraiError,
    LearnerDeadline,
    StatementFacts,
    deliver_statement,
)


class DeadlineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    learner_id: str = Field(min_length=1)
    due_on: date
    completed_on: date | None = None


class StatementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_name: str = Field(min_length=1)
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    course_deliveries: int = Field(ge=0)
    learner_deadlines: list[DeadlineRequest]
    recipient: EmailStr


class StatementResponse(BaseModel):
    message_id: str
    pdf_url: str
    overdue_count: int


app = FastAPI(title="Edtech monthly statement service")


@app.post("/statements/monthly", response_model=StatementResponse)
def create_monthly_statement(request: StatementRequest) -> dict[str, str | int]:
    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="INFRAI_API_KEY is not configured")

    facts = StatementFacts(
        customer_name=request.customer_name,
        period=request.period,
        course_deliveries=request.course_deliveries,
        learner_deadlines=tuple(
            LearnerDeadline(item.learner_id, item.due_on, item.completed_on)
            for item in request.learner_deadlines
        ),
    )
    try:
        return deliver_statement(InfraiClient(api_key), facts, str(request.recipient))
    except InfraiError as exc:
        client_status = exc.status if 400 <= exc.status < 500 else 502
        raise HTTPException(
            status_code=client_status, detail={"code": exc.code, "error": exc.detail}
        ) from exc
    except (KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

