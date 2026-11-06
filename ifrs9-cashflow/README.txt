说明（合成测试数据，不是授信、会计或监管结论）

根据物业组合 2026 年 1 月至 12 月的月末快照，各生成一张 CASH_FLOW 表。
纳入余额大于 0 的客户贷款，每月 40 笔；Off-Bal 余额为 0，每月排除 20 笔。
付息日从到期日每半年往回推，只保留报告日之后的日期，最后一期等于到期日。
利率按借款人对照：政府类 3.0%，其余 4.5% 至 6.0%，详见英文说明。
同一合同全年使用同一种摊还：子弹 24 笔、等额本金 12 笔、前高后低 4 笔。
利息 = 期初余额 × 利率 × 0.5。本金还完后余额为 0。
半年折现后，本金加利息的现值与当月 BAL_OUTSTD 相差不超过半分。
DISCOUNT_RATE 是小数，0.045000 表示 4.5%。日期格式为 DD/MM/YYYY。
每月按该月自己的余额重算，不是把 1 月的计划逐月滚存。

英文规则说明如下。

Property portfolio cash flow tables (synthetic test data)
=========================================================

These files are demonstration cash flows for IFRS 9 ECL, LGD, cash shortfall,
recovery, model validation and UAT. They are not a credit, accounting or
regulatory result.

Source
  PROPERTY_PORTFOLIO_FINAL_202601.csv through 202612.csv
  One cash flow table is generated for each month-end reporting date.

Selection
  Customer loans with BAL_OUTSTD > 0 are included (40 contracts each month).
  Off-Bal facilities have zero outstanding and are excluded (20 each month).

Columns in CASH_FLOW_YYYYMM.csv
  TABLE_NAME, CONTRACT_REFERENCE, BORROWER_NAME, BORROWER_GRADE,
  CURRENT_PD_GRADE, CCY_CODE, DISCOUNT_RATE, AMORTIZATION_METHOD,
  CASH_FLOW_DATE, CASH_FLOW_TYPE, CASH_FLOW_AMOUNT, OUTSTANDING

  CASH_FLOW_ALL_2026.csv adds REPORTING_DATE so the twelve months can sit
  in one file. The monthly files follow the requested column list exactly.

Conventions
  CASH_FLOW_TYPE I = interest, N = principal.
  CASH_FLOW_DATE is DD/MM/YYYY, the same convention as the source files.
  DISCOUNT_RATE is a decimal. 0.045000 means 4.5 percent.
  OUTSTANDING on an interest row is the principal before that date's
  repayment. OUTSTANDING on a principal row is the principal after it.
  A bullet contract shows the full balance on each interest row and zero
  after the single principal row on the maturity date.
  Amounts are HKD with two decimal places. Currency matches the contract.

Dates
  Payment dates are every six months, counted back from MATURITY_DATE.
  Each date is measured from the maturity anchor, so a 31 August maturity
  stays on 31 August and 28 February. Dates on or before REPORTING_DATE
  are dropped. The last date is the maturity date.

Interest and principal
  Interest = opening outstanding x discount rate x 0.5.
  Bullet: 100 percent of principal on the maturity date.
  Equal amortisation: equal principal on each remaining date. The last
  instalment absorbs the cent rounding.
  Declining amortisation: principal weights n, n-1, ... , 1, so the
  earliest remaining instalment is the largest.
  The same contract keeps the same method in every month: 24 bullet,
  12 equal, 4 declining (60 / 30 / 10). See CONTRACT_AMORTIZATION.csv.

Present value
  Remaining coupons are discounted semiannually:
  PV = sum of (interest + principal) / (1 + rate/2) ^ period.
  Period 1 is the first date after the reporting date. Where cent
  rounding leaves a gap, the final interest amount moves by one cent
  at a time until PV is within half a cent of BAL_OUTSTD. Principal
  still sums to BAL_OUTSTD and the final outstanding is zero.

Each month is built from that month's own BAL_OUTSTD. The source balances
move around from month to month, so this is not a roll-forward of the
January schedule.

Checked for every contract and every month
  final outstanding = 0
  no cash flow date after maturity
  no cash flow date on or before the reporting date
  PV within 0.005 of BAL_OUTSTD
  currency matches the source contract
  interest and principal are on separate rows
  portfolio mix is 24 / 12 / 4
  discount rate matches the borrower map
