"""
Google Drive integration for storing and syncing PDFs, invoices,
and contracts with folder management and sharing.
"""

import logging
import io
from datetime import datetime
from typing import Dict, Any, List, Optional, BinaryIO

from django.conf import settings
from django.core.files.base import ContentFile

from .base import IntegrationBase, IntegrationType, IntegrationCredentials

logger = logging.getLogger(__name__)


class GoogleDriveIntegration(IntegrationBase):
    """
    Google Drive integration for file storage and management.
    """
    
    def __init__(self, company_id: int, credentials: Optional[IntegrationCredentials] = None):
        super().__init__(company_id, credentials)
        self.scopes = [
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/drive.metadata"
        ]
        
        self.base_url = "https://www.googleapis.com/drive/v3"
    
    def get_integration_type(self) -> IntegrationType:
        return IntegrationType.GOOGLE_DRIVE
    
    def get_rate_limit(self) -> int:
        return 1000  # Google Drive has high rate limits
    
    def get_rate_limit_window(self) -> int:
        return 60
    
    async def authenticate(self) -> bool:
        """Authenticate with Google Drive."""
        if self.credentials and self.credentials.access_token:
            return await self.test_connection() is not None
        return False
    
    async def refresh_token(self) -> bool:
        """Refresh Google access token."""
        import aiohttp
        
        if not self.credentials or not self.credentials.refresh_token:
            raise IntegrationAPIError("No refresh token available")
        
        data = {
            "client_id": settings.GOOGLE_DRIVE_CLIENT_ID,
            "client_secret": settings.GOOGLE_DRIVE_CLIENT_SECRET,
            "refresh_token": self.credentials.refresh_token,
            "grant_type": "refresh_token"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://oauth2.googleapis.com/token",
                data=data
            ) as response:
                if response.status == 200:
                    token_data = await response.json()
                    
                    self.credentials.access_token = token_data["access_token"]
                    if token_data.get("expires_in"):
                        self.credentials.token_expiry = datetime.fromtimestamp(
                            token_data["expires_in"]
                        )
                    
                    await self._store_credentials()
                    return True
                    
                return False
    
    async def test_connection(self) -> Dict[str, Any]:
        """Test connection by fetching about info."""
        response = await self._make_request(
            "GET",
            f"{self.base_url}/about?fields=user,storageQuota"
        )
        return response
    
    async def create_folder(
        self,
        name: str,
        parent_folder_id: str = None
    ) -> Dict[str, Any]:
        """Create a folder in Google Drive."""
        
        metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder"
        }
        
        if parent_folder_id:
            metadata["parents"] = [parent_folder_id]
        
        response = await self._make_request(
            "POST",
            f"{self.base_url}/files",
            data=metadata
        )
        
        return response
    
    async def upload_file(
        self,
        file_name: str,
        file_content: bytes,
        mime_type: str,
        folder_id: str = None,
        description: str = None
    ) -> Dict[str, Any]:
        """Upload a file to Google Drive."""
        
        # Use multipart upload for metadata + file
        import aiohttp
        
        boundary = '---boundary---'
        
        # Prepare metadata
        metadata = {
            "name": file_name,
            "mimeType": mime_type
        }
        
        if folder_id:
            metadata["parents"] = [folder_id]
        
        if description:
            metadata["description"] = description
        
        # Create multipart body
        body = io.BytesIO()
        body.write(f'--{boundary}\r\n'.encode())
        body.write(b'Content-Type: application/json; charset=UTF-8\r\n\r\n')
        body.write(json.dumps(metadata).encode())
        body.write(f'\r\n--{boundary}\r\n'.encode())
        body.write(f'Content-Type: {mime_type}\r\n\r\n'.encode())
        body.write(file_content)
        body.write(f'\r\n--{boundary}--\r\n'.encode())
        
        headers = {
            "Content-Type": f"multipart/related; boundary={boundary}"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/files?uploadType=multipart",
                headers=headers,
                data=body.getvalue()
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error = await response.text()
                    raise IntegrationAPIError(f"Upload failed: {error}")
    
    async def upload_invoice_pdf(
        self,
        invoice_number: str,
        pdf_content: bytes,
        customer_name: str,
        invoice_date: str,
        company_folder_id: str = None
    ) -> Dict[str, Any]:
        """
        Upload an invoice PDF to Google Drive with proper organization.
        
        Args:
            invoice_number: Invoice number for filename
            pdf_content: PDF file content
            customer_name: Customer name for folder organization
            invoice_date: Invoice date for naming
            company_folder_id: Parent folder ID
        """
        
        # Create or get invoices folder
        invoices_folder = await self._get_or_create_folder(
            "Invoices",
            company_folder_id
        )
        
        # Create customer subfolder
        customer_folder = await self._get_or_create_folder(
            customer_name,
            invoices_folder.get("id")
        )
        
        # Upload file
        file_name = f"Invoice_{invoice_number}_{invoice_date}.pdf"
        
        result = await self.upload_file(
            file_name=file_name,
            file_content=pdf_content,
            mime_type="application/pdf",
            folder_id=customer_folder.get("id"),
            description=f"Invoice {invoice_number} for {customer_name}"
        )
        
        # Set sharing to anyone with link can view (optional)
        await self._set_file_permissions(
            result["id"],
            "anyoneWithLink",
            "reader"
        )
        
        return result
    
    async def upload_contract_pdf(
        self,
        contract_name: str,
        pdf_content: bytes,
        client_name: str,
        company_folder_id: str = None
    ) -> Dict[str, Any]:
        """Upload a contract PDF to Google Drive."""
        
        # Create or get contracts folder
        contracts_folder = await self._get_or_create_folder(
            "Contracts",
            company_folder_id
        )
        
        # Create client subfolder
        client_folder = await self._get_or_create_folder(
            client_name,
            contracts_folder.get("id")
        )
        
        # Upload file
        file_name = f"Contract_{contract_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
        
        result = await self.upload_file(
            file_name=file_name,
            file_content=pdf_content,
            mime_type="application/pdf",
            folder_id=client_folder.get("id"),
            description=f"Contract: {contract_name} for {client_name}"
        )
        
        return result
    
    async def download_file(self, file_id: str) -> bytes:
        """Download a file from Google Drive."""
        response = await self._make_request(
            "GET",
            f"{self.base_url}/files/{file_id}?alt=media"
        )
        
        # For binary content, we need to handle differently
        import aiohttp
        
        headers = self._get_request_headers()
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/files/{file_id}?alt=media",
                headers=headers
            ) as response:
                if response.status == 200:
                    return await response.read()
                else:
                    error = await response.text()
                    raise IntegrationAPIError(f"Download failed: {error}")
    
    async def list_files(
        self,
        folder_id: str = None,
        mime_type: str = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List files in a folder."""
        
        query_parts = []
        
        if folder_id:
            query_parts.append(f"'{folder_id}' in parents")
        
        if mime_type:
            query_parts.append(f"mimeType = '{mime_type}'")
        
        query = " and ".join(query_parts) if query_parts else ""
        
        url = f"{self.base_url}/files?pageSize={limit}"
        if query:
            url += f"&q={query}"
        
        response = await self._make_request("GET", url)
        
        return response.get("files", [])
    
    async def delete_file(self, file_id: str) -> bool:
        """Delete a file from Google Drive."""
        await self._make_request(
            "DELETE",
            f"{self.base_url}/files/{file_id}"
        )
        return True
    
    async def share_file(
        self,
        file_id: str,
        email: str,
        role: str = "reader"
    ) -> Dict[str, Any]:
        """Share a file with a specific user."""
        
        permission = {
            "type": "user",
            "role": role,
            "emailAddress": email
        }
        
        response = await self._make_request(
            "POST",
            f"{self.base_url}/files/{file_id}/permissions",
            data=permission
        )
        
        return response
    
    async def get_shareable_link(self, file_id: str) -> str:
        """Get shareable link for a file."""
        
        # First ensure file is shareable
        await self._set_file_permissions(file_id, "anyoneWithLink", "reader")
        
        response = await self._make_request(
            "GET",
            f"{self.base_url}/files/{file_id}?fields=webViewLink"
        )
        
        return response.get("webViewLink")
    
    async def search_files(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Search for files by name or content."""
        
        url = f"{self.base_url}/files?q=name contains '{query}'&pageSize={limit}"
        
        response = await self._make_request("GET", url)
        
        return response.get("files", [])
    
    async def _get_or_create_folder(
        self,
        folder_name: str,
        parent_id: str = None
    ) -> Dict[str, Any]:
        """Get existing folder or create new one."""
        
        # Search for existing folder
        query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder'"
        if parent_id:
            query += f" and '{parent_id}' in parents"
        
        url = f"{self.base_url}/files?q={query}&pageSize=1"
        
        response = await self._make_request("GET", url)
        files = response.get("files", [])
        
        if files:
            return files[0]
        else:
            return await self.create_folder(folder_name, parent_id)
    
    async def _set_file_permissions(
        self,
        file_id: str,
        permission_type: str,
        role: str
    ):
        """Set file permissions."""
        
        permission = {
            "type": permission_type,
            "role": role
        }
        
        await self._make_request(
            "POST",
            f"{self.base_url}/files/{file_id}/permissions",
            data=permission
        )
    
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
                    "scopes": self.credentials.scopes
                },
                "is_active": True,
                "last_sync_at": datetime.now()
            }
        )