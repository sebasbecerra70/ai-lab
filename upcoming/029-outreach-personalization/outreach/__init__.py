"""Outreach personalization: LLM-drafted prospect emails gated by a deterministic eval suite."""
from .drafting import SYSTEM, Draft, build_prompt, draft_email, parse_email
from .evals import Check, failures, personalization_tokens, run_checks
from .llm import AnthropicClient, LLMClient, MockLLM, pick_proof

__all__ = ["SYSTEM", "AnthropicClient", "Check", "Draft", "LLMClient", "MockLLM", "build_prompt", "draft_email",
           "failures", "parse_email", "personalization_tokens", "pick_proof", "run_checks"]
