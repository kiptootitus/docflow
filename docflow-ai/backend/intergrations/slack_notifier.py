"""
Slack integration for real-time notifications with rich formatting,
message blocks, and interactive components.
"""

import logging
from typing import Dict, Any, List, Optional
from enum import Enum

from django.conf import settings

from .base import IntegrationBase, IntegrationType, IntegrationCredentials

logger = logging.getLogger(__name__)


class SlackMessageType(Enum):
    """Types of Slack messages."""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class SlackIntegration(IntegrationBase):
    """
    Slack integration for sending notifications and alerts.
    """
    
    def __init__(self, company_id: int, credentials: Optional[IntegrationCredentials] = None):
        super().__init__(company_id, credentials)
        self.bot_token = None
        self.default_channel = None
        
        if credentials:
            self.bot_token = credentials.access_token
            self.default_channel = credentials.additional_data.get("default_channel", "#general")
    
    def get_integration_type(self) -> IntegrationType:
        return IntegrationType.SLACK
    
    def get_rate_limit(self) -> int:
        return 50  # Slack's rate limit varies by endpoint
    
    def get_rate_limit_window(self) -> int:
        return 60
    
    async def authenticate(self) -> bool:
        """Authenticate with Slack and validate token."""
        if not self.bot_token:
            return False
        
        # Test token by calling auth.test
        import aiohttp
        
        headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://slack.com/api/auth.test",
                headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("ok"):
                        return True
                    
        return False
    
    async def refresh_token(self) -> bool:
        """Slack tokens don't refresh, but we implement for interface."""
        return await self.authenticate()
    
    async def test_connection(self) -> Dict[str, Any]:
        """Test connection by fetching bot info."""
        import aiohttp
        
        headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://slack.com/api/auth.test",
                headers=headers
            ) as response:
                if response.status == 200:
                    return await response.json()
        
        return {}
    
    async def send_message(
        self,
        text: str,
        channel: str = None,
        blocks: List[Dict[str, Any]] = None,
        message_type: SlackMessageType = SlackMessageType.INFO,
        thread_ts: str = None
    ) -> Dict[str, Any]:
        """
        Send a message to Slack.
        
        Args:
            text: Message text
            channel: Channel ID or name (defaults to configured channel)
            blocks: Rich block kit blocks
            message_type: Type of message for styling
            thread_ts: Thread timestamp to reply in thread
        """
        channel = channel or self.default_channel
        
        # Add emoji prefix based on type
        emojis = {
            SlackMessageType.INFO: ":information_source:",
            SlackMessageType.SUCCESS: ":white_check_mark:",
            SlackMessageType.WARNING: ":warning:",
            SlackMessageType.ERROR: ":x:"
        }
        
        if emojis.get(message_type):
            text = f"{emojis[message_type]} {text}"
        
        payload = {
            "channel": channel,
            "text": text
        }
        
        if blocks:
            payload["blocks"] = blocks
        
        if thread_ts:
            payload["thread_ts"] = thread_ts
        
        response = await self._make_request(
            "POST",
            "https://slack.com/api/chat.postMessage",
            data=payload
        )
        
        return response
    
    async def send_invoice_notification(
        self,
        invoice_number: str,
        customer_name: str,
        amount: float,
        due_date: str,
        status: str,
        invoice_url: str = None
    ):
        """Send invoice notification with rich formatting."""
        
        # Determine color based on status
        colors = {
            "sent": "#36C5F0",
            "paid": "#2EB67D",
            "overdue": "#E01E5A",
            "pending": "#ECB22E"
        }
        
        color = colors.get(status.lower(), "#36C5F0")
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"Invoice {invoice_number} - {customer_name}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Amount:*\n${amount:,.2f}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Due Date:*\n{due_date}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Status:*\n{status.upper()}"
                    }
                ]
            }
        ]
        
        if invoice_url:
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View Invoice",
                            "emoji": True
                        },
                        "url": invoice_url,
                        "style": "primary"
                    }
                ]
            })
        
        message_type = SlackMessageType.INFO
        if status.lower() == "paid":
            message_type = SlackMessageType.SUCCESS
        elif status.lower() == "overdue":
            message_type = SlackMessageType.ERROR
        
        return await self.send_message(
            text=f"Invoice {invoice_number} update",
            blocks=blocks,
            message_type=message_type
        )
    
    async def send_contract_notification(
        self,
        contract_name: str,
        client_name: str,
        expiry_date: str,
        days_remaining: int
    ):
        """Send contract expiration notification."""
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"⚠️ Contract Expiring Soon",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Contract:*\n{contract_name}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Client:*\n{client_name}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Expiry Date:*\n{expiry_date}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Days Remaining:*\n{days_remaining}"
                    }
                ]
            }
        ]
        
        message_type = SlackMessageType.WARNING if days_remaining <= 7 else SlackMessageType.INFO
        
        return await self.send_message(
            text=f"Contract {contract_name} expires in {days_remaining} days",
            blocks=blocks,
            message_type=message_type
        )
    
    async def send_payment_reminder(
        self,
        invoice_number: str,
        customer_name: str,
        amount: float,
        days_overdue: int,
        invoice_url: str = None
    ):
        """Send payment reminder notification."""
        
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Payment Reminder*\nInvoice #{invoice_number} for *{customer_name}* is {days_overdue} days overdue."
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Amount Due:*\n${amount:,.2f}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Overdue:*\n{days_overdue} days"
                    }
                ]
            }
        ]
        
        if invoice_url:
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View & Pay",
                            "emoji": True
                        },
                        "url": invoice_url,
                        "style": "primary"
                    }
                ]
            })
        
        return await self.send_message(
            text=f"Payment reminder: Invoice #{invoice_number} is {days_overdue} days overdue",
            blocks=blocks,
            message_type=SlackMessageType.WARNING
        )
    
    async def send_ai_review_complete(
        self,
        document_name: str,
        risks_found: int,
        review_url: str = None
    ):
        """Send notification when AI contract review is complete."""
        
        risk_emoji = "⚠️" if risks_found > 0 else "✅"
        
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{risk_emoji} *AI Contract Review Complete*\nDocument: *{document_name}*"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Risks Found:*\n{risks_found}"
                    }
                ]
            }
        ]
        
        if review_url:
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View Review",
                            "emoji": True
                        },
                        "url": review_url,
                        "style": "primary"
                    }
                ]
            })
        
        message_type = SlackMessageType.WARNING if risks_found > 0 else SlackMessageType.SUCCESS
        
        return await self.send_message(
            text=f"AI review completed for {document_name}",
            blocks=blocks,
            message_type=message_type
        )
    
    async def send_bulk_notifications(
        self,
        notifications: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Send multiple notifications with rate limiting.
        """
        results = []
        
        for notification in notifications:
            try:
                result = await self.send_message(**notification)
                results.append({"success": True, "result": result})
            except Exception as e:
                logger.error(f"Failed to send Slack notification: {e}")
                results.append({"success": False, "error": str(e)})
        
        return results
    
    async def get_channel_info(self, channel: str) -> Dict[str, Any]:
        """Get channel information."""
        response = await self._make_request(
            "GET",
            f"https://slack.com/api/conversations.info?channel={channel}"
        )
        
        return response.get("channel", {})
    
    async def list_channels(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List all channels the bot has access to."""
        response = await self._make_request(
            "GET",
            f"https://slack.com/api/conversations.list?limit={limit}"
        )
        
        return response.get("channels", [])