from typing import List, Dict, Any
from .models import Contract, ComplianceRule, ComplianceAlert

class JurisdictionComplianceMatcher:
    """
    Evaluates contract attributes against active legislative compliance rules 
    and issues tenant operations warnings.
    """
    def __init__(self, contract: Contract):
        self.contract = contract

    def audit_against_active_rules(self) -> List[ComplianceAlert]:
        triggered_alerts: List[ComplianceAlert] = []
        
        # Query active rules for this tenant's region
        applicable_rules = ComplianceRule.objects.filter(
            company=self.contract.company,
            active=True
        )

        contract_metadata = self.contract.metadata or {}
        contract_tags = [tag.lower() for tag in (self.contract.tags or [])]

        for rule in applicable_rules:
            rule_config: Dict[str, Any] = rule.configuration or {}
            target_keyword = rule_config.get("mandatory_keyword", "").lower()
            maximum_allowed_term = rule_config.get("max_term_months", 0)

            # Rule Check 1: Mandatory clause terms evaluation
            if target_keyword and target_keyword not in str(self.contract.title).lower():
                # Verify cross-referenced inner clause data segments
                text_match_found = any(target_keyword in str(c.content).lower() for c in self.contract.clauses.all())
                if not text_match_found:
                    alert = ComplianceAlert.objects.create(
                        company=self.contract.company,
                        contract=self.contract,
                        rule=rule,
                        severity=ComplianceAlert.Severity.HIGH,
                        description=f"Compliance Breach: Missing required language parameters for item: '{target_keyword}'."
                    )
                    triggered_alerts.append(alert)

            # Rule Check 2: Expiry timeline constraint validation
            if maximum_allowed_term and self.contract.effective_date and self.contract.expiry_date:
                delta_days = (self.contract.expiry_date - self.contract.effective_date).days
                approximate_months = delta_days / 30.44
                if approximate_months > maximum_allowed_term:
                    alert = ComplianceAlert.objects.create(
                        company=self.contract.company,
                        contract=self.contract,
                        rule=rule,
                        severity=ComplianceAlert.Severity.MEDIUM,
                        description=f"Duration warning: Active parameters [{int(approximate_months)} months] exceed maximum threshold values [{maximum_allowed_term} months]."
                    )
                    triggered_alerts.append(alert)

        return triggered_alerts