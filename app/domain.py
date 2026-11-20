"""Business rules for the Order-to-Audit prototype.

Money is stored as integer paise and quantities use Decimal.  Stock is never
overwritten: every balance is calculated from stock_moves.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "food_audit.db"
TOLERANCE = Decimal("0.03")

def q(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

def paise(value) -> int:
    return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

def rupees(value: int) -> str:
    return f"{Decimal(value) / 100:.2f}"

def connect(path: Path | str = DB_PATH):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, role TEXT, name TEXT);
CREATE TABLE IF NOT EXISTS customers (id INTEGER PRIMARY KEY, name TEXT, state TEXT, gstin TEXT, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, sku TEXT UNIQUE, name TEXT, category TEXT, unit TEXT, hsn TEXT, gst_rate INTEGER, sell_price_paise INTEGER DEFAULT 0, reorder_level TEXT DEFAULT '0');
CREATE TABLE IF NOT EXISTS boms (id INTEGER PRIMARY KEY, product_id INTEGER UNIQUE REFERENCES items(id), expected_output TEXT, output_unit TEXT, version INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS bom_lines (id INTEGER PRIMARY KEY, bom_id INTEGER REFERENCES boms(id), item_id INTEGER REFERENCES items(id), standard_qty TEXT, unit TEXT);
CREATE TABLE IF NOT EXISTS purchases (id INTEGER PRIMARY KEY, supplier TEXT, received_on TEXT, reference TEXT);
CREATE TABLE IF NOT EXISTS production_runs (id INTEGER PRIMARY KEY, product_id INTEGER REFERENCES items(id), run_on TEXT, expected_output TEXT, actual_output TEXT, damaged_pouches TEXT, notes TEXT, labour_paise INTEGER DEFAULT 0, utilities_paise INTEGER DEFAULT 0, status TEXT, created_by INTEGER REFERENCES users(id));
CREATE TABLE IF NOT EXISTS production_consumption (id INTEGER PRIMARY KEY, run_id INTEGER REFERENCES production_runs(id), item_id INTEGER REFERENCES items(id), planned_qty TEXT, actual_qty TEXT, unit TEXT, unit_cost_paise INTEGER, variance_pct TEXT, flagged INTEGER);
CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id), salesman_id INTEGER REFERENCES users(id), ordered_on TEXT, status TEXT, shortage_qty TEXT DEFAULT '0', notes TEXT);
CREATE TABLE IF NOT EXISTS order_lines (id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES orders(id), product_id INTEGER REFERENCES items(id), qty TEXT, unit_price_paise INTEGER);
CREATE TABLE IF NOT EXISTS invoices (id INTEGER PRIMARY KEY, invoice_no TEXT UNIQUE, order_id INTEGER REFERENCES orders(id), customer_id INTEGER REFERENCES customers(id), invoice_on TEXT, taxable_paise INTEGER, cgst_paise INTEGER, sgst_paise INTEGER, igst_paise INTEGER, status TEXT DEFAULT 'POSTED');
CREATE TABLE IF NOT EXISTS invoice_lines (id INTEGER PRIMARY KEY, invoice_id INTEGER REFERENCES invoices(id), product_id INTEGER REFERENCES items(id), qty TEXT, unit_price_paise INTEGER, taxable_paise INTEGER);
CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY, invoice_id INTEGER REFERENCES invoices(id), received_on TEXT, amount_paise INTEGER, reference TEXT, created_by INTEGER REFERENCES users(id));
CREATE TABLE IF NOT EXISTS stock_moves (id INTEGER PRIMARY KEY, moved_on TEXT, item_id INTEGER REFERENCES items(id), qty TEXT, unit_cost_paise INTEGER, movement_type TEXT, source_type TEXT, source_id INTEGER, notes TEXT, created_by INTEGER REFERENCES users(id));
CREATE TABLE IF NOT EXISTS audit_logs (id INTEGER PRIMARY KEY, happened_at TEXT, user_id INTEGER, action TEXT, entity_type TEXT, entity_id INTEGER, detail TEXT);
"""

def initialise(db=DB_PATH):
    db = Path(db)
    db.parent.mkdir(parents=True, exist_ok=True)
    con = connect(db)
    con.executescript(SCHEMA)
    if con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        seed(con)
    con.commit(); con.close()

