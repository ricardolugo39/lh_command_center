from typing import Any

from app.database.connection import get_connection


class ProjectBrandRepository:

    @staticmethod
    def add_brand(
        *,
        project_id: int,
        brand: str,
    ) -> int | None:
        clean_brand = brand.strip().upper()

        if not clean_brand:
            return None

        sql = """
        INSERT OR IGNORE INTO ws_project_brands (
            project_id,
            brand
        )
        VALUES (?, ?)
        """

        with get_connection() as conn:
            cursor = conn.execute(
                sql,
                (
                    project_id,
                    clean_brand,
                ),
            )
            conn.commit()

            if cursor.rowcount == 0:
                return None

            return int(cursor.lastrowid)

    @staticmethod
    def replace_project_brands(
        *,
        project_id: int,
        brands: list[str],
    ) -> None:
        clean_brands = sorted(
            {
                brand.strip().upper()
                for brand in brands
                if brand.strip()
            }
        )

        with get_connection() as conn:
            conn.execute(
                """
                DELETE FROM ws_project_brands
                WHERE project_id = ?
                """,
                (project_id,),
            )

            conn.executemany(
                """
                INSERT INTO ws_project_brands (
                    project_id,
                    brand
                )
                VALUES (?, ?)
                """,
                [
                    (
                        project_id,
                        brand,
                    )
                    for brand in clean_brands
                ],
            )

            conn.commit()

    @staticmethod
    def list_project_brands(
        project_id: int,
    ) -> list[dict[str, Any]]:
        sql = """
        SELECT
            id,
            project_id,
            brand,
            created_at
        FROM ws_project_brands
        WHERE project_id = ?
        ORDER BY brand
        """

        with get_connection() as conn:
            rows = conn.execute(
                sql,
                (project_id,),
            ).fetchall()

        return [dict(row) for row in rows]