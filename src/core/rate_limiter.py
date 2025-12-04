"""Rate limiter with per-domain limits and exponential backoff."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from urllib.parse import urlparse
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limit configuration for a domain."""
    
    requests_per_second: float = 1.0
    requests_per_minute: Optional[int] = None
    requests_per_hour: Optional[int] = None
    burst_size: int = 5  # Allow burst of N requests
    
    def get_min_interval(self) -> float:
        """Get minimum interval between requests in seconds."""
        if self.requests_per_second:
            return 1.0 / self.requests_per_second
        return 1.0


@dataclass
class RequestRecord:
    """Record of a request for rate limiting."""
    
    timestamp: float
    domain: str
    status_code: Optional[int] = None


class RateLimiter:
    """Rate limiter with per-domain limits and exponential backoff."""
    
    def __init__(self):
        self._domain_configs: Dict[str, RateLimitConfig] = {}
        self._domain_queues: Dict[str, deque] = {}  # Track request timestamps
        self._domain_backoff: Dict[str, float] = {}  # Track backoff until time
        self._default_config = RateLimitConfig(requests_per_second=1.0)
        self._lock = asyncio.Lock()
        
        # Global rate limit (optional)
        self._global_queue: Optional[deque] = None
        self._global_config: Optional[RateLimitConfig] = None
    
    def set_default_rate_limit(
        self,
        requests_per_second: float = 1.0,
        requests_per_minute: Optional[int] = None,
        requests_per_hour: Optional[int] = None,
    ) -> None:
        """Set default rate limit for all domains."""
        self._default_config = RateLimitConfig(
            requests_per_second=requests_per_second,
            requests_per_minute=requests_per_minute,
            requests_per_hour=requests_per_hour,
        )
        logger.info(f"Set default rate limit: {requests_per_second} req/s")
    
    def set_domain_rate_limit(
        self,
        domain: str,
        requests_per_second: float = 1.0,
        requests_per_minute: Optional[int] = None,
        requests_per_hour: Optional[int] = None,
    ) -> None:
        """Set rate limit for a specific domain."""
        self._domain_configs[domain] = RateLimitConfig(
            requests_per_second=requests_per_second,
            requests_per_minute=requests_per_minute,
            requests_per_hour=requests_per_hour,
        )
        logger.info(f"Set rate limit for {domain}: {requests_per_second} req/s")
    
    def set_global_rate_limit(
        self,
        requests_per_second: float = 10.0,
        requests_per_minute: Optional[int] = None,
        requests_per_hour: Optional[int] = None,
    ) -> None:
        """Set global rate limit across all domains."""
        self._global_config = RateLimitConfig(
            requests_per_second=requests_per_second,
            requests_per_minute=requests_per_minute,
            requests_per_hour=requests_per_hour,
        )
        self._global_queue = deque()
        logger.info(f"Set global rate limit: {requests_per_second} req/s")
    
    async def wait_if_needed(self, url: str) -> None:
        """Wait if rate limit would be exceeded for this URL."""
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.hostname or "unknown"
        
        async with self._lock:
            # Check global rate limit first
            if self._global_config and self._global_queue:
                await self._check_global_rate_limit()
            
            # Check domain-specific rate limit
            await self._check_domain_rate_limit(domain)
            
            # Record the request
            now = time.time()
            if domain not in self._domain_queues:
                self._domain_queues[domain] = deque()
            self._domain_queues[domain].append(now)
            
            if self._global_queue is not None:
                self._global_queue.append(now)
    
    async def _check_global_rate_limit(self) -> None:
        """Check and enforce global rate limit."""
        if not self._global_config or not self._global_queue:
            return
        
        now = time.time()
        config = self._global_config
        
        # Clean old entries
        cutoff = now - 3600  # Keep last hour
        while self._global_queue and self._global_queue[0] < cutoff:
            self._global_queue.popleft()
        
        # Check per-second limit
        if config.requests_per_second:
            recent = sum(1 for t in self._global_queue if t > now - 1.0)
            if recent >= config.requests_per_second:
                wait_time = 1.0 - (now - self._global_queue[-1])
                if wait_time > 0:
                    logger.debug(f"Global rate limit: waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
        
        # Check per-minute limit
        if config.requests_per_minute:
            recent = sum(1 for t in self._global_queue if t > now - 60.0)
            if recent >= config.requests_per_minute:
                wait_time = 60.0 - (now - self._global_queue[-1])
                if wait_time > 0:
                    logger.debug(f"Global rate limit (minute): waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
        
        # Check per-hour limit
        if config.requests_per_hour:
            recent = sum(1 for t in self._global_queue if t > now - 3600.0)
            if recent >= config.requests_per_hour:
                wait_time = 3600.0 - (now - self._global_queue[-1])
                if wait_time > 0:
                    logger.warning(f"Global rate limit (hour): waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
    
    async def _check_domain_rate_limit(self, domain: str) -> None:
        """Check and enforce domain-specific rate limit."""
        # Check if domain is in backoff
        if domain in self._domain_backoff:
            backoff_until = self._domain_backoff[domain]
            now = time.time()
            if now < backoff_until:
                wait_time = backoff_until - now
                logger.debug(f"Domain {domain} in backoff: waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
            else:
                # Backoff expired
                del self._domain_backoff[domain]
        
        # Get config for domain
        config = self._domain_configs.get(domain, self._default_config)
        
        # Initialize queue if needed
        if domain not in self._domain_queues:
            self._domain_queues[domain] = deque()
        
        queue = self._domain_queues[domain]
        now = time.time()
        
        # Clean old entries (keep last hour)
        cutoff = now - 3600
        while queue and queue[0] < cutoff:
            queue.popleft()
        
        # Check per-second limit
        if config.requests_per_second:
            recent = [t for t in queue if t > now - 1.0]
            if len(recent) >= config.requests_per_second:
                # Calculate wait time
                oldest_recent = recent[0]
                wait_time = 1.0 - (now - oldest_recent)
                if wait_time > 0:
                    logger.debug(f"Rate limit for {domain}: waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
        
        # Check per-minute limit
        if config.requests_per_minute:
            recent = [t for t in queue if t > now - 60.0]
            if len(recent) >= config.requests_per_minute:
                oldest_recent = recent[0]
                wait_time = 60.0 - (now - oldest_recent)
                if wait_time > 0:
                    logger.debug(f"Rate limit (minute) for {domain}: waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
        
        # Check per-hour limit
        if config.requests_per_hour:
            recent = [t for t in queue if t > now - 3600.0]
            if len(recent) >= config.requests_per_hour:
                oldest_recent = recent[0]
                wait_time = 3600.0 - (now - oldest_recent)
                if wait_time > 0:
                    logger.warning(f"Rate limit (hour) for {domain}: waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
    
    def record_response(self, url: str, status_code: int) -> None:
        """Record a response and apply exponential backoff if needed."""
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.hostname or "unknown"
        
        # Apply exponential backoff on 429 (Too Many Requests) or 503 (Service Unavailable)
        if status_code in [429, 503]:
            retry_after = None
            
            # Try to get Retry-After header (would need to pass headers here)
            # For now, use exponential backoff based on failure count
            
            current_backoff = self._domain_backoff.get(domain, 0)
            now = time.time()
            
            if current_backoff > now:
                # Already in backoff, increase it
                backoff_duration = min((current_backoff - now) * 2, 300)  # Max 5 minutes
            else:
                # Start new backoff
                backoff_duration = 5.0  # Start with 5 seconds
            
            backoff_until = now + backoff_duration
            self._domain_backoff[domain] = backoff_until
            logger.warning(
                f"Rate limit hit for {domain} (status {status_code}). "
                f"Backing off for {backoff_duration:.1f}s"
            )
    
    def get_stats(self) -> Dict:
        """Get rate limiter statistics."""
        stats = {
            "default_config": {
                "requests_per_second": self._default_config.requests_per_second,
                "requests_per_minute": self._default_config.requests_per_minute,
                "requests_per_hour": self._default_config.requests_per_hour,
            },
            "domain_configs": len(self._domain_configs),
            "domains_in_backoff": len(self._domain_backoff),
            "domains_tracked": len(self._domain_queues),
        }
        
        if self._global_config:
            stats["global_config"] = {
                "requests_per_second": self._global_config.requests_per_second,
                "requests_per_minute": self._global_config.requests_per_minute,
                "requests_per_hour": self._global_config.requests_per_hour,
            }
        
        return stats

