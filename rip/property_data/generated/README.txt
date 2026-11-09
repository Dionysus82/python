IFRS 9 cash-flow and collateral extracts
Property portfolio, reporting dates 31/12/2025 through 30/11/2026

The construction rules are unchanged from the previous extract.

Cash flow
- One table per month-end, plus CASH_FLOW_ALL.csv.
- Included: every contract with BAL_OUTSTD > 0. That is 40 customer loans and the Apex Global Holdings Limited bond CTR-0010-06.
- Excluded: 19 off-balance facilities with zero outstanding.
- Dates are every six months, counted back from MATURITY_DATE. A date strictly before the reporting date is dropped. The last date is the maturity date. Where the maturity falls on the reporting date and the balance is still outstanding, that date is kept and discounted as period 1.
- Month-end maturities stay on month-end (31 August steps back to 28 or 29 February).
- Each month is rebuilt from that month's own balance, grade, and maturity. The coupon and amortization method stay on the contract. See CONTRACT_AMORTIZATION.csv.
- Customer loans: 24 bullet, 12 equal principal, 4 declining (weights n, n-1, ..., 1). The bond is bullet at the borrower's 5.5% coupon. Government names are 3.0%.
- Interest = opening principal x coupon x 1/2, rounded to the cent. Interest (I) and principal (N) are separate rows. Bullet dates before maturity have interest only.
- OUTSTANDING on an interest row is principal before that date's repayment. On a principal row it is principal after. The final outstanding is 0 and principal sums to the balance.
- Present value discounts each date's interest plus principal by (1 + coupon/2) ^ period, period 1 being the first date on or after the reporting date. The final interest is moved by one cent until the present value is within 0.005 of the balance.
- Monthly files omit REPORTING_DATE. The combined file includes it. Dates are DD/MM/YYYY. Discount rates are decimals.

Collateral
- One row per contract per month (60), including zero-balance off-balance facilities and the bond.
- COLLATERAL_REFERENCE is the source COLLATERAL_ID. The fictional Hong Kong address is fixed for that id across all 12 months and follows the collateral type.
- Market value, net realizable value, and outstanding balance are copied from the portfolio. LTV = balance / market value and LTV on NRV = balance / net realizable value, six decimal places. A zero balance has both LTVs at 0.
- Charge rank is 1. Valuation date is the reporting date.

Files
- cashflow/CASH_FLOW_YYYYMM.csv and Cash_Flow.xlsx
- collateral/COLLATERAL_YYYYMM.csv and Collateral.xlsx
- CONTRACT_AMORTIZATION.csv
- VALIDATION.txt

These figures are a synthetic demonstration extract, not a credit decision.
