"""Dependency-free web server for the Order-to-Audit demo."""
from __future__ import annotations
import csv, io, json, mimetypes, os, secrets, sys
from datetime import date
from decimal import Decimal
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from domain import DB_PATH, average_cost, connect, create_order, create_production, dispatch_and_invoice, initialise, item_by_sku, paise, record_payment, reset, run_benchmark, rupees, stock

ROOT=Path(__file__).resolve().parents[1]; PUBLIC=ROOT/'public'; SESSIONS={}

def rowdict(row): return dict(row) if row else None
def money(n): return rupees(n or 0)

def summary(con):
    items=[]
    for x in con.execute("SELECT * FROM items ORDER BY category,name"):
        qty=stock(con,x['id']); items.append({**dict(x),'balance':str(qty),'average_cost_paise':average_cost(con,x['id']),'low_stock': qty <= Decimal(x['reorder_level'])})
    today_orders=con.execute("SELECT COUNT(*) FROM orders WHERE ordered_on=?",(date.today().isoformat(),)).fetchone()[0]
    outstanding=con.execute("SELECT COALESCE(SUM(i.taxable_paise+i.cgst_paise+i.sgst_paise+i.igst_paise)-COALESCE((SELECT SUM(p.amount_paise) FROM payments p WHERE p.invoice_id=i.id),0),0) FROM invoices i").fetchone()[0]
    alerts=con.execute("SELECT pr.id, i.name, pr.expected_output,pr.actual_output,'Yield' AS kind, ROUND((CAST(pr.actual_output AS REAL)-CAST(pr.expected_output AS REAL))*100/CAST(pr.expected_output AS REAL),1) AS variance FROM production_runs pr JOIN items i ON i.id=pr.product_id WHERE ABS(CAST(pr.actual_output AS REAL)-CAST(pr.expected_output AS REAL))/CAST(pr.expected_output AS REAL) > 0.03 UNION ALL SELECT pc.run_id,i.name,pc.planned_qty,pc.actual_qty,'Consumption',ROUND(CAST(pc.variance_pct AS REAL),1) FROM production_consumption pc JOIN items i ON i.id=pc.item_id WHERE pc.flagged=1 ORDER BY 1 DESC").fetchall()
    return {'today_orders':today_orders,'outstanding_paise':outstanding,'stock':items,'alerts':[dict(a) for a in alerts]}

def orders(con, user):
    sql="SELECT o.*,c.name customer,u.name salesman FROM orders o JOIN customers c ON c.id=o.customer_id JOIN users u ON u.id=o.salesman_id"; args=[]
    if user['role']=='salesman': sql+=" WHERE o.salesman_id=?"; args=[user['id']]
    sql+=" ORDER BY o.id DESC"; result=[]
    for o in con.execute(sql,args):
        lines=[dict(x) for x in con.execute("SELECT ol.*,i.name,i.unit FROM order_lines ol JOIN items i ON i.id=ol.product_id WHERE order_id=?",(o['id'],))]
        result.append({**dict(o),'lines':lines})
    return result

def production(con):
    result=[]
    for r in con.execute("SELECT pr.*,i.name product FROM production_runs pr JOIN items i ON i.id=pr.product_id ORDER BY pr.id DESC"):
        lines=[dict(x) for x in con.execute("SELECT pc.*,i.name FROM production_consumption pc JOIN items i ON i.id=pc.item_id WHERE run_id=?",(r['id'],))]
        result.append({**dict(r),'lines':lines,'cost_per_packet_paise': int((sum(Decimal(x['actual_qty'])*x['unit_cost_paise'] for x in lines)+r['labour_paise']+r['utilities_paise'])/Decimal(r['actual_output'])) if Decimal(r['actual_output']) else 0})
    return result

def report(con):
    sales=[]
    for x in con.execute("SELECT i.*,c.name customer, COALESCE((SELECT SUM(amount_paise) FROM payments p WHERE p.invoice_id=i.id),0) paid FROM invoices i JOIN customers c ON c.id=i.customer_id ORDER BY i.id"):
        total=x['taxable_paise']+x['cgst_paise']+x['sgst_paise']+x['igst_paise']; sales.append({**dict(x),'total_paise':total,'outstanding_paise':total-x['paid']})
    gst=con.execute("SELECT COALESCE(SUM(taxable_paise),0) taxable,COALESCE(SUM(cgst_paise),0) cgst,COALESCE(SUM(sgst_paise),0) sgst,COALESCE(SUM(igst_paise),0) igst FROM invoices").fetchone()
    return {'sales':sales,'gst':dict(gst),'production':production(con),'stock':summary(con)['stock']}

