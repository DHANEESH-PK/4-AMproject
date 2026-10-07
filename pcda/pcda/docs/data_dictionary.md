# Data Dictionary — Synthetic Retail Ledger (2026)

The "documents" half of the problem statement. The agent must READ this, not guess.

## Business rules
- Reporting currency is **USD**. EUR amounts are converted at the month-average rate in `fx_rates.csv` (month of the order date).
- The **fiscal year starts 1 April**. FY Q1 = Apr–Jun, FY Q2 = Jul–Sep, FY Q3 = Oct–Dec, FY Q4 = Jan–Mar.
- Revenue = sum of order amounts. Net revenue = revenue minus refunds (refunds booked to the month of the original order).
- `monthly_summary.csv` is a finance export prepared manually. `orders.csv` is the system of record.

## orders.csv
| column | meaning |
|---|---|
| order_id | unique order key (re-exports can repeat a row) |
| customer_id | FK to customers.csv |
| order_date | text date — format depends on `source_system` |
| source_system | `us_shop` = MM/DD/YYYY, `eu_shop` = DD/MM/YYYY, `legacy` = **format not documented** |
| amount | text; may carry `$`, `€`, `USD`, `EUR`; eu_shop uses `.` for thousands and `,` for decimals |
| currency | ISO code; may be blank when the amount text already carries a symbol |

## customers.csv
customer_id, name, region (North / South / East / West). One region per customer is expected.

## refunds.csv
refund_id, order_id, refund_date (ISO), amount, currency (same as the original order).

## fx_rates.csv
month (YYYY-MM), from_ccy, to_ccy, rate. Coverage: 2026-01 to 2026-06.
