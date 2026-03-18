"""Extraction prompts for the Groq LLM."""

EXTRACTION_SYSTEM = """You are an expert at extracting engineering decisions from text.
An engineering decision is a deliberate choice made by a team about technology, architecture,
process, or tooling. It must be explicit — not implied or hypothetical.

You must respond with ONLY valid JSON matching the exact schema provided. No explanation, no markdown."""

EXTRACTION_HUMAN = """Analyse the following text and extract any engineering decision present.

TEXT:
{text}

SOURCE: {source_type} | {source_url}
AUTHOR: {author}
DATE HINT: {created_at}

Respond with this exact JSON schema:
{{
  "is_decision": true or false,
  "decision": "one sentence stating the decision, or empty string if none",
  "rationale": "2-3 sentences explaining why, or empty string if unclear",
  "decision_date": "ISO date string if mentioned, else empty string",
  "entities": ["list", "of", "services", "teams", "or", "technologies", "mentioned"],
  "confidence": 0.0 to 1.0
}}

Rules:
- Set is_decision=false if the text is just discussion, not a clear decision
- confidence < 0.5 means you are unsure it is actually a decision
- entities must be specific nouns (PostgreSQL, auth-service, platform team) not generic words
- Keep decision to one clear sentence
"""
