import sqlite3
from datetime import date, timedelta

import pytest
from flask import Flask

from app.database.migrations import upgrade
from app.routes import register_blueprints
from app.workspace.connectors.visit_source import VisitSourceAdapter
from app.workspace.repositories.commercial_visit_repository import CommercialVisitRepository
from app.workspace.services.commercial_visit_service import CommercialVisitService
from app.workspace.services.visit_normalizer import VisitNormalizer


class FakeVisitSource(VisitSourceAdapter):
    def __init__(self, rows):self.rows=rows
    def read_rows(self):return self.rows


@pytest.fixture
def visit_database(tmp_path,monkeypatch):
    path=tmp_path/"visits.db"
    monkeypatch.setattr("app.database.connection.DB_PATH",path)
    upgrade()
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO ws_customers(id,name,erp_customer_id) VALUES (1,'Papeles Nacionales','900123')")
        connection.execute("INSERT INTO ws_projects(id,customer_id,name,status,objective) VALUES (1,1,'Homologación','prospect','Validar')")
    return path


def _row(identifier="v-1",**changes):
    row={"ID_Visita":identifier,"Fecha_Registro":"07/20/2026 10:30",
         "Fecha_Visita":"07/19/2026","Asesor":"Jairo Vera","Cliente":"900.123",
         "Cliente_Nombre":"Papeles Nacionales","Contacto_Visitado":"Iván Cardona",
         "Cargo_Contacto":"Compras","Tipo_Visita":"Técnica",
         "Motivo_Visita":"Revisar homologación","Resumen_Ejecutivo":"Visita productiva",
         "Necesidad_Detectada":"Homologar guías","Riesgo_Detectado":"Competencia",
         "Competencia_Presente":"Marca X","Comentarios_Clave":"Enviar ficha",
         "Requiere_Accion":"TRUE","Accion_Requerida":"Realizar seguimiento",
         "Responsable_Seguimiento_nombre":"Jairo Vera","Fecha_Compromiso":"07/25/2026",
         "Generar_Oportunidad_CRM":"TRUE","Estado":"En seguimiento",
         "Adjuntos":"Visitas_Images/e2cb15.jpg"}
    row.update(changes);return row


def _visits(path):
    with sqlite3.connect(path) as connection:
        connection.row_factory=sqlite3.Row
        return [dict(row) for row in connection.execute("SELECT * FROM ws_commercial_visits ORDER BY id")]


def test_import_valid_visit_matches_erp_and_preserves_source(visit_database):
    result=CommercialVisitService.sync(FakeVisitSource([_row()]))
    visit=_visits(visit_database)[0]
    assert result["inserted"]==1
    assert visit["customer_id"]==1 and visit["customer_match_status"]=="matched"
    assert visit["visit_type"]=="Técnica" and visit["visit_status"]=="En seguimiento"
    assert visit["source_created_at"].startswith("2026-07-20")
    assert visit["visit_date"]=="2026-07-19"
    assert visit["generate_opportunity_requested"]==1
    assert visit["attachment_reference"]=="Visitas_Images/e2cb15.jpg"
    assert visit["advisor_name"] == "JAIRO DAVID VERA"
    assert visit["follow_up_owner_name"] == "JAIRO DAVID VERA"


@pytest.mark.parametrize(("alias", "canonical"), [
    ("Andrea Jimenez", "NUBIA ANDREA JIMENEZ"),
    ("Fabio Valencia", "FABIO NELSON VALENCIA"),
    ("Jairo Vera", "JAIRO DAVID VERA"),
    ("Jeisman Holguin", "JEISMAN HOLGUIN"),
    ("Jose Beltran", "JOSE TRINIDAD BELTRAN CARVAJAL"),
    ("Yeisson Renteria", "YEISSON ANDRES RENTERIA MOSQUERA"),
])
def test_visit_advisor_aliases_are_canonical(alias, canonical):
    normalized = VisitNormalizer.normalize(_row(Asesor=alias))
    assert normalized["advisor_name"] == canonical


