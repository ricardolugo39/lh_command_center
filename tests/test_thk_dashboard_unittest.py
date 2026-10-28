"""Focused regression tests for customer windows, filters and ERP classification."""
import importlib.util
import sqlite3
import sys
import types
import unittest
from datetime import date
from pathlib import Path

# Load the read model without booting unrelated integrations.
fake = types.ModuleType('app.database.connection')
fake.get_connection = lambda: None
old_connection_module = sys.modules.get('app.database.connection')
sys.modules['app.database.connection'] = fake
spec = importlib.util.spec_from_file_location('thk_dashboard_under_test', Path(__file__).parents[1] / 'app/workspace/services/thk_dashboard_service.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
if old_connection_module is None:
    del sys.modules['app.database.connection']
else:
    sys.modules['app.database.connection'] = old_connection_module

class DashboardTest(unittest.TestCase):
    def test_reference_parsing_and_ambiguous_codes(self):
        product = {'name':'RIEL LINEAL','ref':'SR 15+2000LYTHK','group_id':1550}
        self.assertEqual(module._product(product), ('rail','SR','15',2000))
        self.assertEqual(module._product({'name':'GUIA LINEAL','ref':'SSR 25 XW1SSTHK','group_id':1550})[:3], ('guide','SSR','25'))
        self.assertEqual(module._guide_variant({'ref':'HSR 25 CA1SSTHK'}), 'CA')
        self.assertEqual(module._product({'name':'GUIA LINEAL','ref':'BTK 4512VTHK','group_id':1560})[0], 'other')

    def test_customer_penetration_returns_and_recovery(self):
        today=date(2026,10,24)
        def row(customer, d, sales, group, component, qty=1, length=None):
            return {'customer':customer,'date':d,'sales':sales,'group_id':group,'component':component,'qty':qty,'length':length,'family':'HSR','size':'15','ref':'HSR 15-1000L','document':(customer,'FC',1),'customer_name':customer}
        rows=[row('A',date(2026,1,1),100,1550,'rail',1,1000),row('B',date(2025,1,1),50,1560,'other')]
        # D has THK sales but a negative overall total, and must not increase penetration.
        daily=[(date(2026,1,1),'A',100,100,100,0,0),(date(2025,1,1),'B',50,50,0,50,0),
               (date(2026,2,1),'B',10,0,0,0,5),(date(2026,3,1),'D',-10,20,20,0,0)]
        p=module.ThkDashboardService._build(rows,daily,lambda c,k:c,{'segment':[],'city':[],'advisor':[]},{'segment':'','city':'','advisor':''},date(2026,1,1),today,date(2025,1,1),date(2025,10,24),today,2026,'YTD')
        self.assertEqual((p['active'],p['buyers']), (2,1))
        self.assertEqual(p['penetration'],50)
        self.assertEqual([r['id'] for r in p['recover']],['B'])
        self.assertEqual([r['id'] for r in p['develop']],['B'])
        self.assertEqual(p['overlap'],1)
        self.assertEqual(p['meters'],1)
        self.assertEqual(p['screw_families'][0]['previous'],50)

    def test_same_size_opportunity_and_monthly_ratio(self):
        today=date(2026,10,24)
        def row(d, component, qty, length):
            return {'customer':'A','date':d,'sales':100,'group_id':1550,'component':component,'qty':qty,'length':length,'family':'HSR','size':'15','ref':'HSR 15','document':('A','FC',1),'customer_name':'Cliente A'}
        rows=[row(date(2025,3,1),'rail',2,1000), row(date(2026,3,1),'guide',6,None), row(date(2026,4,1),'rail',1,3000)]
        # No current HSR 15 rail in this test; a different-size rail must not suppress the lead.
        rows[2]['size']='25'
        p=module.ThkDashboardService._build(rows,[],lambda c,k:'ANA',{'segment':[],'city':[],'advisor':[]},{'segment':'','city':'','advisor':''},date(2026,1,1),today,date(2025,1,1),date(2025,10,24),today,2026,'YTD')
        self.assertEqual(p['paired_opportunities'][0]['product'],'HSR 15')
        self.assertEqual(p['paired_opportunities'][0]['current_guides'],6)
        self.assertIsNone(p['ratio_months'][0]['ratio'])
        self.assertEqual(p['ratio_months'][1]['meters'],3)

    def test_all_four_templates_render_with_empty_data(self):
        from jinja2 import Environment, DictLoader
        template = (Path(__file__).parents[1] / 'app/templates/workspace/thk_dashboard.html').read_text()
        env = Environment(loader=DictLoader({'workspace/thk_dashboard.html':template, 'base.html':'{% block styles %}{% endblock %}{% block content %}{% endblock %}{% block scripts %}{% endblock %}'}), autoescape=True)
        env.globals['url_for'] = lambda *args, **kwargs: '/dashboard'
        today=date(2026,10,24)
        page=module.ThkDashboardService._build([],[],lambda c,k:'Sin asignar',{'segment':[],'city':[],'advisor':[]},{'segment':'','city':'','advisor':''},date(2026,1,1),today,date(2025,1,1),date(2025,10,24),today,2026,'YTD')
        for focus in ('','customers','guides','screws'):
            output=env.get_template('workspace/thk_dashboard.html').render(page=page,focus=focus)
            self.assertIn('THK · Crecimiento comercial',output)
            self.assertIn('thk-data',output)

    def test_real_filter_applies_to_sales_and_denominator(self):
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
        db.executescript('''create table dim_customer(customer_id,customer_name,city,seller,classification_name);
          create table ws_customer_portfolio_metadata(erp_customer_id,advisor);
          create table raw_sales(fecha,nit,razonsocial,prefijo,numero,idproducto,nombreproducto,cantidad,neto,idfam2,sufijo);''')
        y=date.today().year; d=f'{y}-01-02'
        db.executemany('insert into dim_customer values(?,?,?,?,?)',[('1','Uno','CALI','ANA','PLASTICOS'),('2','Dos','BOGOTA','LUIS','OTRO')])
        db.executemany('insert into raw_sales values(?,?,?,?,?,?,?,?,?,?,?)',[(d,'1','Uno','FC',1,'HSR 15-1000L','RIEL LINEAL',1,100,1550,'THK'),(d,'2','Dos','FC',2,'HSR 15 C','GUIA LINEAL',2,200,1550,'THK')])
        module.get_connection=lambda:db
        p=module.ThkDashboardService.get_page({'segment':'PLASTICOS','year':str(y)})
        self.assertEqual((p['buyers'],p['active'],p['sales'],p['meters']), (1,1,100,1))
        self.assertEqual(p['guide_qty'],0)
        self.assertEqual(p['filters']['segment'],'PLASTICOS')

if __name__=='__main__':unittest.main()