def seed(con):
    con.executemany("INSERT INTO users(username,password,role,name) VALUES(?,?,?,?)", [
        ("salesman.a", "demo123", "salesman", "Salesman A"),
        ("salesman.b", "demo123", "salesman", "Salesman B"),
        ("admin", "demo123", "admin", "Factory Admin"),
        ("production", "demo123", "production", "Production Supervisor"),
        ("auditor", "demo123", "auditor", "Auditor"),
        ("owner", "demo123", "owner", "Owner"),
    ])
    con.executemany("INSERT INTO customers(name,state,gstin) VALUES(?,?,?)", [
        ("Retailer A", "Tamil Nadu", "33AAAAA0000A1Z5"), ("Distributor B", "Karnataka", "29BBBBB0000B1Z5")])
    items = [
        ("RM-FLOUR", "Flour", "RAW", "kg", "1101", 0, 0, "25"),
        ("RM-OIL", "Cooking oil", "RAW", "litre", "1512", 0, 0, "10"),
        ("RM-SPICE", "Salt and spice mix", "RAW", "kg", "0910", 0, 0, "2"),
        ("PK-POUCH", "200 g pouch", "PACKAGING", "piece", "3923", 0, 0, "100"),
        ("PK-CARTON", "Carton 20 packets", "PACKAGING", "piece", "4819", 0, 0, "10"),
        ("FG-M200", "Murukku 200 g", "FINISHED", "packet", "1905", 5, paise(50), "50"),
    ]
    con.executemany("INSERT INTO items(sku,name,category,unit,hsn,gst_rate,sell_price_paise,reorder_level) VALUES(?,?,?,?,?,?,?,?)", items)
    ids = {r["sku"]: r["id"] for r in con.execute("SELECT id,sku FROM items")}
    con.execute("INSERT INTO boms(product_id,expected_output,output_unit) VALUES(?,?,?)", (ids["FG-M200"], "200", "packet"))
    bom = con.execute("SELECT id FROM boms").fetchone()[0]
    con.executemany("INSERT INTO bom_lines(bom_id,item_id,standard_qty,unit) VALUES(?,?,?,?)", [
        (bom, ids["RM-FLOUR"], "40", "kg"), (bom, ids["RM-OIL"], "10", "litre"),
        (bom, ids["RM-SPICE"], "1.2", "kg"), (bom, ids["PK-POUCH"], "200", "piece"),
        (bom, ids["PK-CARTON"], "10", "piece")])
    admin = con.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
    opening = [("RM-FLOUR",100,42),("RM-OIL",30,140),("RM-SPICE",5,200),("PK-POUCH",500,2.5),("PK-CARTON",30,15),("FG-M200",50,0)]
    for sku, qty, cost in opening:
        move(con, ids[sku], qty, paise(cost), "OPENING", "Opening balance", 0, "Benchmark opening balance", admin)
    log(con, admin, "SEEDED", "system", 0, "Section 5 master data loaded")

def move(con, item_id, quantity, unit_cost, movement_type, source_type, source_id, notes, user_id, moved_on=None):
    con.execute("INSERT INTO stock_moves(moved_on,item_id,qty,unit_cost_paise,movement_type,source_type,source_id,notes,created_by) VALUES(?,?,?,?,?,?,?,?,?)",
      (moved_on or date.today().isoformat(), item_id, str(q(quantity)), unit_cost, movement_type, source_type, source_id, notes, user_id))

def log(con, user_id, action, entity_type, entity_id, detail):
    con.execute("INSERT INTO audit_logs(happened_at,user_id,action,entity_type,entity_id,detail) VALUES(?,?,?,?,?,?)", (datetime.now().isoformat(timespec="seconds"), user_id, action, entity_type, entity_id, detail))

def stock(con, item_id) -> Decimal:
    value = con.execute("SELECT COALESCE(SUM(CAST(qty AS REAL)),0) FROM stock_moves WHERE item_id=?", (item_id,)).fetchone()[0]
    return q(value)

