"""THK customer penetration and product diagnostics, based on ERP transactions."""
from collections import defaultdict
from datetime import date, timedelta
import calendar
import re
import time
from functools import lru_cache

from app.database.connection import get_connection


def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _customer(value):
    return str(value or '').replace(',', '').strip()


def _year_before(day):
    try:
        return day.replace(year=day.year - 1)
    except ValueError:
        return day.replace(year=day.year - 1, day=28)


def _product(row):
    name = (row['name'] or '').upper()
    ref = (row['ref'] or '').upper().strip()
    group = int(row['group_id'] or 0)
    if 'GUIA' in name and 'RIEL' in name:
        component = 'set'
    elif group == 1550 and name.startswith('RIEL LINEAL'):
        component = 'rail'
    elif group == 1550 and name.startswith('GUIA LINEAL'):
        component = 'guide'
    elif 'TORNILLO' in name and 'TUERCA' in name:
        component = 'screw_set'
    elif group == 1560 and 'TUERCA' in name and 'BOLAS' in name:
        component = 'nut'
    elif group == 1560 and 'TORNILLO DE BOLAS' in name and 'SOPORTE' not in name:
        component = 'screw'
    else:
        component = 'other'
    match = re.match(r'^\s*([A-Z]+)\s*(\d+)', ref)
    family = match.group(1) if match else 'Sin clasificar'
    size = match.group(2) if match else 'Sin clasificar'
    length_match = re.search(r'[- +](\d{3,4})L', ref)
    length = int(length_match.group(1)) if component == 'rail' and length_match else None
    return component, family, size, length


def _guide_variant(row):
    ref = row['ref'].upper().strip()
    match = re.match(r'^\s*[A-Z]+\s*\d+\s*[- ]?\s*(XW|XV|LR|LC|LV|CA|HA|LA|C|R|V)', ref)
    return match.group(1) if match else 'Sin clasificar'


def _change(current, previous):
    return (current / previous - 1) * 100 if previous > 0 else None


def _sum(rows, key='sales'):
    return sum(_number(r.get(key)) for r in rows)


