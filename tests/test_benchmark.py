import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from domain import connect, initialise, item_by_sku, run_benchmark, stock

class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.db=Path(self.temp.name)/'demo.db'; initialise(self.db); self.con=connect(self.db)
        self.admin=self.con.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
    def tearDown(self): self.con.close(); self.temp.cleanup()
    def balance(self, sku): return stock(self.con,item_by_sku(self.con,sku)['id'])
    def test_required_benchmark_balances_and_flags(self):
        r=run_benchmark(self.con,self.admin); self.con.commit()
        self.assertEqual(str(self.balance('RM-FLOUR')),'120.000')
        self.assertEqual(str(self.balance('RM-OIL')),'19.500')
        self.assertEqual(str(self.balance('PK-POUCH')),'306.000')
        self.assertEqual(str(self.balance('FG-M200')),'88.000')
        self.assertEqual(r['distributor_check']['shortage'],'32.000')
        run=self.con.execute('SELECT * FROM production_runs').fetchone()
        self.assertEqual(run['actual_output'],'188.000')
        flags=self.con.execute('SELECT i.sku,flagged FROM production_consumption pc JOIN items i ON i.id=pc.item_id').fetchall()
        self.assertEqual(dict((x['sku'],x['flagged']) for x in flags)['RM-OIL'],1)
    def test_invoice_tax_and_receivable(self):
        run_benchmark(self.con,self.admin); self.con.commit()
        inv=self.con.execute('SELECT * FROM invoices').fetchone()
        self.assertEqual(inv['taxable_paise'],750000)
        self.assertEqual(inv['cgst_paise'],18750); self.assertEqual(inv['sgst_paise'],18750); self.assertEqual(inv['igst_paise'],0)
        paid=self.con.execute('SELECT SUM(amount_paise) FROM payments WHERE invoice_id=?',(inv['id'],)).fetchone()[0]
        self.assertEqual(inv['taxable_paise']+inv['cgst_paise']+inv['sgst_paise']-paid,387500)

if __name__=='__main__': unittest.main()
