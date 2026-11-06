抵押品表（合成测试数据，不是授信、估值或监管结论）

按物业组合 2026 年 1 月至 12 月的月末快照各生成一张表，每月 60 行。
一笔合同对应一个抵押品。COLLATERAL_REFERENCE 等于原文件的 COLLATERAL_ID。
地址是虚构的，同一抵押品全年使用同一地址。市值、可变现净值和表内余额沿用原文件。
LTV = 表内余额 / 市值。LTV_ON_NRV = 表内余额 / 可变现净值。两个比率保留 6 位小数。
Off-Bal 的表内余额为 0，所以两个 LTV 都是 0。抵押顺位全部为第一顺位。估值日等于当月报告日。

Columns: REPORTING_DATE, CONTRACT_REFERENCE, COLLATERAL_REFERENCE, BORROWER_NAME,
INSTRUMENT, COLLATERAL_TYPE, CCY_CODE, PROPERTY_ADDRESS, DISTRICT, CHARGE_RANK,
VALUATION_DATE, MARKET_VALUE_HKD, NET_REALIZABLE_VALUE_HKD, BAL_OUTSTD_HKD,
LTV, LTV_ON_NRV.
