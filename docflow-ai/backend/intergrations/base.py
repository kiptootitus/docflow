"""
Enterprise-grade integration base classes with retry logic, rate limiting,
circuit breakers, and comprehensive error handling.
"""

import logging
import hashlib
import hmac
import json
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass
from enum import Enum
import asyncio
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.db import models
from django.utils import timezone
from django.utils.crypto import get_random_string
from celery import shared_task

logger = logging.getLogger(__name__)


class IntegrationStatus(Enum):
    """Integration health status."""
    ACTIVE = "active"
    DEGRADED = "degraded"
    INACTIVE = "inactive"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"


class IntegrationType(Enum):
    """Supported integration types."""
    QUICKBOOKS = "quickbooks"
    XERO = "xero"
    SLACK = "slack"
    GOOGLE_DRIVE = "google_drive"
    ZAPIER = "zapier"


@dataclass
class IntegrationCredentials:
    """Securely store integration credentials."""
    access_token: str
    refresh_token: Optional[str] = None
    token_expiry: Optional[datetime] = None
    scopes: List[str] = None
    additional_data: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.scopes is None:
            self.scopes = []
        if self.additional_data is None:
            self.additional_data = {}
    
    def is_expired(self) -> bool:
        """Check if token is expired."""
        if not self.token_expiry:
            return False
        return timezone.now() >= self.token_expiry
    
    def needs_refresh(self, buffer_minutes: int = 5) -> bool:
        """Check if token needs refresh (with buffer)."""
        if not self.token_expiry:
            return False
        return timezone.now() >= (self.token_expiry - timedelta(minutes=buffer_minutes))


class CircuitBreaker:
    """
    Circuit breaker pattern to prevent cascading failures.
    
    States:
    - CLOSED: Normal operation, requests go through
    - OPEN: Failing, requests fail fast
    - HALF_OPEN: Testing if service recovered
    """
    
    class State(Enum):
        CLOSED = "closed"
        OPEN = "open"
        HALF_OPEN = "half_open"
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        
        self.state = self.State.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.half_open_calls = 0
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        if self.state == self.State.OPEN:
            if timezone.now() >= self.last_failure_time + timedelta(seconds=self.recovery_timeout):
                self.state = self.State.HALF_OPEN
                self.half_open_calls = 0
                logger.info("Circuit breaker moved to HALF_OPEN state")
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker is OPEN. Failed {self.failure_count} times. "
                    f"Recovery in {self.recovery_timeout - (timezone.now() - self.last_failure_time).seconds}s"
                )
        
        try:
            result = func(*args, **kwargs)
            
            if self.state == self.State.HALF_OPEN:
                self.half_open_calls += 1
                if self.half_open_calls >= self.half_open_max_calls:
                    self.reset()
                    
            return result
            
        except Exception as e:
            self._record_failure()
            raise
    
    def _record_failure(self):
        """Record a failure and potentially open the circuit."""
        self.failure_count += 1
        self.last_failure_time = timezone.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = self.State.OPEN
            logger.error(
                f"Circuit breaker opened after {self.failure_count} failures"
            )
    
    def reset(self):
        """Reset circuit breaker to closed state."""
        self.state = self.State.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.half_open_calls = 0
        logger.info("Circuit breaker reset to CLOSED state")


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


class RateLimiter:
    """
    Token bucket rate limiter for API rate limiting.
    """
    
    def __init__(
        self,
        rate_limit: int = 100,  # requests per time_window
        time_window: int = 60,  # seconds
        burst_limit: int = 10
    ):
        self.rate_limit = rate_limit
        self.time_window = time_window
        self.burst_limit = burst_limit
        self.tokens = burst_limit
        self.last_refill = timezone.now()
    
    async def acquire(self) -> bool:
        """Acquire a token for rate-limited operation."""
        now = timezone.now()
        elapsed = (now - self.last_refill).total_seconds()
        
        # Refill tokens based on elapsed time
        new_tokens = elapsed * (self.rate_limit / self.time_window)
        self.tokens = min(self.burst_limit, self.tokens + new_tokens)
        self.last_refill = now
        
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        
        return False
    
    async def wait_and_acquire(self, max_wait: int = 30):
        """Wait until a token is available."""
        start_time = timezone.now()
        
        while (timezone.now() - start_time).total_seconds() < max_wait:
            if await self.acquire():
                return True
            await asyncio.sleep(0.5)
        
        raise RateLimitExceededError(f"Could not acquire token within {max_wait}s")


class RateLimitExceededError(Exception):
    """Raised when rate limit is exceeded."""
    pass


