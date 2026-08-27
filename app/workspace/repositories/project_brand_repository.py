from typing import Any

from app.database.transaction import connection_scope


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

        with connection_scope() as conn:
            cursor = conn.execute(
                sql,
                (
                    project_id,
                    clean_brand,
                ),
            )

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

        with connection_scope() as conn:
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

        with connection_scope() as conn:
            rows = conn.execute(
                sql,
                (project_id,),
            ).fetchall()

        return [dict(row) for row in rows]
