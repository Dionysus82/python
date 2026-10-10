# Risk taxonomy

The taxonomy is configured in `config/risk_taxonomy.json` and stored in `risk_taxonomy`. The UI reads it from the database.

| Code | Name | Owner |
| --- | --- | --- |
| credit | Credit risk | Credit Risk |
| counterparty_credit | Counterparty credit risk | Market Risk |
| market | Market risk | Market Risk |
| interest_rate | Interest-rate risk | Treasury |
| liquidity | Liquidity risk | Liquidity Risk Management |
| operational | Operational risk | Operational Risk |
| technology | Technology risk | Operational Risk |
| cyber | Cyber risk | Operational Risk |
| concentration | Concentration risk | Enterprise Risk |
| country | Country risk | Enterprise Risk |
| industry | Industry risk | Credit Risk |
| collateral | Collateral risk | Collateral Management |
| legal | Legal risk | Legal |
| reputation | Reputation risk | Enterprise Risk |
| strategic | Strategic risk | Corporate Banking |
| climate | Climate risk | Enterprise Risk |
| model | Model risk | Model Risk |
| data | Data risk | Data Governance |
| aml | AML risk | Financial Crime Compliance |
| terrorist_financing | Terrorist-financing risk | Financial Crime Compliance |
| proliferation_financing | Proliferation-financing risk | Financial Crime Compliance |
| sanctions | Sanctions risk | Financial Crime Compliance |
| fraud | Fraud risk | Financial Crime Compliance |
| conduct | Conduct risk | Enterprise Risk |

Descriptions are in the configuration file. The score weights are separate and live in `config/risk_score.json`.
