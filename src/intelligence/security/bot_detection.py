"""Bot detection analyzer."""

import logging
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum

try:
    from .captcha_solver import get_captcha_solver, CaptchaSolver
    CAPTCHA_SOLVING_AVAILABLE = True
except ImportError:
    CAPTCHA_SOLVING_AVAILABLE = False
    CaptchaSolver = None

logger = logging.getLogger(__name__)


class ProtectionType(Enum):
    """Protection type."""
    CLOUDFLARE = "cloudflare"
    AKAMAI = "akamai"
    PERIMETERX = "perimeterx"
    DATADOME = "datadome"
    IMPERVA = "imperva"
    SHAPE_SECURITY = "shape_security"
    KASADA = "kasada"
    RECAPTCHA = "recaptcha"
    HCAPTCHA = "hcaptcha"
    FUNCAPTCHA = "funcaptcha"
    AWS_WAF = "aws_waf"
    MODSECURITY = "modsecurity"
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
    device_fingerprint: bool = False
    tls_fingerprint: bool = False  # JA3/JA4 fingerprinting


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
        headers_lower = {k.lower(): v.lower() for k, v in headers.items()}
        
        # Check headers first (more reliable)
        server = headers_lower.get("server", "")
        cf_ray = headers.get("CF-RAY", "")
        x_akamai = headers.get("X-Akamai-Transformed", "")
        x_imperva = headers.get("X-Imperva", "")
        x_kasada = headers.get("X-Kasada", "")
        
        if "cloudflare" in server or cf_ray or "cf-ray" in headers_lower:
            return ProtectionType.CLOUDFLARE
        
        if "akamai" in server or x_akamai:
            return ProtectionType.AKAMAI
        
        if x_imperva or "imperva" in server:
            return ProtectionType.IMPERVA
        
        if x_kasada or "kasada" in content_lower:
            return ProtectionType.KASADA
        
        # Check for AWS WAF
        if "x-amzn-requestid" in headers_lower or "aws" in server:
            # Additional check for WAF challenge
            if "aws-waf" in content_lower or "aws waf" in content_lower:
                return ProtectionType.AWS_WAF
        
        # Check for ModSecurity
        if "mod_security" in server or "modsecurity" in content_lower:
            return ProtectionType.MODSECURITY
        
        # Check page content
        if "perimeterx" in content_lower or "px-captcha" in content_lower:
            return ProtectionType.PERIMETERX
        
        if "datadome" in content_lower or "datadome.co" in content_lower:
            return ProtectionType.DATADOME
        
        if "shape" in content_lower and "security" in content_lower:
            return ProtectionType.SHAPE_SECURITY
        
        # Check for captcha
        if "recaptcha" in content_lower or "grecaptcha" in content_lower:
            return ProtectionType.RECAPTCHA
        
        if "hcaptcha" in content_lower:
            return ProtectionType.HCAPTCHA
        
        if "funcaptcha" in content_lower or "arkoselabs" in content_lower:
            return ProtectionType.FUNCAPTCHA
        
        return ProtectionType.NONE
    
    def analyze_fingerprinting(self, page_content: str) -> FingerprintingInfo:
        """Analyze fingerprinting techniques used."""
        content_lower = page_content.lower()
        
        info = FingerprintingInfo()
        
        # Check for fingerprinting libraries
        fingerprint_libs = [
            "fingerprintjs", "fingerprint2", "clientjs", "fpcollect",
            "browserprint", "deviceprint"
        ]
        
        has_fingerprint_lib = any(lib in content_lower for lib in fingerprint_libs)
        
        if "fingerprint" in content_lower or has_fingerprint_lib:
            # Common fingerprinting checks
            info.canvas_fingerprint = (
                "canvas" in content_lower and 
                ("toDataURL" in content_lower or "getImageData" in content_lower)
            )
            info.webgl_fingerprint = (
                "webgl" in content_lower or 
                "getcontext" in content_lower and "webgl" in content_lower
            )
            info.audio_fingerprint = (
                "audiocontext" in content_lower or 
                "createanalyser" in content_lower
            )
            info.font_fingerprint = (
                "font" in content_lower and 
                ("measuretext" in content_lower or "getcomputedstyle" in content_lower)
            )
            info.screen_fingerprint = (
                "screen.width" in content_lower or 
                "window.screen" in content_lower or
                "screen.availwidth" in content_lower
            )
            info.device_fingerprint = (
                "navigator.device" in content_lower or
                "navigator.hardwareconcurrency" in content_lower or
                "navigator.platform" in content_lower
            )
        
        # Check for TLS fingerprinting (JA3/JA4) - would need network analysis
        # This is a placeholder - actual detection would require TLS handshake analysis
        if "tls" in content_lower and "fingerprint" in content_lower:
            info.tls_fingerprint = True
        
        return info
    
    def detect_waf(self, headers: dict, page_content: str) -> Optional[str]:
        """Detect Web Application Firewall (WAF)."""
        content_lower = page_content.lower()
        headers_lower = {k.lower(): v.lower() for k, v in headers.items()}
        
        # AWS WAF
        if "x-amzn-requestid" in headers_lower or "aws-waf" in content_lower:
            return "AWS WAF"
        
        # Cloudflare WAF
        if "cf-ray" in headers_lower or "cloudflare" in headers_lower.get("server", ""):
            return "Cloudflare WAF"
        
        # Imperva
        if "x-imperva" in headers_lower or "imperva" in content_lower:
            return "Imperva"
        
        # Akamai
        if "x-akamai" in headers_lower or "akamai" in headers_lower.get("server", ""):
            return "Akamai"
        
        # ModSecurity
        if "mod_security" in headers_lower.get("server", "") or "modsecurity" in content_lower:
            return "ModSecurity"
        
        # Sucuri
        if "x-sucuri" in headers_lower or "sucuri" in content_lower:
            return "Sucuri"
        
        return None
    
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
    
    async def solve_captcha_if_present(
        self,
        page_content: str,
        page_url: str,
        captcha_type: Optional[CaptchaType] = None,
    ) -> Optional[str]:
        """Detect and solve CAPTCHA if present.
        
        Args:
            page_content: Page HTML content
            page_url: Page URL
            captcha_type: Optional specific CAPTCHA type to solve
            
        Returns:
            Solution token if solved, None otherwise
        """
        if not CAPTCHA_SOLVING_AVAILABLE:
            logger.warning("CAPTCHA solving not available")
            return None
        
        captcha_solver = get_captcha_solver()
        if not captcha_solver:
            logger.warning("No CAPTCHA solver configured")
            return None
        
        # Detect CAPTCHA type if not provided
        if not captcha_type:
            captcha_type = self.detect_captcha_type(page_content)
        
        if captcha_type == CaptchaType.NONE:
            return None
        
        # Extract site key from page content
        import re
        
        site_key = None
        if captcha_type in [CaptchaType.RECAPTCHA_V2, CaptchaType.RECAPTCHA_V3]:
            # Extract reCAPTCHA site key
            match = re.search(r'data-sitekey=["\']([^"\']+)["\']', page_content)
            if not match:
                match = re.search(r'sitekey["\']?\s*[:=]\s*["\']([^"\']+)["\']', page_content)
            if match:
                site_key = match.group(1)
                logger.info(f"Found reCAPTCHA site key: {site_key[:20]}...")
        
        elif captcha_type == CaptchaType.HCAPTCHA:
            # Extract hCaptcha site key
            match = re.search(r'data-sitekey=["\']([^"\']+)["\']', page_content)
            if match:
                site_key = match.group(1)
                logger.info(f"Found hCaptcha site key: {site_key[:20]}...")
        
        elif captcha_type == CaptchaType.TURNSTILE:
            # Extract Turnstile site key
            match = re.search(r'data-sitekey=["\']([^"\']+)["\']', page_content)
            if not match:
                match = re.search(r'sitekey["\']?\s*[:=]\s*["\']([^"\']+)["\']', page_content)
            if match:
                site_key = match.group(1)
                logger.info(f"Found Turnstile site key: {site_key[:20]}...")
        
        if not site_key:
            logger.warning(f"Could not extract site key for {captcha_type.value}")
            return None
        
        # Solve CAPTCHA
        try:
            if captcha_type == CaptchaType.RECAPTCHA_V2:
                return await captcha_solver.solve_recaptcha_v2(site_key, page_url)
            elif captcha_type == CaptchaType.HCAPTCHA:
                return await captcha_solver.solve_hcaptcha(site_key, page_url)
            elif captcha_type == CaptchaType.TURNSTILE:
                return await captcha_solver.solve_turnstile(site_key, page_url)
            else:
                logger.warning(f"CAPTCHA type {captcha_type.value} not yet supported for solving")
                return None
        except Exception as e:
            logger.error(f"Error solving CAPTCHA: {e}")
            return None



