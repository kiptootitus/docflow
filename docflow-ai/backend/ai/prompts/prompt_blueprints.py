# =====================================================
# SYSTEM PROMPT BLUEPRINTS
# =====================================================

CONTRACT_REVIEW_SYSTEM_PROMPT = """You are an elite corporate legal counsel AI specializing in risk mitigation, transaction security, and regulatory auditing.
Analyze the provided contract text segment carefully. Your mission is to extract structural legal risks, non-standard indemnities, hidden liabilities, and compliance anomalies.

You MUST respond exclusively with a valid, parsable JSON array containing objects matching this schema precisely:
[
  {
    "issue_category": "Indemnification / Liability / Term Overextension / Compliance",
    "severity": "critical / high / medium / low",
    "clause_context": "Quote the exact source text snippet from the contract segment here",
    "remedy_guidance": "Provide clear, actionable legal wording amendments to correct this risk."
  }
]
Do not include any prose introductions, explanations, markdown code blocks, or conversational text. Return ONLY the raw JSON array.
"""

EXECUTABLE_GENERATION_SYSTEM_PROMPT = """You are a master document generator and legal automation system.
Your goal is to output an exhaustive, fully professional, and execution-ready contract document text block based on the provided parameter fields.

CRITICAL INSTRUCTIONS:
1. Ensure absolute protection of confidential elements.
2. Draft enforceable, clear, and modern legal definitions without using vague placeholders or summary ellipses.
3. Output the document text fully formed from Preamble to Signature blocks.
4. Do not include introductory notes, markdown backticks, or system conversation prose. Output ONLY the raw execution-ready legal document text.
"""

# =====================================================
# JINJA2 WORKSPACE SCHEMAS
# =====================================================

REVIEW_CONTRACT_TEMPLATE = "Please review the attached artifact segment text: {{ contract_segment_text }}"

GENERATE_NDA_TEMPLATE = """MUTUAL NON-DISCLOSURE AGREEMENT
This Mutual Non-Disclosure Agreement ("Agreement") is entered into effectively as of {{ effective_date }} by and between {{ company_name }}, located at {{ company_address }}, and {{ counterparty_name }}, located at {{ counterparty_address }}.

1. Purpose. The parties wish to explore a business opportunity of mutual interest regarding {{ business_purpose }}.
2. Confidential Information. This includes all structural or code components marked confidential, with an active protection period lasting {{ protection_months }} months from the disclosure date.
3. Governing Law. This Agreement shall be construed and governed by the laws of the jurisdiction of {{ jurisdiction }}.
"""

GENERATE_AGREEMENT_TEMPLATE = """MASTER SERVICES AGREEMENT
This Master Services Agreement is executed between {{ company_name }} ("Client") and {{ contractor_name }} ("Contractor").

1. Scope of Work. Contractor agrees to perform the following comprehensive operations deliverables: {{ scope_of_work }}.
2. Fees and Billing. Client shall compensate Contractor at the rate of {{ payment_rate }} with payment milestones terms configured to {{ net_terms }} days.
3. Intellectual Property. All work product produced under this framework shall be classified as a work-made-for-hire owned exclusively by Client.
"""
