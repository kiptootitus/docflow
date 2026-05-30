"""
Xero accounting integration with OAuth 2.0, invoices, contacts,
and bank transactions.
"""

import logging
import hashlib
import base64
from datetime import datetime
from typing import Dict, Any, List, Optional
from urllib.parse import urlencode

from django.conf import settings

from .base import IntegrationBase, IntegrationType, IntegrationCredentials

logger = logging.getLogger(__name__)


class XeroIntegration(IntegrationBase):
    """
    Xero accounting integration with full API support.
    """
    
    def __init__(self, company_id: int, credentials: Optional[IntegrationCredentials] = None):
        super().__init__(company_id, credentials)
        self.client_id = settings.XERO_CLIENT_ID
        self.client_secret = settings.XERO_CLIENT_SECRET
        self.redirect_uri = settings.XERO_REDIRECT_URI
        self.tenant_id = None  # Will be set after authentication
        
        self.base_url = "https://api.xero.com/api.xro/2.0"
        self.auth_url = "https://login.xero.com"
    
    def get_integration_type(self) -> IntegrationType:
        return IntegrationType.XERO
    
    def get_rate_limit(self) -> int:
        return 60  # Xero allows 60 requests per minute
    
    def get_rate_limit_window(self) -> int:
        return 60
    
    def get_authorization_url(self, state: str = None) -> str:
        """Get OAuth authorization URL."""
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "scope": "openid profile email accounting.transactions accounting.contacts accounting.settings offline_access",
            "redirect_uri": self.redirect_uri,
            "state": state or self._generate_state()
        }
        return f"{self.auth_url}/identity/connect/authorize?{urlencode(params)}"
    
    async def authenticate(self, code: str = None) -> bool:
        """Authenticate with Xero."""
        if code:
            return await self._exchange_code_for_tokens(code)
        elif self.credentials:
            # Get tenant ID
            await self._get_tenants()
            return await self.test_connection() is not None
        return False
    
    async def _exchange_code_for_tokens(self, code: str) -> bool:
        """Exchange authorization code for tokens."""
        import aiohttp
        
        # Encode client credentials for Basic Auth
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://identity.xero.com/connect/token",
                headers=headers,
                data=data
            ) as response:
                if response.status == 200:
                    token_data = await response.json()
                    
                    self.credentials = IntegrationCredentials(
                        access_token=token_data["access_token"],
                        refresh_token=token_data.get("refresh_token"),
                        token_expiry=datetime.fromtimestamp(
                            token_data["expires_in"]
                        ),
                        scopes=token_data.get("scope", "").split(" ")
                    )
                    
                    await self._store_credentials()
                    await self._get_tenants()
                    return True
                else:
                    error = await response.text()
                    raise IntegrationAPIError(f"Token exchange failed: {error}")
    
    async def _get_tenants(self):
        """Get connected Xero tenants (organizations)."""
        import aiohttp
        
        headers = {
            "Authorization": f"Bearer {self.credentials.access_token}",
            "Accept": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.xero.com/connections",
                headers=headers
            ) as response:
                if response.status == 200:
                    tenants = await response.json()
                    if tenants:
                        # Use first tenant
                        self.tenant_id = tenants[0]["tenantId"]
                else:
                    error = await response.text()
                    logger.error(f"Failed to get tenants: {error}")
    
    async def refresh_token(self) -> bool:
        """Refresh access token."""
        import aiohttp
        
        if not self.credentials or not self.credentials.refresh_token:
            raise IntegrationAPIError("No refresh token available")
        
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.credentials.refresh_token
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://identity.xero.com/connect/token",
                headers=headers,
                data=data
            ) as response:
                if response.status == 200:
                    token_data = await response.json()
                    
                    self.credentials.access_token = token_data["access_token"]
                    self.credentials.refresh_token = token_data.get("refresh_token")
                    self.credentials.token_expiry = datetime.fromtimestamp(
                        token_data["expires_in"]
                    )
                    
                    await self._store_credentials()
                    return True
                    
                return False
    
    async def test_connection(self) -> Dict[str, Any]:
        """Test connection by getting organization info."""
        if not self.tenant_id:
            await self._get_tenants()
        
        response = await self._make_request(
            "GET",
            f"{self.base_url}/Organisation",
            headers={"Xero-tenant-id": self.tenant_id}
        )
        
        orgs = response.get("Organisations", [])
        return orgs[0] if orgs else {}
    
    async def create_invoice(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create invoice in Xero."""
        xero_invoice = self._transform_invoice_to_xero(invoice_data)
        
        response = await self._make_request(
            "POST",
            f"{self.base_url}/Invoices",
            data={"Invoices": [xero_invoice]},
            headers={"Xero-tenant-id": self.tenant_id}
        )
        
        invoices = response.get("Invoices", [])
        return invoices[0] if invoices else {}
    
    async def get_invoice(self, invoice_id: str) -> Dict[str, Any]:
        """Get invoice from Xero by ID."""
        response = await self._make_request(
            "GET",
            f"{self.base_url}/Invoices/{invoice_id}",
            headers={"Xero-tenant-id": self.tenant_id}
        )
        
        invoices = response.get("Invoices", [])
        return invoices[0] if invoices else {}
    
    async def update_invoice(self, invoice_id: str, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update invoice in Xero."""
        current = await self.get_invoice(invoice_id)
        
        xero_invoice = self._transform_invoice_to_xero(invoice_data)
        xero_invoice["InvoiceID"] = invoice_id
        xero_invoice["Version"] = current.get("Version", 0)
        
        response = await self._make_request(
            "POST",
            f"{self.base_url}/Invoices",
            data={"Invoices": [xero_invoice]},
            headers={"Xero-tenant-id": self.tenant_id}
        )
        
        invoices = response.get("Invoices", [])
        return invoices[0] if invoices else {}
    
    async def delete_invoice(self, invoice_id: str) -> bool:
        """Delete/void invoice in Xero."""
        # Xero requires status update to DELETE
        response = await self._make_request(
            "POST",
            f"{self.base_url}/Invoices/{invoice_id}",
            data={"Status": "DELETED"},
            headers={"Xero-tenant-id": self.tenant_id}
        )
        
        invoices = response.get("Invoices", [])
        return invoices and invoices[0].get("Status") == "DELETED"
    
    async def create_contact(self, contact_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create contact in Xero."""
        xero_contact = self._transform_contact_to_xero(contact_data)
        
        response = await self._make_request(
            "POST",
            f"{self.base_url}/Contacts",
            data={"Contacts": [xero_contact]},
            headers={"Xero-tenant-id": self.tenant_id}
        )
        
        contacts = response.get("Contacts", [])
        return contacts[0] if contacts else {}
    
    async def get_contacts(
        self,
        limit: int = 100,
        offset: int = 0,
        where: str = None
    ) -> List[Dict[str, Any]]:
        """Get contacts from Xero."""
        url = f"{self.base_url}/Contacts?page={offset // limit + 1}"
        if where:
            url += f"&where={where}"
        
        response = await self._make_request(
            "GET",
            url,
            headers={"Xero-tenant-id": self.tenant_id}
        )
        
        return response.get("Contacts", [])
    
    async def create_bank_transaction(self, transaction_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create bank transaction (payment) in Xero."""
        xero_transaction = self._transform_transaction_to_xero(transaction_data)
        
        response = await self._make_request(
            "POST",
            f"{self.base_url}/BankTransactions",
            data={"BankTransactions": [xero_transaction]},
            headers={"Xero-tenant-id": self.tenant_id}
        )
        
        transactions = response.get("BankTransactions", [])
        return transactions[0] if transactions else {}
    
    async def sync_invoices(
        self,
        last_sync_time: datetime = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Sync invoices changed after last_sync_time."""
        url = f"{self.base_url}/Invoices"
        if last_sync_time:
            url += f"?modifiedAfter={last_sync_time.isoformat()}"
        
        response = await self._make_request(
            "GET",
            url,
            headers={"Xero-tenant-id": self.tenant_id}
        )
        
        return response.get("Invoices", [])
    
    def _transform_invoice_to_xero(self, docflow_invoice: Dict[str, Any]) -> Dict[str, Any]:
        """Transform DocFlow invoice to Xero format."""
        line_items = []
        for item in docflow_invoice.get("line_items", []):
            line_items.append({
                "Description": item.get("description", ""),
                "Quantity": float(item.get("quantity", 1)),
                "UnitAmount": float(item.get("unit_price", 0)),
                "AccountCode": item.get("account_code", "200"),
                "TaxType": "OUTPUT",
                "LineAmount": float(item.get("amount", 0))
            })
        
        return {
            "Type": "ACCREC",  # Accounts Receivable
            "Contact": {
                "ContactID": docflow_invoice.get("contact_id", ""),
                "Name": docflow_invoice.get("customer_name", "")
            },
            "Date": docflow_invoice.get("date", datetime.now().date().isoformat()),
            "DueDate": docflow_invoice.get("due_date", ""),
            "InvoiceNumber": docflow_invoice.get("invoice_number", ""),
            "Reference": docflow_invoice.get("reference", ""),
            "LineItems": line_items,
            "Status": "AUTHORISED",
            "CurrencyCode": docflow_invoice.get("currency", "USD"),
            "Total": float(docflow_invoice.get("total_amount", 0)),
            "AmountDue": float(docflow_invoice.get("balance_due", 0))
        }
    
    def _transform_contact_to_xero(self, docflow_contact: Dict[str, Any]) -> Dict[str, Any]:
        """Transform DocFlow contact to Xero format."""
        return {
            "Name": docflow_contact.get("name", ""),
            "FirstName": docflow_contact.get("first_name", ""),
            "LastName": docflow_contact.get("last_name", ""),
            "EmailAddress": docflow_contact.get("email", ""),
            "PhoneNumber": docflow_contact.get("phone", ""),
            "Addresses": [{
                "AddressType": "STREET",
                "AddressLine1": docflow_contact.get("address_line1", ""),
                "AddressLine2": docflow_contact.get("address_line2", ""),
                "City": docflow_contact.get("city", ""),
                "Region": docflow_contact.get("state", ""),
                "PostalCode": docflow_contact.get("postal_code", ""),
                "Country": docflow_contact.get("country", "US")
            }]
        }
    
    def _transform_transaction_to_xero(self, docflow_transaction: Dict[str, Any]) -> Dict[str, Any]:
        """Transform DocFlow transaction to Xero bank transaction."""
        return {
            "Type": "RECEIVE",
            "BankAccount": {
                "Code": docflow_transaction.get("bank_account_code", "090")
            },
            "Contact": {
                "ContactID": docflow_transaction.get("contact_id", "")
            },
            "Date": docflow_transaction.get("date", datetime.now().date().isoformat()),
            "Reference": docflow_transaction.get("reference", f"Payment for Invoice {docflow_transaction.get('invoice_number', '')}"),
            "LineItems": [{
                "Description": f"Payment for {docflow_transaction.get('invoice_number', 'invoice')}",
                "Quantity": 1,
                "UnitAmount": float(docflow_transaction.get("amount", 0)),
                "AccountCode": "200"  # Sales revenue account
            }]
        }
    
    def _generate_state(self) -> str:
        """Generate random state for OAuth."""
        import secrets
        return secrets.token_urlsafe(32)
    
    async def _store_credentials(self):
        """Store credentials securely."""
        from .models import IntegrationConfig
        
        IntegrationConfig.objects.update_or_create(
            company_id=self.company_id,
            integration_type=self.get_integration_type().value,
            defaults={
                "credentials": {
                    "access_token": self.credentials.access_token,
                    "refresh_token": self.credentials.refresh_token,
                    "token_expiry": self.credentials.token_expiry.isoformat() if self.credentials.token_expiry else None,
                    "scopes": self.credentials.scopes,
                    "tenant_id": self.tenant_id
                },
                "is_active": True,
                "last_sync_at": datetime.now()
            }
        )