def invoice_pdf(con, invoice_id):
    inv=con.execute("SELECT i.*,c.name,c.gstin,c.state FROM invoices i JOIN customers c ON c.id=i.customer_id WHERE i.id=?",(invoice_id,)).fetchone()
    if not inv: raise ValueError('Invoice not found')
    lines=con.execute("SELECT il.*,it.name,it.hsn FROM invoice_lines il JOIN items it ON it.id=il.product_id WHERE invoice_id=?",(invoice_id,)).fetchall()
    text=["SRI MURUKKU FOODS", "GSTIN: 33ABCDE1234F1Z5", "TAX INVOICE", f"Invoice: {inv['invoice_no']}   Date: {inv['invoice_on']}", f"Bill to: {inv['name']} ({inv['state']})", f"GSTIN: {inv['gstin']}", ""]
    for line in lines: text.append(f"{line['name']} | HSN {line['hsn']} | {line['qty']} packets x Rs {money(line['unit_price_paise'])} = Rs {money(line['taxable_paise'])}")
    text += ["",f"Taxable value: Rs {money(inv['taxable_paise'])}",f"CGST: Rs {money(inv['cgst_paise'])}",f"SGST: Rs {money(inv['sgst_paise'])}",f"IGST: Rs {money(inv['igst_paise'])}",f"Invoice total: Rs {money(inv['taxable_paise']+inv['cgst_paise']+inv['sgst_paise']+inv['igst_paise'])}","Computer generated invoice"]
    # Minimal, deliberately simple PDF using built-in Helvetica.
    safe=[s.replace('\\','\\\\').replace('(','\\(').replace(')','\\)') for s in text]
    stream='BT /F1 12 Tf 50 770 Td 16 TL ' + ' '.join(f'({s}) Tj T*' for s in safe) + ' ET'
    objs=['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Kids [3 0 R] /Count 1 >>','<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>','<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',f'<< /Length {len(stream.encode())} >>\nstream\n{stream}\nendstream']
    pdf='%PDF-1.4\n'; offsets=[0]
    for n,obj in enumerate(objs,1): offsets.append(len(pdf.encode())); pdf+=f'{n} 0 obj\n{obj}\nendobj\n'
    xref=len(pdf.encode()); pdf+=f'xref\n0 {len(objs)+1}\n0000000000 65535 f \n'+''.join(f'{o:010d} 00000 n \n' for o in offsets[1:])+f'trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'
    return pdf.encode(),inv['invoice_no'].replace('/','-')+'.pdf'

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(PUBLIC),**kwargs)
    def json(self,status,data):
        body=json.dumps(data,default=str).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def user(self):
        cookie=SimpleCookie(self.headers.get('Cookie')); token=cookie.get('session'); return SESSIONS.get(token.value) if token else None
    def body(self):
        length=int(self.headers.get('Content-Length','0')); return json.loads(self.rfile.read(length) or b'{}')
    def guard(self,*roles):
        user=self.user()
        if not user: self.json(401,{'error':'Please sign in.'}); return None
        if roles and user['role'] not in roles: self.json(403,{'error':'This role cannot perform that action.'}); return None
        return user
    def do_GET(self):
        if self.path.startswith('/api/'):
            try:
                user=self.guard()
                if not user:return
                con=connect()
                path=self.path.split('?')[0]
                if path=='/api/me': data=user
                elif path=='/api/dashboard': data=summary(con)
                elif path=='/api/items': data=[dict(x) for x in con.execute('SELECT * FROM items ORDER BY category,name')]
                elif path=='/api/customers': data=[dict(x) for x in con.execute('SELECT * FROM customers ORDER BY name')]
                elif path=='/api/orders': data=orders(con,user)
                elif path=='/api/production': data=production(con)
                elif path=='/api/reports': data=report(con)
                elif path=='/api/audit': data=[dict(x) for x in con.execute('SELECT a.*,u.name user FROM audit_logs a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 50')]
                elif path.startswith('/api/invoices/') and path.endswith('.pdf'):
                    pdf,name=invoice_pdf(con,int(path.split('/')[-1].split('.')[0])); self.send_response(200); self.send_header('Content-Type','application/pdf'); self.send_header('Content-Disposition',f'attachment; filename="{name}"'); self.send_header('Content-Length',str(len(pdf))); self.end_headers(); self.wfile.write(pdf); con.close(); return
                elif path.startswith('/api/export/'):
                    kind=path.split('/')[-1]; data=report(con); rows=data.get(kind, data['sales'] if kind=='sales' else data['stock']); out=io.StringIO(); writer=csv.DictWriter(out,fieldnames=rows[0].keys() if rows else ['empty']); writer.writeheader(); writer.writerows(rows); blob=out.getvalue().encode(); self.send_response(200); self.send_header('Content-Type','text/csv'); self.send_header('Content-Disposition',f'attachment; filename="{kind}-report.csv"'); self.end_headers(); self.wfile.write(blob); con.close(); return
                else: self.json(404,{'error':'Not found'}); con.close(); return
                con.close(); self.json(200,data)
            except Exception as e: self.json(400,{'error':str(e)})
        else: super().do_GET()
    def do_POST(self):
        try:
            data=self.body(); path=self.path
            if path=='/api/login':
                con=connect(); x=con.execute('SELECT id,username,role,name FROM users WHERE username=? AND password=?',(data.get('username'),data.get('password'))).fetchone(); con.close()
                if not x: return self.json(401,{'error':'Invalid demo login.'})
                token=secrets.token_urlsafe(24); SESSIONS[token]=dict(x); self.send_response(200); self.send_header('Set-Cookie',f'session={token}; HttpOnly; SameSite=Lax; Path=/'); self.send_header('Content-Type','application/json'); self.end_headers(); self.wfile.write(json.dumps(dict(x)).encode()); return
            if path=='/api/logout':
                cookie=SimpleCookie(self.headers.get('Cookie')); token=cookie.get('session');
                if token: SESSIONS.pop(token.value,None)
                self.send_response(204);self.send_header('Set-Cookie','session=; Max-Age=0; Path=/');self.end_headers();return
            user=self.guard()
            if not user:return
            con=connect()
            if path=='/api/orders':
                if user['role']!='salesman': raise PermissionError('Only salesmen create field orders.')
                answer={'id':create_order(con,user['id'],data['customer_id'],data['lines'],data.get('notes',''))}
            elif path.endswith('/approve'):
                if user['role']!='admin': raise PermissionError('Only admin approves orders.')
                from domain import approve_order; answer=approve_order(con,user['id'],int(path.split('/')[-2]))
            elif path.endswith('/dispatch'):
                if user['role']!='admin': raise PermissionError('Only admin dispatches invoices.')
                answer={'invoice_id':dispatch_and_invoice(con,user['id'],int(path.split('/')[-2]))}
            elif path=='/api/production':
                if user['role'] not in ('production','admin'): raise PermissionError('Production role required.')
                answer=create_production(con,user['id'],data['product_sku'],data['actual_output'],data['consumption'],data.get('damaged_pouches',0),data.get('labour',0),data.get('utilities',0),data.get('notes',''))
            elif path=='/api/payments':
                if user['role']!='admin': raise PermissionError('Only admin records payments.')
                answer={'id':record_payment(con,user['id'],data['invoice_id'],data['amount'],data.get('reference',''))}
            elif path=='/api/demo/run':
                if user['role'] not in ('admin','production'): raise PermissionError('Admin or production role required.')
                answer=run_benchmark(con,user['id'])
            elif path=='/api/demo/reset':
                if user['role']!='admin': raise PermissionError('Admin role required.')
                con.close(); reset(); return self.json(200,{'ok':True})
            else: con.close(); return self.json(404,{'error':'Not found'})
            con.commit();con.close();self.json(201,answer)
        except Exception as e:
            try: con.rollback();con.close()
            except Exception: pass
            self.json(400,{'error':str(e)})

if __name__=='__main__':
    os.chdir(ROOT); initialise(); port=int(os.environ.get('PORT','8000')); print(f'Food Audit running at http://localhost:{port}')
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
