
from pathlib import Path

from typing import Any

from bs4 import BeautifulSoup

class AgreementHtmlParser:

    EXPECTED_HEADERS = [

        "NUMERO PARTE",

        "REFERENCIA SKF",

        "FOB DD LISTA",

        "FOB DD CONVENIO",

        "PRECIO SUGERIDO",

        "PRODUCT LINE",

        "SPC",

    ]

    @staticmethod

    def parse(

        file_path: str | Path,

    ) -> dict[str, Any]:

        path = Path(file_path)

        if not path.exists():

            raise ValueError(

                f"El archivo no existe: {path}"

            )

        html = path.read_text(

            encoding="latin1",

            errors="replace",

        )

        soup = BeautifulSoup(

            html,

            "html.parser",

        )

        tables = soup.find_all("table")

        if len(tables) < 2:

            raise ValueError(

                "El archivo no contiene las tablas esperadas."

            )

        metadata = (

            AgreementHtmlParser._parse_metadata(

                tables[0]

            )

        )

        product_table = (

            AgreementHtmlParser._find_product_table(

                tables

            )

        )

        items, duplicate_count = (

            AgreementHtmlParser._parse_items(

                product_table,

                source_file_name=path.name,

            )

        )

        if not items:

            raise ValueError(

                "No se encontraron productos en el archivo."

            )

        return {

            "metadata": metadata,

            "items": items,

            "stats": {

                "rows_read": (

                    len(items) + duplicate_count

                ),

                "unique_items": len(items),

                "duplicates": duplicate_count,

            },

        }

    @staticmethod

    def _parse_metadata(

        table,

    ) -> dict[str, Any]:

        raw_metadata = {}

        for row in table.find_all("tr"):

            cells = row.find_all(

                ["th", "td"]

            )

            if len(cells) < 2:

                continue

            key = cells[0].get_text(

                " ",

                strip=True,

            )

            value = cells[1].get_text(

                " ",

                strip=True,

            )

            raw_metadata[key] = value

        return {

            "pricing_type": raw_metadata.get(

                "Tipo"

            ),

            "customer_name": raw_metadata.get(

                "Cliente"

            ),

            "start_date": raw_metadata.get(

                "Fecha Inicio"

            ),

            "end_date": raw_metadata.get(

                "Fecha Fin"

            ),

        }

    @staticmethod

    def _find_product_table(

        tables,

    ):

        for table in tables:

            headers = [

                header.get_text(

                    " ",

                    strip=True,

                ).upper()

                for header in table.find_all("th")

            ]

            if all(

                expected in headers

                for expected

                in AgreementHtmlParser.EXPECTED_HEADERS

            ):

                return table

        raise ValueError(

            "No se encontró la tabla de productos SKF."

        )

    @staticmethod

    def _parse_items(

        table,

        *,

        source_file_name: str,

    ) -> tuple[list[dict[str, Any]], int]:

        items_by_key = {}

        duplicate_count = 0

        for row_number, row in enumerate(

            table.find_all("tr"),

            start=1,

        ):

            cells = [

                cell.get_text(

                    " ",

                    strip=True,

                )

                for cell in row.find_all(

                    ["td", "th"]

                )

            ]

            # El encabezado del archivo no está dentro

            # de un <tr>, r lo que cada fila válida

            # debe contener exactamente siete columnas.

            if len(cells) != 7:

                continue

            (

                part_number,

                skf_reference,

                list_price,

                agreement_price,

                suggested_price,

                product_line,

                spc,

            ) = cells

            if (

                not part_number

                or not skf_reference

            ):

                continue

            item = {

                "part_number": part_number,

                "skf_reference": skf_reference,

                "list_price_usd": (

                    AgreementHtmlParser

                    ._parse_decimal(

                        list_price,

                        row_number=row_number,

                        field_name="FOB DD LISTA",

                    )

                ),

                "agreement_price_usd": (

                    AgreementHtmlParser

                   ._parse_decimal(

                        agreement_price,

                        row_number=row_number,

                        field_name="FOB DD CONVENIO",

                    )

                ),

                "suggested_price_usd": (

                    AgreementHtmlParser

                    ._parse_decimal(

                        suggested_price,

                        row_number=row_number,

                        field_name="PRECIO SUGERIDO",

                    )

                ),

                "product_line": (

                    product_line or None

                ),

                "spc": spc or None,

                "source_file_name": (

                    source_file_name

                ),

            }

            key = (

                part_number,

                skf_reference,

            )

            if key in items_by_key:

                duplicate_count += 1

            # Conserva la última aparición.

            items_by_key[key] = item

        return (

            list(items_by_key.values()),

            duplicate_count,

        )

    @staticmethod

    def _parse_decimal(

        value: str,

        *,

        row_number: int,

        field_name: str,

    ) -> float | None:

        clean_value = (

            value.strip()

            .replace("\xa0", "")

            .replace(" ", "")

        )

        if not clean_value:

            return None

        # Formatos soportados:

        # 354,98

        # 354, 98

        # 1.017,48

        # 1017.48

        if (

            "," in clean_value

            and "." in clean_value

        ):

            clean_value = (

                clean_value

                .replace(".", "")

                .replace(",", ".")

            )

        elif "," in clean_value:

            clean_value = (

                clean_value.replace(",", ".")

            )

        try:

            return float(clean_value)

        except ValueError as exc:

            raise ValueError(

                f"Precio inválido en fila "

                f"{row_number}, campo "

                f"{field_name}: {value}"

            ) from exc