class IntegrationBase(ABC):
    """
    Abstract base class for all integrations with enterprise features.
    """
    
    def __init__(
        self,
        company_id: int,
        credentials: Optional[IntegrationCredentials] = None,
        enable_circuit_breaker: bool = True,
        enable_rate_limiter: bool = True
    ):
        self.company_id = company_id
        self.credentials = credentials
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Circuit breaker for failure handling
        self.circuit_breaker = CircuitBreaker() if enable_circuit_breaker else None
        
        # Rate limiter for API throttling
        self.rate_limiter = RateLimiter(
            rate_limit=self.get_rate_limit(),
            time_window=self.get_rate_limit_window()
        ) if enable_rate_limiter else None
        
        # Metrics tracking
        self.metrics = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_latency": 0.0
        }
    
    @abstractmethod
    def get_integration_type(self) -> IntegrationType:
        """Return integration type."""
        pass
    
    @abstractmethod
    def get_rate_limit(self) -> int:
        """Get API rate limit (requests per window)."""
        pass
    
    @abstractmethod
    def get_rate_limit_window(self) -> int:
        """Get rate limit window in seconds."""
        pass
    
    @abstractmethod
    async def authenticate(self) -> bool:
        """Authenticate with the third-party service."""
        pass
    
    @abstractmethod
    async def refresh_token(self) -> bool:
        """Refresh access token if expired."""
        pass
    
    @abstractmethod
    async def test_connection(self) -> Dict[str, Any]:
        """Test the integration connection."""
        pass
    
    async def _make_request(
        self,
        method: str,
        url: str,
        data: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        retry_count: int = 3
    ) -> Dict[str, Any]:
        """
        Make authenticated API request with retry logic and circuit breaker.
        """
        import aiohttp
        from aiohttp import ClientTimeout
        
        # Check rate limit
        if self.rate_limiter:
            await self.rate_limiter.wait_and_acquire()
        
        # Execute with circuit breaker
        async def _execute_request():
            # Refresh token if needed
            if self.credentials and self.credentials.needs_refresh():
                await self.refresh_token()
            
            # Prepare request
            request_headers = self._get_request_headers()
            if headers:
                request_headers.update(headers)
            
            timeout = ClientTimeout(total=30)
            
            start_time = timezone.now()
            
            async with aiohttp.ClientSession() as session:
                for attempt in range(retry_count):
                    try:
                        async with session.request(
                            method=method,
                            url=url,
                            json=data,
                            headers=request_headers,
                            timeout=timeout
                        ) as response:
                            latency = (timezone.now() - start_time).total_seconds()
                            self._update_metrics(True, latency)
                            
                            if response.status == 200:
                                return await response.json()
                            elif response.status == 401:
                                # Token expired, try refresh
                                await self.refresh_token()
                                continue
                            elif response.status == 429:
                                # Rate limited, exponential backoff
                                wait_time = min(2 ** attempt, 30)
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                response_text = await response.text()
                                raise IntegrationAPIError(
                                    f"API request failed with status {response.status}: {response_text}"
                                )
                    
                    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                        latency = (timezone.now() - start_time).total_seconds()
                        self._update_metrics(False, latency)
                        
                        if attempt == retry_count - 1:
                            raise IntegrationRequestError(f"Request failed after {retry_count} attempts: {str(e)}")
                        
                        wait_time = min(2 ** attempt, 10)
                        await asyncio.sleep(wait_time)
                        continue
        
        if self.circuit_breaker:
            return self.circuit_breaker.call(_execute_request)
        else:
            return await _execute_request()
    
    def _get_request_headers(self) -> Dict[str, str]:
        """Get headers for API request."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"DocFlowAI/{settings.VERSION if hasattr(settings, 'VERSION') else '1.0'}"
        }
        
        if self.credentials and self.credentials.access_token:
            headers["Authorization"] = f"Bearer {self.credentials.access_token}"
        
        return headers
    
    def _update_metrics(self, success: bool, latency: float):
        """Update integration metrics."""
        self.metrics["total_calls"] += 1
        if success:
            self.metrics["successful_calls"] += 1
        else:
            self.metrics["failed_calls"] += 1
        self.metrics["total_latency"] += latency
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get integration metrics."""
        success_rate = 0
        if self.metrics["total_calls"] > 0:
            success_rate = (
                self.metrics["successful_calls"] / self.metrics["total_calls"] * 100
            )
        
        avg_latency = 0
        if self.metrics["total_calls"] > 0:
            avg_latency = self.metrics["total_latency"] / self.metrics["total_calls"]
        
        return {
            "total_calls": self.metrics["total_calls"],
            "successful_calls": self.metrics["successful_calls"],
            "failed_calls": self.metrics["failed_calls"],
            "success_rate": success_rate,
            "average_latency_ms": avg_latency * 1000,
            "circuit_breaker_state": self.circuit_breaker.state.value if self.circuit_breaker else "disabled",
            "rate_limiter_enabled": bool(self.rate_limiter)
        }


class IntegrationAPIError(Exception):
    """Raised when external API returns error."""
    pass


class IntegrationRequestError(Exception):
    """Raised when request to external API fails."""
    pass