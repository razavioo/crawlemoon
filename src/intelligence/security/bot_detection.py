"""Bot detection analyzer."""

import logging
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ProtectionType(Enum):
    """Protection type."""
    CLOUDFLARE = "cloudflare"
    AKAMAI = "akamai"
    PERIMETERX = "perimeterx"
    DATADOME = "datadome"
    RECAPTCHA = "recaptcha"
    HCAPTCHA = "hcaptcha"
    FUNCAPTCHA = "funcaptcha"
    NONE = "none"


class CaptchaType(Enum):
    """Captcha type."""
    RECAPTCHA_V2 = "recaptcha_v2"
    RECAPTCHA_V3 = "recaptcha_v3"
    HCAPTCHA = "hcaptcha"
    FUNCAPTCHA = "funcaptcha"
    NONE = "none"


@dataclass
class FingerprintingInfo:
    """Browser fingerprinting information."""
    
    canvas_fingerprint: bool = False
    webgl_fingerprint: bool = False
    audio_fingerprint: bool = False
    font_fingerprint: bool = False
    screen_fingerprint: bool = False


@dataclass
class RateLimitInfo:
    """Rate limiting information."""
    
    requests_per_minute: Optional[int] = None
    requests_per_hour: Optional[int] = None
    block_duration: Optional[int] = None


class BotDetectionAnalyzer:
    """Analyzes bot detection and protection mechanisms."""
    
    def detect_protection_type(self, page_content: str, headers: dict) -> ProtectionType:
        """Detect protection type from page content and headers."""
        content_lower = page_content.lower()
        
        # Check headers
        server = headers.get("Server", "").lower()
        cf_ray = headers.get("CF-RAY", "")
        
        if "cloudflare" in server or cf_ray:
            return ProtectionType.CLOUDFLARE
        
        if "akamai" in server:
            return ProtectionType.AKAMAI
        
        # Check page content
        if "perimeterx" in content_lower:
            return ProtectionType.PERIMETERX
        
        if "datadome" in content_lower:
            return ProtectionType.DATADOME
        
        # Check for captcha
        if "recaptcha" in content_lower:
            return ProtectionType.RECAPTCHA
        
        if "hcaptcha" in content_lower:
            return ProtectionType.HCAPTCHA
        
        if "funcaptcha" in content_lower:
            return ProtectionType.FUNCAPTCHA
        
        return ProtectionType.NONE
    
    def analyze_fingerprinting(self, page_content: str) -> FingerprintingInfo:
        """Analyze fingerprinting techniques used."""
        content_lower = page_content.lower()
        
        info = FingerprintingInfo()
        
        # Check for fingerprinting libraries
        if "fingerprint" in content_lower:
            # Common fingerprinting checks
            info.canvas_fingerprint = "canvas" in content_lower
            info.webgl_fingerprint = "webgl" in content_lower or "getcontext" in content_lower
            info.audio_fingerprint = "audiocontext" in content_lower
            info.font_fingerprint = "font" in content_lower and "measuretext" in content_lower
            info.screen_fingerprint = "screen.width" in content_lower or "window.screen" in content_lower
        
        return info
    
    def detect_captcha_type(self, page_content: str) -> CaptchaType:
        """Detect captcha type."""
        content_lower = page_content.lower()
        
        if "recaptcha" in content_lower:
            if "recaptcha/v3" in content_lower:
                return CaptchaType.RECAPTCHA_V3
            return CaptchaType.RECAPTCHA_V2
        
        if "hcaptcha" in content_lower:
            return CaptchaType.HCAPTCHA
        
        if "funcaptcha" in content_lower:
            return CaptchaType.FUNCAPTCHA
        
        return CaptchaType.NONE
    
    def find_rate_limits(self, headers: dict, response_times: List[float]) -> RateLimitInfo:
        """Find rate limiting information."""
        info = RateLimitInfo()
        
        # Check headers for rate limit info
        rate_limit = headers.get("X-RateLimit-Limit")
        rate_limit_remaining = headers.get("X-RateLimit-Remaining")
        retry_after = headers.get("Retry-After")
        
        if rate_limit:
            try:
                info.requests_per_minute = int(rate_limit)
            except:
                pass
        
        if retry_after:
            try:
                info.block_duration = int(retry_after)
            except:
                pass
        
        # Analyze response times for patterns
        if response_times:
            # If response times spike or become slow, might indicate rate limiting
            avg_time = sum(response_times) / len(response_times)
            if avg_time > 5.0:  # More than 5 seconds average
                logger.warning("Slow response times detected, possible rate limiting")
        
        return info