class ThkDashboardService:
    @classmethod
    def get_page(cls, args):
        keys = ('year', 'period', 'segment', 'city', 'advisor')
        values = tuple((key, str(args.get(key, ''))) for key in keys)
        return cls._cached_page(values, int(time.time() // 60))

    @staticmethod
    @lru_cache(maxsize=16)
    def _cached_page(values, _minute):
        return ThkDashboardService._calculate(dict(values))

    @classmethod
    def _calculate(cls, args):
        with get_connection() as conn:
            latest = conn.execute("SELECT MAX(date(fecha)) FROM raw_sales WHERE date(fecha)<=date('now')").fetchone()[0]
            latest_day = date.fromisoformat(latest) if latest else date.today()
            try:
                year = int(args.get('year', latest_day.year))
            except (ValueError, TypeError):
                year = latest_day.year
            year = year if 2023 <= year <= latest_day.year else latest_day.year
            period = args.get('period', 'YTD')
            if period not in ('YTD', 'Q1', 'Q2', 'Q3', 'Q4'):
                period = 'YTD'
            if period == 'YTD':
                end = min(latest_day, date(year, latest_day.month, min(latest_day.day, calendar.monthrange(year, latest_day.month)[1])))
                start = date(year, 1, 1)
            else:
                q = int(period[1]); month = q * 3
                end = min(latest_day, date(year, month, calendar.monthrange(year, month)[1]))
                start = date(year, month - 2, 1)
            if end < start:
                period, start, end = 'YTD', date(latest_day.year, 1, 1), latest_day
                year = latest_day.year
            prev_start, prev_end = _year_before(start), _year_before(end)
            dimension_rows = conn.execute("""SELECT TRIM(customer_id) customer_id,customer_name,city,seller,classification_name FROM dim_customer""").fetchall()
            metadata = conn.execute("SELECT erp_customer_id,advisor FROM ws_customer_portfolio_metadata").fetchall()
            dims = defaultdict(lambda: defaultdict(set))
            for r in dimension_rows:
                customer = _customer(r['customer_id'])
                for key, column in [('name','customer_name'), ('city','city'), ('segment','classification_name'), ('advisor','seller')]:
                    val = str(r[column] or '').strip()
                    if val: dims[customer][key].add(val)
            advisers = defaultdict(set)
            for r in metadata:
                if r['advisor'] and r['advisor'].strip():
                    advisers[_customer(r['erp_customer_id'])].add(r['advisor'].strip())
            def dimension(customer, key):
                values = advisers[customer] if key == 'advisor' and advisers[customer] else dims[customer][key]
                return next(iter(values)) if len(values) == 1 else ('Sin asignar' if not values else 'Múltiples')
            options = {key: sorted({dimension(c, key) for c in dims}) for key in ('segment', 'city', 'advisor')}
            filters = {key: args.get(key, '').strip() for key in options}
            for key in filters:
                if filters[key] not in options[key]: filters[key] = ''
            def include(customer):
                return all(not value or dimension(customer, key) == value for key, value in filters.items())
            # The product detail covers the prior three years plus the selected year.
            product_rows = []
            for r in conn.execute("""SELECT fecha,nit,razonsocial,prefijo,numero,idproducto,nombreproducto,cantidad,neto,idfam2
                    FROM raw_sales WHERE UPPER(TRIM(sufijo))='THK'
                    AND CAST(idfam2 AS INTEGER) IN (1550,1560)
                    AND date(fecha)>=? AND date(fecha)<=?""", (f'{max(2023,year-3)}-01-01', end.isoformat())):
                customer = _customer(r['nit'])
                if not customer or not include(customer): continue
                item = {'date': date.fromisoformat(str(r['fecha'])[:10]), 'customer': customer,
                        'customer_name': r['razonsocial'], 'document': (customer,r['prefijo'],r['numero']),
                        'ref': r['idproducto'] or '', 'name': r['nombreproducto'] or '',
                        'qty': _number(r['cantidad']), 'sales': _number(r['neto']), 'group_id': r['idfam2']}
                item['component'], item['family'], item['size'], item['length'] = _product(item)
                product_rows.append(item)
            # Daily customer aggregates permit exact rolling windows and comparable quarter snapshots.
            first = date(max(2023, year-3),1,1)
            daily = []
            sql = """SELECT date(fecha) d,REPLACE(TRIM(nit),',','') customer,
                     SUM(COALESCE(neto,0)) total,
                     SUM(CASE WHEN UPPER(TRIM(sufijo))='THK' AND CAST(idfam2 AS INTEGER) IN (1550,1560) THEN COALESCE(neto,0) ELSE 0 END) thk,
                     SUM(CASE WHEN UPPER(TRIM(sufijo))='THK' AND CAST(idfam2 AS INTEGER)=1550 THEN COALESCE(neto,0) ELSE 0 END) guides,
                     SUM(CASE WHEN UPPER(TRIM(sufijo))='THK' AND CAST(idfam2 AS INTEGER)=1560 THEN COALESCE(neto,0) ELSE 0 END) screws,
                     SUM(CASE WHEN CAST(idfam2 AS INTEGER) IN (1510,1550,1560) AND UPPER(TRIM(COALESCE(sufijo,''))) NOT IN ('THK','THO','THOMSON') THEN COALESCE(neto,0) ELSE 0 END) competition
                     FROM raw_sales WHERE date(fecha)>=? AND date(fecha)<=? AND TRIM(COALESCE(nit,''))<>'' GROUP BY date(fecha),REPLACE(TRIM(nit),',','')"""
            for r in conn.execute(sql, (first.isoformat(), end.isoformat())):
                customer = _customer(r['customer'])
                if customer and include(customer):
                    daily.append((date.fromisoformat(r['d']), customer, *[_number(r[k]) for k in ('total','thk','guides','screws','competition')]))
        return cls._build(product_rows, daily, dimensions=dimension, options=options, filters=filters,
                          start=start, end=end, prev_start=prev_start, prev_end=prev_end,
                          latest=latest_day, year=year, period=period)

    @classmethod
    def _build(cls, rows, daily, dimensions, options, filters, start, end, prev_start, prev_end, latest, year, period):
        def window(stop):
            begin = _year_before(stop)
            customers = defaultdict(lambda: [0.0]*5)
            for day, customer, *values in daily:
                if begin < day <= stop:
                    for i, value in enumerate(values): customers[customer][i] += value
            return customers
        now, old = window(end), window(_year_before(end))
        active = {k for k,v in now.items() if v[0] > 0}
        buyers = {k for k,v in now.items() if v[1] > 0 and v[0] > 0}
        old_buyers = {k for k,v in old.items() if v[1] > 0 and v[0] > 0}
        recover = (old_buyers - buyers) & active
        develop = {k for k in active-buyers if now[k][4] > 0}
        def customer_list(ids, kind):
            result = []
            names = {r['customer']: r['customer_name'] for r in rows if r['customer_name']}
            for c in ids:
                result.append({'id': c, 'name': names.get(c) or dimensions(c,'name'), 'advisor': dimensions(c,'advisor'),
                               'city': dimensions(c,'city'), 'segment': dimensions(c,'segment'),
                               'current': now.get(c,[0]*5)[0], 'previous': old.get(c,[0]*5)[1],
                               'other_linear': now.get(c,[0]*5)[4], 'pool': kind})
            return sorted(result,key=lambda r: r['previous'] if kind=='Recuperar' else r['other_linear'],reverse=True)
        current = [r for r in rows if start <= r['date'] <= end]
        previous = [r for r in rows if prev_start <= r['date'] <= prev_end]
        def aggregate(group, component, key):
            result = defaultdict(lambda: [0.0,0.0,0.0,0.0])
            for period_index, selection in enumerate((previous,current)):
                for r in selection:
                    if component and r['component'] not in component: continue
                    expected_group = 1560 if group in ('screw', 'size') else 1550
                    if int(r['group_id'] or 0) != expected_group: continue
                    label = key(r)
                    result[label][period_index] += r['sales']
                    result[label][period_index+2] += r['qty']
            return [{'name':k, 'previous':v[0], 'current':v[1], 'previous_qty':v[2], 'current_qty':v[3],
                     'change':_change(v[1],v[0])} for k,v in sorted(result.items(),key=lambda x: (-x[1][1],str(x[0])))]
        rails = [r for r in current if r['component']=='rail']
        old_rails = [r for r in previous if r['component']=='rail']
        guide_qty = _sum([r for r in current if r['component']=='guide'],'qty')
        old_guide_qty = _sum([r for r in previous if r['component']=='guide'],'qty')
        meters = sum(r['qty'] * r['length']/1000 for r in rails if r['length'])
        old_meters = sum(r['qty'] * r['length']/1000 for r in old_rails if r['length'])
        rail_sizes = defaultdict(lambda:[0.,0.,0.,0.])
        lengths = defaultdict(lambda:[0.,0.,0.,0.])
        for ix, selection in enumerate((old_rails,rails)):
            for r in selection:
                label = f"{r['family']} {r['size']}"
                rail_sizes[label][ix] += r['qty']*(r['length'] or 0)/1000
                rail_sizes[label][ix+2] += r['qty'] if not r['length'] else 0
                length_label = str(r['length'])+' mm' if r['length'] else 'Sin longitud'
                lengths[length_label][ix] += r['qty']*(r['length'] or 0)/1000
                lengths[length_label][ix+2] += r['qty']
        def meter_rows(d):
            return [{'name':k,'previous':v[0],'current':v[1],'previous_qty':v[2],'current_qty':v[3]} for k,v in sorted(d.items())]
        quarters=[]
        for y in range(max(2023,year-2),year+1):
            for q in range(1,5):
                last=date(y,q*3,calendar.monthrange(y,q*3)[1]); first=date(y,q*3-2,1)
                if last>end: continue
                qrows=[r for r in rows if first<=r['date']<=last]
                quarters.append({'label':f'Q{q} {y}', 'year':y, 'q':q, 'sales':_sum(qrows),
                                 'rails':_sum([r for r in qrows if r['component']=='rail']),
                                 'guides':_sum([r for r in qrows if r['component']=='guide']),
                                 'screws':_sum([r for r in qrows if r['component']=='screw']),
                                 'nuts':_sum([r for r in qrows if r['component']=='nut']),
                                 'screw_erp':_sum([r for r in qrows if int(r['group_id'] or 0)==1560]),
                                 'guide_qty':_sum([r for r in qrows if r['component']=='guide'],'qty'),
                                 'rail_qty':_sum([r for r in qrows if r['component']=='rail'],'qty'),
                                 'rail_meters':sum(r['qty']*r['length']/1000 for r in qrows if r['component']=='rail' and r['length'])})
        ytd=[]
        for y in range(max(2023,year-3),year+1):
            stop=date(y,end.month,min(end.day,calendar.monthrange(y,end.month)[1]))
            ytd.append({'label':str(y),'sales':_sum([r for r in rows if date(y,1,1)<=r['date']<=stop])})
        snapshots=[]
        for y in range(max(2024,year-2),year+1):
            for q in range(1,5):
                stop=date(y,q*3,calendar.monthrange(y,q*3)[1])
                if stop>end: continue
                w=window(stop); count=sum(v[1]>0 and v[0]>0 for v in w.values()); base=sum(v[0]>0 for v in w.values())
                snapshots.append({'label':f'Q{q} {y}','buyers':count,'active':base,'penetration':100*count/base if base else None})
        documents=[]
        for selection in (previous,current):
            docs=defaultdict(set)
            for r in selection:
                if r['component'] in ('rail','guide') and r['qty']>0: docs[r['document']].add(r['component'])
            documents.append({'both':sum(v=={'guide','rail'} for v in docs.values()),
                              'guide':sum(v=={'guide'} for v in docs.values()), 'rail':sum(v=={'rail'} for v in docs.values())})
        segment_rows=[]
        for seg in sorted({dimensions(c,'segment') for c in active}):
            base={c for c in active if dimensions(c,'segment')==seg}; n=len(base & buyers)
            segment_rows.append({'name':seg,'active':len(base),'buyers':n,'penetration':100*n/len(base) if base else 0})
        segment_rows.sort(key=lambda x:x['active'],reverse=True)
        city_rows=[]
        for city in sorted({dimensions(c,'city') for c in active}):
            base={c for c in active if dimensions(c,'city')==city}; n=len(base & buyers)
            city_rows.append({'name':city,'active':len(base),'buyers':n,'penetration':100*n/len(base) if base else 0})
        city_rows.sort(key=lambda x:x['active'],reverse=True)
        # Unit price is computed from positive-quantity transactions, weighted by pieces.
        price_rows=[]
        for r in aggregate('rail', {'rail'}, lambda r:r['ref']):
            a=[x for x in previous if x['ref']==r['name'] and x['component']=='rail' and x['qty']>0]
            b=[x for x in current if x['ref']==r['name'] and x['component']=='rail' and x['qty']>0]
            aq,bq=_sum(a,'qty'),_sum(b,'qty')
            if aq>0 and bq>0:
                r.update(previous_qty=aq,current_qty=bq,previous=_sum(a),current=_sum(b),prev_price=_sum(a)/aq,price=_sum(b)/bq)
                r['price_change']=_change(r['price'],r['prev_price']);price_rows.append(r)
        price_rows.sort(key=lambda x:x['previous'],reverse=True)
        price_history = {}
        for price_row in price_rows[:20]:
            months = defaultdict(lambda: [0.0, 0.0])
            for row in rows:
                if row['component']=='rail' and row['ref']==price_row['name'] and row['qty']>0:
                    month=row['date'].strftime('%Y-%m'); months[month][0]+=row['sales']; months[month][1]+=row['qty']
            price_history[price_row['name']] = [{'month':m, 'price':v[0]/v[1], 'qty':v[1]} for m,v in sorted(months.items()) if v[1]>0]
        group_sales=lambda selection,code: _sum([r for r in selection if int(r['group_id'] or 0)==code])
        return {'filters':filters,'options':options,'period':period,'year':year,'years':list(range(max(2023,latest.year-4),latest.year+1)),
                'start':start.isoformat(),'end':end.isoformat(),'latest':latest.isoformat(),'prev_start':prev_start.isoformat(),'prev_end':prev_end.isoformat(),
                'sales':_sum(current),'previous_sales':_sum(previous),'sales_change':_change(_sum(current),_sum(previous)),
                'active':len(active),'buyers':len(buyers),'penetration':100*len(buyers)/len(active) if active else None,
                'previous_buyers':len(old_buyers),'entered':len(buyers-old_buyers),'left':len(old_buyers-buyers),'retained':len(buyers & old_buyers),
                'recover':customer_list(recover,'Recuperar'),'develop':customer_list(develop,'Desarrollar'),'overlap':len(recover&develop),
                'segments':segment_rows,'cities':city_rows,'quarters':quarters,'ytd':ytd,'snapshots':snapshots,
                'guide_sales':group_sales(current,1550),'screw_sales':group_sales(current,1560),
                'rail_sales':_sum(rails),'rail_prev_sales':_sum(old_rails),'meters':meters,'previous_meters':old_meters,
                'unparsed_rails':sum(r['qty'] for r in rails if not r['length']),
                'ratio':guide_qty/meters if meters>0 else None,'previous_ratio':old_guide_qty/old_meters if old_meters>0 else None,
                'guide_qty':guide_qty,'documents':documents,'rail_sizes':meter_rows(rail_sizes),'lengths':meter_rows(lengths),
                'rail_families':aggregate('rail',{'rail'},lambda r:r['family']),
                'guide_families':aggregate('guide',{'guide'},lambda r:r['family']),
                'guide_sizes':aggregate('guide',{'guide'},lambda r:f"{r['family']} {r['size']}"),
                'guide_variants':aggregate('guide',{'guide'},lambda r:f"{r['family']} · {_guide_variant(r)}"),
                'screw_families':aggregate('screw',{'screw','nut','screw_set','other'},lambda r: (r['component']+' · '+r['family']) if r['component'] in ('screw','nut') else r['component']),
                'screw_sizes':aggregate('size',{'screw','nut'},lambda r:f"{r['component']} · {r['family']} {r['size']}"),
                'prices':price_rows[:20], 'price_history':price_history}
