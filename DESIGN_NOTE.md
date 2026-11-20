# FoodFlow Audit Design Note

## Purpose

FoodFlow Audit records each business event once and produces stock, costing and accounting views from the same source data. It is intentionally small enough to explain in an interview, while keeping the production loop as first-class data rather than a spreadsheet attachment.

## Data model

```text
Users ──< Orders >── Customers
              │
              ├──< OrderLines >── Items ──< StockMoves
              └── Invoice ──< InvoiceLines ──< Payments

Items (finished product) ──< BOM ──< BOMLines >── Items (raw/packaging)
                                  │
ProductionRun ──< ProductionConsumption ──┘
```

`Items` holds raw materials, packaging and finished goods. A BOM represents a versioned standard recipe and expected yield. `stock_moves` is the central append-only journal: opening stock, purchase receipts, production issues, production receipts and sales dispatches all write a source type and source ID. The displayed balance is `SUM(qty)` from this journal, never a manually editable field.

## Event flow and controls

1. A salesman submits an order. It has no stock or finance effect.
2. Admin approval checks the current finished-goods ledger. A short order becomes `NEEDS_STOCK`; it cannot invoice or dispatch.
3. Dispatch posts the GST invoice and a negative finished-goods movement in one database transaction.
4. A production run reads its BOM. It checks ingredient availability, posts negative ingredient movements, posts good output as a finished-goods receipt, and stores planned versus actual consumption.
5. Payments reduce invoice receivables but never change sales or stock.

The audit log records actor, time, action and entity. In a production system, invoice cancellation would create a credit note and reversing ledger entries rather than deleting a row.

## Costing and variance

The valuation method is moving weighted average. Each receipt updates an item’s available quantity and value; an issue uses the current average rate. This is practical for a small factory where individual flour/oil lots are often mixed. Run cost is:

`actual materials + actual packaging + labour + gas/power`, divided by good packets produced.

This prevents damaged pouches and poor yield from disappearing into a monthly average. A consumption or yield variance with absolute value over 3% receives an alert. For the benchmark, oil is +5% and yield is -6%, so both are flagged.

## Deliberate scope

The benchmark supports kg, litres, pieces and packets on their source records. The next production version would add conversion ratios, supplier lots/expiry, FEFO picking, partial dispatches, returns, credit notes, approval history and a PostgreSQL deployment. Those additions do not require changing the ledger model.
