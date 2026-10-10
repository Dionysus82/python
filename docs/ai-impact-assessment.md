# AI impact assessment template

This template is not an independent validation and not a regulatory filing.

| Item | Position in this prototype |
| --- | --- |
| Intended purpose | Help authorised users research and draft an evidence-grounded view of synthetic customers |
| Users affected | Synthetic staff roles only |
| Decisions automated | None. Scores are labelled demonstration calculations. Reports are drafts |
| Prohibited uses | See `config/governance.json` |
| Training data | No customer content is used to train a model. The hashing embedder is not a trained language model |
| Human oversight | High-impact text asks for human review. Report author and reviewer must differ |
| Quality measures | Evaluation cases for citation, abstention, contradiction and authorisation |
| Failure modes | A reader ignores the banner; a name is missed and the answer abstains; a demonstration score is mistaken for a rating |
| Kill switch | `ai_kill_switch` suppresses narrative commentary. Figures remain available |
| Fallback | The Customer 360 and dashboard do not need the composer |
| Residual risk | Recorded in governance configuration. Not accepted for production |

Formal model-risk and AI-governance review remains required.
