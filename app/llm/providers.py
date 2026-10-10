"""Provider-neutral language-model boundary. The default profile calls nobody."""

from __future__ import annotations

import re

from app.domain.errors import LLMDisabledError

NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


class DisabledLLM:
    provider_name = "disabled"

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        raise LLMDisabledError(
            "External language models are disabled. The deterministic composer is the local path."
        )


class GuardedCommentary:
    """Optional model text is kept only when it adds no new numbers or customer identifiers."""

    def __init__(self, provider: DisabledLLM) -> None:
        self.provider = provider

    def comment(
        self,
        *,
        enabled: bool,
        kill_switch: bool,
        system_prompt: str,
        evidence_text: str,
        allowed_customer_ids: set[str],
    ) -> str | None:
        if kill_switch or not enabled:
            return None
        raw = self.provider.complete(system_prompt, evidence_text)
        evidence_numbers = set(NUMBER.findall(evidence_text))
        for number in NUMBER.findall(raw):
            if number not in evidence_numbers:
                return None
        for customer_id in re.findall(r"CUS-[A-Z0-9-]+", raw):
            if customer_id not in allowed_customer_ids:
                return None
        return raw.strip()
