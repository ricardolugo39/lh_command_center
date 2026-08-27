from typing import Any

from app.database.transaction import connection_scope


class AdvisorReviewRepository:
    @staticmethod
    def create(*, advisor_name: str, scheduled_at: str, period_start: str | None,
               period_end: str | None, created_by: str) -> int:
        with connection_scope() as conn:
            cursor = conn.execute(
                """INSERT INTO ws_advisor_reviews(
                    advisor_name,scheduled_at,period_start,period_end,created_by
                ) VALUES (?,?,?,?,?)""",
                (advisor_name, scheduled_at, period_start, period_end, created_by),
            )
        return int(cursor.lastrowid)

    @staticmethod
    def list_advisor(advisor_name: str) -> list[dict[str, Any]]:
        with connection_scope() as conn:
            rows = conn.execute(
                """SELECT * FROM ws_advisor_reviews
                WHERE LOWER(TRIM(advisor_name))=LOWER(TRIM(?))
                ORDER BY status='scheduled' DESC,scheduled_at DESC""",
                (advisor_name,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def complete(review_id: int, notes: str) -> None:
        with connection_scope() as conn:
            cursor = conn.execute(
                """UPDATE ws_advisor_reviews SET status='completed',notes=?,
                    completed_at=CURRENT_TIMESTAMP WHERE id=? AND status='scheduled'""",
                (notes.strip(), review_id),
            )
            if cursor.rowcount == 0:
                raise ValueError("La revisión no existe o ya fue cerrada.")
