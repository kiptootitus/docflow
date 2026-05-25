"""AI Service Layer — abstracts LLM provider (Claude primary, GPT-4 fallback)"""
import json
import logging
from typing import Optional
from django.conf import settings

logger = logging.getLogger(__name__)

# Core Business Automation Prompts
CONTRACT_REVIEW_PROMPT = """You are an automated document parsing engine. Review the text or document schema and identify standard parameters.
Return a JSON object matching this exact structure:
{{
  "findings": [
    {{
      "type": "risk|suggestion|compliant|note",
      "severity": "high|medium|low",
      "title": "Short title",
      "description": "Detailed explanation",
      "clause_reference": "Section reference",
      "recommendation": "Suggested action"
    }}
  ],
  "extracted_company_name": "",
  "extracted_company_address": "",
  "extracted_company_city": "",
  "extracted_company_location_number": "",
  "extracted_salutation": "Mr.",
  "extracted_client_name": "",
  "extracted_currency": "KES",
  "extracted_items": []
}}
Return ONLY valid JSON matching this schema, no extra chat text.

Document Text:
{text}"""

DOCUMENT_EXTRACTION_PROMPT = """You are an AI document builder. Analyze the text payload and execute user instructions: {instructions}

Isolate pricing structures, corporate entities, identifiers, logos, descriptions, and line entries.
Return a JSON object with this structure:
{{
  "findings": [
    {{
      "type": "note",
      "severity": "low",
      "title": "AI Extraction Successful",
      "description": "Processed text structure for direct document configuration."
    }}
  ],
  "extracted_company_name": "Name of the issuing company or seller entity",
  "extracted_company_address": "Street address or postal box details",
  "extracted_company_city": "City name",
  "extracted_company_location_number": "Phone number or registration/location number",
  "extracted_salutation": "Mr.|Mrs.|Ms.|Dr.|Prof.|Messrs.",
  "extracted_client_name": "Target buyer name or client entity representative",
  "extracted_currency": "Three-letter currency code (e.g., KES, USD, EUR, GBP)",
  "extracted_items": [
    {{
      "description": "Detailed task description line item breakdown text",
      "quantity": 1,
      "unit_price": 0.00
    }}
  ]
}}

Return ONLY the raw JSON object, no introductory or conversational prose.

Document Text:
{text}"""


class AIProvider:
    """Abstract AI provider — Claude primary, OpenAI fallback."""

    def __init__(self):
        self.anthropic_key = settings.ANTHROPIC_API_KEY
        self.openai_key = settings.OPENAI_API_KEY
        self.primary_model = settings.AI_MODEL_PRIMARY

    def review_contract(self, text: str, instructions: Optional[str] = None) -> dict:
        """Review text context streams or extract direct commercial entities using user directives."""
        if instructions and any(kw in instructions.lower() for kw in ["quote", "quotation", "invoice", "extract", "billing", "generate"]):
            prompt = DOCUMENT_EXTRACTION_PROMPT.format(instructions=instructions, text=text[:15000])
        else:
            prompt = CONTRACT_REVIEW_PROMPT.format(text=text[:15000])

        try:
            result = self._call_anthropic(prompt)
            data = json.loads(result["content"])
        except Exception as e:
            logger.warning(f"Claude fallback engine activated: {e}")
            try:
                result = self._call_openai(prompt)
                data = json.loads(result["content"])
            except Exception as e2:
                logger.error(f"AI Extraction processing failed: {e2}")
                raise

        return {
            "findings": data.get("findings", []),
            "extracted_company_name": data.get("extracted_company_name", ""),
            "extracted_company_address": data.get("extracted_company_address", ""),
            "extracted_company_city": data.get("extracted_company_city", ""),
            "extracted_company_location_number": data.get("extracted_company_location_number", ""),
            "extracted_salutation": data.get("extracted_salutation", "Mr."),
            "extracted_client_name": data.get("extracted_client_name", ""),
            "extracted_currency": data.get("extracted_currency", "KES"),
            "extracted_items": data.get("extracted_items", []),
            "model": result["model"],
            "tokens": result["tokens"]
        }

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
            max_digits=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return {
            "content": response.choices[0].message.content,
            "model": response.model,
            "tokens": response.usage.total_tokens,
        }


ai_provider = AIProvider()