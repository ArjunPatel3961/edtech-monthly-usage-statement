from datetime import date

from edtech_statement.monthly_statement import LearnerDeadline, StatementFacts, render_statement


def test_statement_marks_open_and_late_completions_overdue() -> None:
    facts = StatementFacts(
        customer_name="Cedar Academy",
        period="2026-08",
        course_deliveries=42,
        learner_deadlines=(
            LearnerDeadline("learner-101", date(2026, 8, 10), date(2026, 8, 9)),
            LearnerDeadline("learner-102", date(2026, 8, 12), date(2026, 8, 14)),
            LearnerDeadline("learner-103", date(2026, 8, 15), None),
        ),
    )

    statement = render_statement(facts, {"period": "2026-08", "requests": 17})

    assert facts.overdue_count == 2
    assert "Course deliveries: 42" in statement
    assert "| learner-101 | 2026-08-10 | 2026-08-09 | On time |" in statement
    assert "| learner-102 | 2026-08-12 | 2026-08-14 | Overdue |" in statement
    assert "| learner-103 | 2026-08-15 | Open | Overdue |" in statement
