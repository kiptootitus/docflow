"""
QuickBooks Online integration with OAuth 2.0, CRUD operations for
invoices, customers, and real-time sync.
"""

import logging
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache

from .base import IntegrationBase, IntegrationType, IntegrationCredentials

logger = logging.getLogger(__name__)


class QuickBooksIntegration(IntegrationBase):
    """
    QuickBooks Online integration with full CRUD operations.
    """
    
    def __init__(self, company_id: int, credentials: Optional[IntegrationCredentials] = None):
        super().__init__(company_id, credentials)
        self.client_id = settings.QUICKBOOKS_CLIENT_ID
        self.client_secret = settings.QUICKBOOKS_CLIENT_SECRET
        self.redirect_uri = settings.QUICKBOOKS_REDIRECT_URI
        self.environment = settings.QUICKBOOKS_ENVIRONMENT  # 'sandbox' or 'production'
        
        if self.environment == 'sandbox':
            self.base_url = "https://sandbox-quickbooks.api.intuit.com"
            self.auth_url = "https://sandbox-accounts.platform.intuit.com"
        else:
            self.base_url = "https://quickbooks.api.intuit.com"
            self.auth_url = "https://accounts.platform.intuit.com"
    
    def get_integration_type(self) -> IntegrationType:
        return IntegrationType.QUICKBOOKS
    
    def get_rate_limit(self) -> int:
        return 250  # QuickBooks allows 250 requests per minute
    
    def get_rate_limit_window(self) -> int:
        return 60
    
    def get_authorization_url(self, state: str = None) -> str:
        """Get OAuth authorization URL."""
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "scope": "com.intuit.quickbooks.accounting",
            "redirect_uri": self.redirect_uri,
            "state": state or self._generate_state()
        }
        return f"{self.auth_url}/oauth2/v1/authorize?{urlencode(params)}"
    
    async def authenticate(self, code: str = None) -> bool:
        """Complete OAuth flow or validate existing credentials."""
        if code:
            return await self._exchange_code_for_tokens(code)
        elif self.credentials:
            return await self.test_connection() is not None
        return False
    
    async def _exchange_code_for_tokens(self, code: str) -> bool:
        """Exchange authorization code for access token."""
        import aiohttp
        
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri
        }
        
        auth = aiohttp.BasicAuth(self.client_id, self.client_secret)
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.auth_url}/oauth2/v1/token",
                data=data,
                auth=auth
            ) as response:
                if response.status == 200:
                    token_data = await response.json()
                    
                    self.credentials = IntegrationCredentials(
                        access_token=token_data["access_token"],
                        refresh_token=token_data.get("refresh_token"),
                        token_expiry=datetime.fromtimestamp(
                            token_data["expires_in"] + token_data["x_refresh_token_expires_in"]
                        ),
                        scopes=token_data.get("x_refresh_token_expires_in", [])
                    )
                    
                    await self._store_credentials()
                    return True
                else:
                    error = await response.text()
                    raise IntegrationAPIError(f"Token exchange failed: {error}")
    
    async def refresh_token(self) -> bool:
        """Refresh access token using refresh token."""
        import aiohttp
        
        if not self.credentials or not self.credentials.refresh_token:
            raise IntegrationAPIError("No refresh token available")
        
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.credentials.refresh_token
        }
        
        auth = aiohttp.BasicAuth(self.client_id, self.client_secret)
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.auth_url}/oauth2/v1/token",
                data=data,
                auth=auth
            ) as response:
                if response.status == 200:
                    token_data = await response.json()
                    
                    self.credentials.access_token = token_data["access_token"]
                    self.credentials.refresh_token = token_data.get("refresh_token")
                    self.credentials.token_expiry = datetime.fromtimestamp(
                        token_data["expires_in"] + token_data["x_refresh_token_expires_in"]
                    )
                    
                    await self._store_credentials()
                    return True
                    
                return False
    
    async def test_connection(self) -> Dict[str, Any]:
        """Test connection by fetching company info."""
        response = await self._make_request(
            "GET",
            f"{self.base_url}/v3/company/{self.company_id}/companyinfo/{self.company_id}"
        )
        return response.get("CompanyInfo", {})
    
    async def create_invoice(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create an invoice in QuickBooks.
        
        Args:
            invoice_data: Invoice data including customer, line items, etc.
        
        Returns:
            QuickBooks invoice response
        """
        # Transform DocFlow invoice to QuickBooks format
        qb_invoice = self._transform_invoice_to_qb(invoice_data)
        
        response = await self._make_request(
            "POST",
            f"{self.base_url}/v3/company/{self.company_id}/invoice",
            data=qb_invoice
        )
        
        return response.get("Invoice", {})
    
    async def get_invoice(self, invoice_id: str) -> Dict[str, Any]:
        """Get invoice from QuickBooks by ID."""
        response = await self._make_request(
            "GET",
            f"{self.base_url}/v3/company/{self.company_id}/invoice/{invoice_id}"
        )
        return response.get("Invoice", {})
    
    async def update_invoice(self, invoice_id: str, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update existing invoice in QuickBooks."""
        # Get current invoice for sync token
        current = await self.get_invoice(invoice_id)
        
        # Merge updates
        updated_data = self._transform_invoice_to_qb(invoice_data)
        updated_data["Id"] = invoice_id
        updated_data["SyncToken"] = current.get("SyncToken")
        
        response = await self._make_request(
            "POST",
            f"{self.base_url}/v3/company/{self.company_id}/invoice",
            data=updated_data
        )
        
        return response.get("Invoice", {})
    
    async def delete_invoice(self, invoice_id: str) -> bool:
        """Delete/void invoice in QuickBooks."""
        current = await self.get_invoice(invoice_id)
        
        void_data = {
            "Id": invoice_id,
            "SyncToken": current.get("SyncToken"),
            "status": "Voided"
        }
        
        response = await self._make_request(
            "POST",
            f"{self.base_url}/v3/company/{self.company_id}/invoice",
            data=void_data
        )
        
        return response.get("Invoice", {}).get("status") == "Voided"
    
    async def create_customer(self, customer_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create customer in QuickBooks."""
        qb_customer = self._transform_customer_to_qb(customer_data)
        
        response = await self._make_request(
            "POST",
            f"{self.base_url}/v3/company/{self.company_id}/customer",
            data=qb_customer
        )
        
        return response.get("Customer", {})
    
    async def get_customers(
        self,
        limit: int = 100,
        offset: int = 0,
        active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """Get customers from QuickBooks with pagination."""
        query = f"SELECT * FROM Customer"
        if active_only:
            query += " WHERE Active = true"
        query += f" ORDER BY Id DESC STARTPOSITION {offset} MAXRESULTS {limit}"
        
        response = await self._make_request(
            "GET",
            f"{self.base_url}/v3/company/{self.company_id}/query",
            data={"query": query}
        )
        
        return response.get("QueryResponse", {}).get("Customer", [])
    
    async def sync_invoices(
        self,
        last_sync_time: datetime = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Sync invoices changed after last_sync_time."""
        query = "SELECT * FROM Invoice"
        if last_sync_time:
            query += f" WHERE Metadata.LastUpdatedTime > '{last_sync_time.isoformat()}'"
        query += f" ORDER BY Metadata.LastUpdatedTime DESC MAXRESULTS {limit}"
        
        response = await self._make_request(
            "GET",
            f"{self.base_url}/v3/company/{self.company_id}/query",
            data={"query": query}
        )
        
        return response.get("QueryResponse", {}).get("Invoice", [])
    
    def _transform_invoice_to_qb(self, docflow_invoice: Dict[str, Any]) -> Dict[str, Any]:
        """Transform DocFlow invoice format to QuickBooks format."""
        line_items = []
        for item in docflow_invoice.get("line_items", []):
            line_items.append({
                "DetailType": "SalesItemLineDetail",
                "Amount": float(item.get("amount", 0)),
                "Description": item.get("description", ""),
                "SalesItemLineDetail": {
                    "ItemRef": {
                        "value": item.get("item_code", "1"),
                        "name": item.get("name", "Services")
                    },
                    "UnitPrice": float(item.get("unit_price", 0)),
                    "Qty": float(item.get("quantity", 1))
                }
            })
        
        return {
            "DocNumber": docflow_invoice.get("invoice_number", ""),
            "TxnDate": docflow_invoice.get("date", datetime.now().date().isoformat()),
            "Line": line_items,
            "CustomerRef": {
                "value": docflow_invoice.get("customer_id", ""),
                "name": docflow_invoice.get("customer_name", "")
            },
            "CustomerMemo": {
                "value": docflow_invoice.get("notes", "")
            },
            "TotalAmt": float(docflow_invoice.get("total_amount", 0)),
            "DueDate": docflow_invoice.get("due_date", ""),
            "Balance": float(docflow_invoice.get("balance_due", 0)),
            "CurrencyRef": {
                "value": docflow_invoice.get("currency", "USD")
            }
        }
    
    def _transform_customer_to_qb(self, docflow_customer: Dict[str, Any]) -> Dict[str, Any]:
        """Transform DocFlow customer format to QuickBooks format."""
        return {
            "DisplayName": docflow_customer.get("name", ""),
            "GivenName": docflow_customer.get("first_name", ""),
            "FamilyName": docflow_customer.get("last_name", ""),
            "PrimaryEmailAddr": {
                "Address": docflow_customer.get("email", "")
            },
            "PrimaryPhone": {
                "FreeFormNumber": docflow_customer.get("phone", "")
            },
            "BillAddr": {
                "Line1": docflow_customer.get("address_line1", ""),
                "Line2": docflow_customer.get("address_line2", ""),
                "City": docflow_customer.get("city", ""),
                "CountrySubDivisionCode": docflow_customer.get("state", ""),
                "PostalCode": docflow_customer.get("postal_code", ""),
                "Country": docflow_customer.get("country", "US")
            }
        }
    
    def _generate_state(self) -> str:
        """Generate random state for OAuth."""
        import secrets
        return secrets.token_urlsafe(32)
    
    async def _store_credentials(self):
        """Store credentials securely in database."""
        from .models import IntegrationConfig
        
        IntegrationConfig.objects.update_or_create(
            company_id=self.company_id,
            integration_type=self.get_integration_type().value,
            defaults={
                "credentials": {
                    "access_token": self.credentials.access_token,
                    "refresh_token": self.credentials.refresh_token,
                    "token_expiry": self.credentials.token_expiry.isoformat() if self.credentials.token_expiry else None,
                    "scopes": self.credentials.scopes
                },
                "is_active": True,
                "last_sync_at": datetime.now()
            }
        )