def average_cost(con, item_id) -> int:
    # Moving weighted-average cost of received stock; adequate for this prototype.
    rows = con.execute("SELECT qty,unit_cost_paise FROM stock_moves WHERE item_id=? ORDER BY id", (item_id,)).fetchall()
    qty, value = Decimal(0), Decimal(0)
    for r in rows:
        delta = q(r["qty"])
        if delta > 0:
            qty += delta; value += delta * r["unit_cost_paise"]
        elif qty + delta >= 0:
            qty += delta; value += delta * (value / (qty - delta) if qty - delta else 0)
    return int((value / qty).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if qty else 0

def item_by_sku(con, sku):
    return con.execute("SELECT * FROM items WHERE sku=?", (sku,)).fetchone()

def purchase(con, user_id, sku, qty, rate, supplier="Benchmark Supplier", reference="PUR-001"):
    item = item_by_sku(con, sku)
    cur = con.execute("INSERT INTO purchases(supplier,received_on,reference) VALUES(?,?,?)", (supplier, date.today().isoformat(), reference))
    move(con, item["id"], qty, paise(rate), "PURCHASE_RECEIPT", "Purchase", cur.lastrowid, reference, user_id)
    log(con, user_id, "POSTED", "purchase", cur.lastrowid, f"{qty} {item['unit']} {item['name']} at {rate}")
    return cur.lastrowid

def create_production(con, user_id, product_sku, actual_output, consumption, damaged_pouches=0, labour=0, utilities=0, notes=""):
    product = item_by_sku(con, product_sku)
    bom = con.execute("SELECT * FROM boms WHERE product_id=?", (product["id"],)).fetchone()
    if not bom: raise ValueError("A BOM is required before production can be posted.")
    lines = con.execute("SELECT bl.*,i.name,i.sku FROM bom_lines bl JOIN items i ON i.id=bl.item_id WHERE bom_id=?", (bom["id"],)).fetchall()
    actual = {k: q(v) for k,v in consumption.items()}
    for line in lines:
        used = actual.get(line["sku"], q(line["standard_qty"]))
        if line["sku"] == "PK-POUCH": used += q(damaged_pouches)
        if stock(con, line["item_id"]) < used: raise ValueError(f"Insufficient {line['name']} for this run.")
    cur = con.execute("INSERT INTO production_runs(product_id,run_on,expected_output,actual_output,damaged_pouches,notes,labour_paise,utilities_paise,status,created_by) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (product["id"], date.today().isoformat(), bom["expected_output"], str(q(actual_output)), str(q(damaged_pouches)), notes, paise(labour), paise(utilities), "POSTED", user_id))
    run_id = cur.lastrowid; total_direct = 0
    for line in lines:
        planned = q(line["standard_qty"])
        used = actual.get(line["sku"], planned)
        if line["sku"] == "PK-POUCH": used += q(damaged_pouches)
        rate = average_cost(con, line["item_id"]); total_direct += int(used * rate)
        variance = (used-planned)/planned if planned else Decimal(0)
        flagged = int(abs(variance) > TOLERANCE)
        con.execute("INSERT INTO production_consumption(run_id,item_id,planned_qty,actual_qty,unit,unit_cost_paise,variance_pct,flagged) VALUES(?,?,?,?,?,?,?,?)", (run_id,line["item_id"],str(planned),str(used),line["unit"],rate,str(variance*100),flagged))
        move(con,line["item_id"],-used,rate,"PRODUCTION_ISSUE","Production run",run_id,"Actual consumption",user_id)
    yield_variance=(q(actual_output)-q(bom["expected_output"]))/q(bom["expected_output"])
    finished_cost = int((total_direct+paise(labour)+paise(utilities))/q(actual_output))
    move(con,product["id"],actual_output,finished_cost,"PRODUCTION_RECEIPT","Production run",run_id,"Good packets received",user_id)
    log(con,user_id,"POSTED","production_run",run_id,f"Output {actual_output}; yield variance {yield_variance*100:.2f}%")
    return {"id":run_id,"cost_per_packet_paise":finished_cost,"yield_variance_pct":str(yield_variance*100),"yield_flagged":abs(yield_variance)>TOLERANCE}

def create_order(con, salesman_id, customer_id, lines, notes=""):
    cur=con.execute("INSERT INTO orders(customer_id,salesman_id,ordered_on,status,notes) VALUES(?,?,?,?,?)",(customer_id,salesman_id,date.today().isoformat(),"SUBMITTED",notes)); order_id=cur.lastrowid
    for line in lines:
        item=con.execute("SELECT * FROM items WHERE id=?",(line["product_id"],)).fetchone()
        if not item or item["category"]!="FINISHED": raise ValueError("Orders may contain finished products only.")
        con.execute("INSERT INTO order_lines(order_id,product_id,qty,unit_price_paise) VALUES(?,?,?,?)",(order_id,item["id"],str(q(line["qty"])),line.get("unit_price_paise",item["sell_price_paise"])))
    log(con,salesman_id,"CREATED","order",order_id,"Submitted from salesman order entry")
    return order_id

def approve_order(con, admin_id, order_id):
    order=con.execute("SELECT * FROM orders WHERE id=?",(order_id,)).fetchone()
    if not order or order["status"] not in ("SUBMITTED","NEEDS_STOCK"): raise ValueError("Only submitted orders can be approved.")
    shortage=Decimal(0)
    lines=con.execute("SELECT ol.*,i.name FROM order_lines ol JOIN items i ON i.id=ol.product_id WHERE order_id=?",(order_id,)).fetchall()
    for line in lines: shortage += max(Decimal(0),q(line["qty"])-stock(con,line["product_id"]))
    if shortage:
        con.execute("UPDATE orders SET status='NEEDS_STOCK',shortage_qty=? WHERE id=?",(str(shortage),order_id)); log(con,admin_id,"FLAGGED","order",order_id,f"Stock shortage {shortage}")
        return {"approved":False,"shortage":str(shortage)}
    con.execute("UPDATE orders SET status='APPROVED',shortage_qty='0' WHERE id=?",(order_id,)); log(con,admin_id,"APPROVED","order",order_id,"Stock checked")
    return {"approved":True,"shortage":"0"}

def dispatch_and_invoice(con, admin_id, order_id):
    order=con.execute("SELECT o.*,c.state,c.gstin FROM orders o JOIN customers c ON c.id=o.customer_id WHERE o.id=?",(order_id,)).fetchone()
    if not order or order["status"]!="APPROVED": raise ValueError("Approve an in-stock order before dispatch.")
    lines=con.execute("SELECT ol.*,i.name,i.hsn,i.gst_rate FROM order_lines ol JOIN items i ON i.id=ol.product_id WHERE order_id=?",(order_id,)).fetchall()
    taxable=sum(int(q(x["qty"])*x["unit_price_paise"]) for x in lines); tax=sum(int(q(x["qty"])*x["unit_price_paise"]*x["gst_rate"]/100) for x in lines)
    intrastate=order["state"]=="Tamil Nadu"; cgst=tax//2 if intrastate else 0; sgst=tax-cgst if intrastate else 0; igst=tax if not intrastate else 0
    count=con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]+1; no=f"FA/2026-27/{count:04d}"
    cur=con.execute("INSERT INTO invoices(invoice_no,order_id,customer_id,invoice_on,taxable_paise,cgst_paise,sgst_paise,igst_paise) VALUES(?,?,?,?,?,?,?,?)",(no,order_id,order["customer_id"],date.today().isoformat(),taxable,cgst,sgst,igst)); invoice_id=cur.lastrowid
    for line in lines:
        line_taxable=int(q(line["qty"])*line["unit_price_paise"]); con.execute("INSERT INTO invoice_lines(invoice_id,product_id,qty,unit_price_paise,taxable_paise) VALUES(?,?,?,?,?)",(invoice_id,line["product_id"],line["qty"],line["unit_price_paise"],line_taxable))
        move(con,line["product_id"],-q(line["qty"]),average_cost(con,line["product_id"]),"SALES_DISPATCH","GST Invoice",invoice_id,no,admin_id)
    con.execute("UPDATE orders SET status='DISPATCHED' WHERE id=?",(order_id,)); log(con,admin_id,"POSTED","invoice",invoice_id,no)
    return invoice_id

def record_payment(con,user_id,invoice_id,amount,reference):
    invoice=con.execute("SELECT * FROM invoices WHERE id=?",(invoice_id,)).fetchone()
    if not invoice: raise ValueError("Invoice not found.")
    cur=con.execute("INSERT INTO payments(invoice_id,received_on,amount_paise,reference,created_by) VALUES(?,?,?,?,?)",(invoice_id,date.today().isoformat(),paise(amount),reference,user_id)); log(con,user_id,"RECORDED","payment",cur.lastrowid,reference); return cur.lastrowid

def run_benchmark(con, user_id):
    if con.execute("SELECT COUNT(*) FROM production_runs").fetchone()[0]: raise ValueError("Benchmark is already posted. Reset the database to replay it.")
    purchase(con,user_id,"RM-FLOUR",60,45,"Benchmark Flour Supplier","PUR-001")
    run=create_production(con,user_id,"FG-M200",188,{"RM-FLOUR":40,"RM-OIL":10.5,"RM-SPICE":1.2,"PK-POUCH":188,"PK-CARTON":9},6,1200,600,"Mandatory benchmark run")
    retailer=con.execute("SELECT id FROM customers WHERE name='Retailer A'").fetchone()[0]; dist=con.execute("SELECT id FROM customers WHERE name='Distributor B'").fetchone()[0]
    sa=con.execute("SELECT id FROM users WHERE username='salesman.a'").fetchone()[0]; sb=con.execute("SELECT id FROM users WHERE username='salesman.b'").fetchone()[0]; product=item_by_sku(con,"FG-M200")
    first=create_order(con,sa,retailer,[{"product_id":product["id"],"qty":150}]); approve_order(con,user_id,first); inv=dispatch_and_invoice(con,user_id,first); second=create_order(con,sb,dist,[{"product_id":product["id"],"qty":120}]); shortage=approve_order(con,user_id,second)
    record_payment(con,user_id,inv,4000,"UTR-DEMO-4000")
    return {"production":run,"retailer_order":first,"retailer_invoice":inv,"distributor_order":second,"distributor_check":shortage}

def reset(db=DB_PATH):
    path=Path(db)
    if path.exists(): path.unlink()
    initialise(path)