def test_reimport_is_unchanged_and_followup_is_idempotent(visit_database):
    source=FakeVisitSource([_row()])
    CommercialVisitService.sync(source)
    result=CommercialVisitService.sync(source)
    assert result["unchanged"]==1 and len(_visits(visit_database))==1
    with sqlite3.connect(visit_database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM ws_visit_followups").fetchone()[0]==1


def test_repeated_commitment_for_same_customer_updates_open_item(visit_database):
    CommercialVisitService.sync(FakeVisitSource([
        _row("first"),
        _row("second", Fecha_Compromiso="07/30/2026"),
    ]))
    with sqlite3.connect(visit_database) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("SELECT * FROM ws_visit_followups").fetchall()
    assert len(rows) == 1
    assert rows[0]["external_key"] == "appsheet_visit:second:follow_up"
    assert rows[0]["due_date"] == "2026-07-30"


def test_source_without_action_closes_existing_commitment(visit_database):
    CommercialVisitService.sync(FakeVisitSource([_row()]))
    CommercialVisitService.sync(FakeVisitSource([_row(Requiere_Accion="FALSE")]))
    with sqlite3.connect(visit_database) as connection:
        status = connection.execute(
            "SELECT status FROM ws_visit_followups"
        ).fetchone()[0]
    assert status == "completed"


def test_manual_completion_is_not_reopened_by_sync(visit_database):
    CommercialVisitService.sync(FakeVisitSource([_row()]))
    CommercialVisitRepository.complete_followup(1)
    CommercialVisitService.sync(FakeVisitSource([_row(Comentarios_Clave="Actualizado")]))
    with sqlite3.connect(visit_database) as connection:
        status = connection.execute(
            "SELECT status FROM ws_visit_followups"
        ).fetchone()[0]
    assert status == "completed"


def test_changed_source_updates_same_visit(visit_database):
    CommercialVisitService.sync(FakeVisitSource([_row()]))
    result=CommercialVisitService.sync(FakeVisitSource([_row(Resumen_Ejecutivo="Actualizado")]))
    assert result["updated"]==1
    assert _visits(visit_database)[0]["executive_summary"]=="Actualizado"


def test_unmatched_and_ambiguous_customers_are_retained(visit_database):
    unmatched=CommercialVisitService.sync(FakeVisitSource([_row("u",Cliente="777")]))
    with sqlite3.connect(visit_database) as connection:
        connection.execute("INSERT INTO ws_customers(id,name,erp_customer_id) VALUES (2,'A','90-01')")
        connection.execute("INSERT INTO ws_customers(id,name,erp_customer_id) VALUES (3,'B','9001')")
    ambiguous=CommercialVisitService.sync(FakeVisitSource([_row("a",Cliente="90.01")]))
    visits=_visits(visit_database)
    assert unmatched["unmatched"]==1 and visits[0]["customer_match_status"]=="unmatched"
    assert ambiguous["unmatched"]==1 and visits[1]["customer_match_status"]=="ambiguous"


def test_possible_business_duplicate_is_flagged_not_merged(visit_database):
    result=CommercialVisitService.sync(FakeVisitSource([_row("58756fa5"),_row("58756fa6")]))
    assert result["inserted"]==2 and result["possible_duplicates"]==1
    assert len(_visits(visit_database))==2
    assert _visits(visit_database)[1]["possible_duplicate"]==1


def test_future_unknown_type_and_status_create_quality_warnings(visit_database):
    future=(date.today()+timedelta(days=5)).strftime("%m/%d/%Y")
    CommercialVisitService.sync(FakeVisitSource([_row(
        Fecha_Visita=future,Tipo_Visita="Exploratoria",Estado="Pendiente raro")]))
    page=CommercialVisitService.get_customer_page(1)
    visit=page["visits"][0]
    assert visit["visit_type"]=="Otro" and visit["visit_status"]=="Sin estado"
    assert visit["is_scheduled"] is True
    assert any("desconocido" in warning for warning in visit["quality_warnings"])


def test_bad_row_does_not_block_other_rows_and_sync_history_is_saved(visit_database):
    result=CommercialVisitService.sync(FakeVisitSource([{},_row()]))
    assert result["rows_read"]==2 and result["inserted"]==1 and result["errors"]==1
    latest=CommercialVisitRepository.latest_sync_run()
    assert latest["inserted_count"]==1 and latest["error_count"]==1


def test_linked_visit_publishes_once_to_opportunity_timeline(visit_database):
    CommercialVisitService.sync(FakeVisitSource([_row()]))
    CommercialVisitService.link_to_project(1,1)
    CommercialVisitService.link_to_project(1,1)
    with sqlite3.connect(visit_database) as connection:
        rows=connection.execute("SELECT * FROM ws_activities").fetchall()
    assert len(rows)==1
    assert "[visita:1]" in rows[0][4]
    assert rows[0][6].startswith("2026-07-19")


def test_critical_persistence_failure_rolls_back_all_rows(visit_database,monkeypatch):
    original=CommercialVisitRepository.insert
    calls={"count":0}
    def fail_second(source_system,values):
        calls["count"]+=1
        if calls["count"]==2:raise RuntimeError("database failure")
        return original(source_system,values)
    monkeypatch.setattr(CommercialVisitRepository,"insert",fail_second)
    with pytest.raises(RuntimeError,match="database failure"):
        CommercialVisitService.sync(FakeVisitSource([_row("1"),_row("2")]))
    assert _visits(visit_database)==[]


def test_attachment_is_present_but_not_exposed_as_broken_link(visit_database):
    CommercialVisitService.sync(FakeVisitSource([_row()]))
    attachment=CommercialVisitService.get_customer_page(1)["visits"][0]["attachment"]
    assert attachment=={"has_attachment":True,"is_resolved":False,"url":None,
                        "label":"Adjunto disponible en AppSheet"}


def test_customer_activity_and_quality_pages_render_in_spanish(visit_database):
    CommercialVisitService.sync(FakeVisitSource([_row()]))
    application=Flask(__name__,template_folder="../app/templates",
                      static_folder="../app/static")
    register_blueprints(application); client=application.test_client()
    activities=client.get("/workspace/strategic-accounts/1/activities")
    quality=client.get("/workspace/integrations/google/visits/quality")
    integration=client.get("/workspace/integrations/google/visits")
    assert activities.status_code==200 and b"Visita t\xc3\xa9cnica" in activities.data
    assert b"Adjunto disponible en AppSheet" in activities.data
    assert quality.status_code==200 and b"Calidad de datos" in quality.data
    assert integration.status_code==200 and b"Sincronizar ahora" in integration.data


@pytest.mark.parametrize(("status", "expected"), [
    (None, "Sin estado"),
    ("", "Sin estado"),
    ("Abierto", "Abierto"),
    ("En seguimiento", "En seguimiento"),
    ("Cerrado", "Cerrado"),
])
def test_visit_status_normalization_is_defensive(status,expected):
    normalized=VisitNormalizer.normalize(_row(Estado=status))
    assert normalized["visit_status"]==expected
    assert normalized["source_visit_status"]==(status or None)


def test_missing_status_column_defaults_to_without_status():
    row=_row(); row.pop("Estado")
    normalized=VisitNormalizer.normalize(row)
    assert normalized["visit_status"]=="Sin estado"
    assert normalized["source_visit_status"] is None


def test_all_optional_cells_accept_none_and_sync_continues(visit_database):
    row={key:None for key in _row()}
    row["ID_Visita"]="blank-cells"
    result=CommercialVisitService.sync(FakeVisitSource([row]))
    visit=_visits(visit_database)[0]
    assert result["inserted"]==1 and result["errors"]==0
    assert visit["visit_status"]=="Sin estado"
    assert visit["visit_type"]=="Otro"


@pytest.mark.parametrize(("google_value", "expected"), [
    ("7/10/2026", "2026-07-10"),
    ("5/12/2026", "2026-05-12"),
    ("6/25/2026", "2026-06-25"),
])
def test_google_dates_use_explicit_month_day_year_contract(google_value,expected):
    normalized=VisitNormalizer.normalize(_row(
        Fecha_Registro=google_value,Fecha_Visita=google_value,
        Fecha_Compromiso=google_value))
    assert normalized["source_created_at"]==f"{expected}T00:00:00"
    assert normalized["visit_date"]==expected
    assert normalized["commitment_date"]==expected


@pytest.mark.parametrize("field", ["Fecha_Registro","Fecha_Visita"])
def test_invalid_google_date_format_has_clear_validation_error(field):
    with pytest.raises(ValueError,match=rf"{field} debe usar el formato MM/DD/YYYY"):
        VisitNormalizer.normalize(_row(**{field:"2026-07-10"}))


def test_rebuild_reimports_dates_in_order_and_preserves_other_activities(visit_database):
    CommercialVisitService.sync(FakeVisitSource([
        _row("older",Fecha_Visita="7/2/2026"),
        _row("newer",Fecha_Visita="7/10/2026",Adjuntos="otro.jpg"),
    ]))
    CommercialVisitService.link_to_project(1,1)
    with sqlite3.connect(visit_database) as connection:
        connection.execute("""INSERT INTO ws_activities(
            project_id,activity_type,title,details) VALUES (1,'note','Nota preservada','Otra fuente')""")
    result=CommercialVisitService._rebuild_rows([
        _row("older",Fecha_Visita="7/2/2026"),
        _row("newer",Fecha_Visita="7/10/2026",Adjuntos="otro.jpg"),
    ])
    assert result["removed"]==2 and result["inserted"]==2
    page=CommercialVisitService.get_customer_page(1)
    assert [visit["visit_date"] for visit in page["visits"]]==[
        "2026-07-10","2026-07-02"]
    with sqlite3.connect(visit_database) as connection:
        titles=[row[0] for row in connection.execute(
            "SELECT title FROM ws_activities ORDER BY id")]
    assert "Nota preservada" in titles
    assert titles.count("Visita técnica")==1
