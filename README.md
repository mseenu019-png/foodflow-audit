# FoodFlow Audit

A compact, ledger-backed order-to-audit prototype for a small South Indian snack manufacturer. It is designed around the required benchmark: a field order becomes a GST invoice and dispatch, while the same finished-goods ledger is replenished by recipe-based production.

## Run locally

No package installation is required. The app uses the Python 3 standard library and SQLite.

```powershell
python app/server.py
```

Open `http://localhost:8000`. To run the rules tests:

```powershell
python -m unittest discover -s tests -v
```

If `python` is not on PATH, use the Python executable in your local runtime or install Python 3.11+.

## Demo logins

All demo accounts use password `demo123`.

| User | Role | Use in the demo |
| --- | --- | --- |
| `salesman.a` | Salesman | Mobile-friendly field order entry |
| `salesman.b` | Salesman | Distributor B insufficient-stock example |
| `admin` | Factory admin | Approval, GST invoice, dispatch and payments |
| `production` | Production supervisor | Production runs and BOM variance |
| `auditor` | Auditor | Read-only reports and audit trail |
| `owner` | Owner | Dashboard and alerts |

## Stack and rationale

The prototype uses a dependency-free Python HTTP server, SQLite, and responsive vanilla JavaScript. This keeps a reviewer’s local setup to one command and makes the business logic easy to inspect live. SQLite is a real relational database; the schema can move to PostgreSQL without changing the accounting model.

## What is implemented

- Role-aware login and navigation for salesman, admin, production, auditor and owner.
- Responsive salesman order capture; orders are submitted before any billing action.
- Admin stock check, approval, GST invoice generation as a PDF, dispatch and payment capture.
- BOM master for Murukku 200 g, production issue/receipt, actual-vs-planned consumption and yield alerts beyond 3%.
- Separate raw, packaging and finished-goods inventory, reconciled from an append-only `stock_moves` ledger.
- Weighted-average material valuation, run-level labour and gas/power allocation, cost per good packet.
- Dashboard, stock summary, GST/sales register, receivables and CSV exports.
- Audit log for key posted actions and automated benchmark tests.

## Benchmark walkthrough

1. Sign in as `admin` and choose **Run benchmark scenario** on the dashboard.
2. Inspect Production to see the 188 vs 200 packet yield (-6%) and the 10.5 L vs 10 L oil (+5%) alerts.
3. Inspect Orders: Retailer A is dispatched; Distributor B is marked **Needs stock** with a 32-packet shortage.
4. Open Reports for the Retailer A invoice PDF and sales/GST summary. Export sales or stock CSV if needed.
5. Inspect Inventory and the audit trail to explain every stock movement.

### Required benchmark results

| Result | Prototype result |
| --- | ---: |
| Flour closing balance | 120 kg |
| Oil closing balance | 19.5 L |
| Pouches closing balance | 306 pieces |
| Finished goods after production | 238 packets |
| Finished goods after Retailer A dispatch | 88 packets |
| Yield variance | -6%, flagged |
| Oil consumption variance | +5%, flagged |
| Retailer A invoice | Rs 7,500 taxable + Rs 187.50 CGST + Rs 187.50 SGST = Rs 7,875 |
| Retailer A outstanding after payment | Rs 3,875 |
| Distributor B | 32-packet shortage, IGST would apply on a Karnataka invoice |

## Costing assumption

Material is valued using moving weighted average from the stock ledger. After the flour purchase, flour costs `(100 × 42 + 60 × 45) / 160 = Rs 43.125 per kg`; the stored paise rate is rounded to Rs 43.13. Actual material usage plus Rs 1,200 labour and Rs 600 gas/power is divided only by 188 good packets. The visible cost is Rs 31.14 per packet; it intentionally includes yield loss and the six damaged pouches.

## Assumptions and known gaps

- The factory is in Tamil Nadu. Tamil Nadu customers receive CGST + SGST; interstate customers receive IGST.
- One dispatch is supported per order; partial dispatches, credit notes and returns are deliberately left for the next iteration.
- Units are stored per item, and the benchmark’s kg, litre, piece and packet quantities are validated. A production-grade implementation would add a conversion table for alternate supplier units.
- Sessions and passwords are demo-only. Production deployment should use hashed passwords, CSRF protection, HTTPS, PostgreSQL, backups and immutable journal controls.
- The PDF is intentionally simple and generated without external dependencies.

## Suggested eight-minute demo

1. 0:00-0:45 - sign in as Salesman A and show the mobile order screen.
2. 0:45-2:30 - sign in as Admin and run the benchmark, then show the flow on Orders.
3. 2:30-4:30 - show production planned/actual inputs, stock movements and the two variance flags.
4. 4:30-5:45 - show Retailer A invoice PDF, CGST/SGST and Rs 3,875 receivable.
5. 5:45-6:30 - show Distributor B’s 32-packet block and explain IGST.
6. 6:30-7:30 - show reports, CSV export and stock reconciliation.
7. 7:30-8:00 - show tests, audit log and explain the weighted-average costing decision.
