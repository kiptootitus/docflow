"""AI Service Layer — abstracts LLM provider (Claude primary, GPT-4 fallback)"""
import json
import logging
from typing import Optional
from django.conf import settings

logger = logging.getLogger(__name__)

CONTRACT_REVIEW_PROMPT = """You are a legal document analyst. Review the following contract text and identify:
1. Legal risks or problematic clauses
2. Missing standard clauses
3. Compliance issues
4. Suggestions for improvement

Return a JSON array of findings with this exact structure:
[
  {
    "type": "risk|suggestion|compliant|note",
    "severity": "high|medium|low",
    "title": "Short title",
    "description": "Detailed explanation",
    "clause_reference": "Section X.X (if applicable)",
    "recommendation": "What to do about it"
  }
]

Return ONLY the JSON array, no other text.

Contract text:
{text}"""

DOCUMENT_GENERATION_PROMPTS = {
    "nda": """Generate a professional Non-Disclosure Agreement with the following details:
Party A (Disclosing): {party_a}
Party B (Receiving): {party_b}
Effective Date: {effective_date}
Duration: {duration}
Jurisdiction: {jurisdiction}
Purpose: {purpose}

Generate a complete, legally sound NDA in plain text format suitable for immediate use.""",

    "service": """Generate a Professional Services Agreement with:
Service Provider: {provider_name}
Client: {client_name}
Services: {services_description}
Start Date: {start_date}
End Date: {end_date}
Payment: {payment_terms}
Jurisdiction: {jurisdiction}

Include sections for: Scope of Work, Payment Terms, IP ownership, Confidentiality, Termination, Dispute Resolution.""",

    "freelance": """Generate a Freelance Contract with:
Freelancer: {freelancer_name}
Client: {client_name}
Project: {project_description}
Rate: {rate}
Estimated Duration: {duration}
Deliverables: {deliverables}
Jurisdiction: {jurisdiction}

Include standard freelance contract sections.""",
}


class AIProvider:
    """Abstract AI provider — Claude primary, OpenAI fallback."""

    def __init__(self):
        self.anthropic_key = settings.ANTHROPIC_API_KEY
        self.openai_key = settings.OPENAI_API_KEY
        self.primary_model = settings.AI_MODEL_PRIMARY

    def review_contract(self, text: str) -> dict:
        """Review contract text and return structured findings."""
        prompt = CONTRACT_REVIEW_PROMPT.format(text=text[:15000])  # Limit context

        try:
            result = self._call_anthropic(prompt)
            findings = json.loads(result["content"])
            return {"findings": findings, "model": result["model"], "tokens": result["tokens"]}
        except Exception as e:
            logger.warning(f"Claude failed, trying OpenAI: {e}")
            try:
                result = self._call_openai(prompt)
                findings = json.loads(result["content"])
                return {"findings": findings, "model": result["model"], "tokens": result["tokens"]}
            except Exception as e2:
                logger.error(f"Both AI providers failed: {e2}")
                raise

    def generate_document(self, doc_type: str, fields: dict) -> dict:
        """Generate a document from a template and fields."""
        template = DOCUMENT_GENERATION_PROMPTS.get(doc_type)
        if not template:
            raise ValueError(f"Unknown document type: {doc_type}")

        try:
            prompt = template.format(**fields)
        except KeyError as e:
            raise ValueError(f"Missing required field: {e}")

        try:
            result = self._call_anthropic(prompt, max_tokens=4000)
            return {"content": result["content"], "model": result["model"], "tokens": result["tokens"]}
        except Exception as e:
            logger.warning(f"Claude failed: {e}")
            result = self._call_openai(prompt, max_tokens=4000)
            return {"content": result["content"], "model": result["model"], "tokens": result["tokens"]}

    def _call_anthropic(self, prompt: str, max_tokens: int = 2000) -> dict:
        import anthropic
        client = anthropic.Anthropic(api_key=self.anthropic_key)
        response = client.messages.create(
            model=self.primary_model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return {
            "content": response.content[0].text,
            "model": response.model,
            "tokens": response.usage.input_tokens + response.usage.output_tokens,
        }

    def _call_openai(self, prompt: str, max_tokens: int = 2000) -> dict:
        from openai import OpenAI
        client = OpenAI(api_key=self.openai_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return {
            "content": response.choices[0].message.content,
            "model": response.model,
            "tokens": response.usage.total_tokens,
        }


# Singleton
ai_provider = AIProvider()
