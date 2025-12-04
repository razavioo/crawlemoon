"""CAPTCHA solving integration for various services."""

import logging
import asyncio
from typing import Optional, Dict, Any
from enum import Enum

try:
    from python_anticaptcha import AnticaptchaClient, ImageToTextTask, NoCaptchaTaskProxylessTask
    ANTICAPTCHA_AVAILABLE = True
except ImportError:
    ANTICAPTCHA_AVAILABLE = False

try:
    from capsolver import CapSolver
    CAPSOLVER_AVAILABLE = True
except ImportError:
    CAPSOLVER_AVAILABLE = False

logger = logging.getLogger(__name__)


class CaptchaService(Enum):
    """CAPTCHA solving service."""
    ANTICAPTCHA = "anticaptcha"
    CAPSOLVER = "capsolver"
    AUTO = "auto"  # Try both


class CaptchaType(Enum):
    """CAPTCHA type."""
    RECAPTCHA_V2 = "recaptcha_v2"
    RECAPTCHA_V3 = "recaptcha_v3"
    HCAPTCHA = "hcaptcha"
    TURNSTILE = "turnstile"
    FUNCAPTCHA = "funcaptcha"
    IMAGE = "image"
    TEXT = "text"


class CaptchaSolver:
    """Solve CAPTCHAs using various services."""
    
    def __init__(
        self,
        anticaptcha_key: Optional[str] = None,
        capsolver_key: Optional[str] = None,
        default_service: CaptchaService = CaptchaService.AUTO,
    ):
        """Initialize CAPTCHA solver.
        
        Args:
            anticaptcha_key: AntiCaptcha API key
            capsolver_key: CapSolver API key
            default_service: Default service to use
        """
        self.anticaptcha_key = anticaptcha_key
        self.capsolver_key = capsolver_key
        self.default_service = default_service
        
        self.anticaptcha_client = None
        if ANTICAPTCHA_AVAILABLE and anticaptcha_key:
            try:
                self.anticaptcha_client = AnticaptchaClient(anticaptcha_key)
            except Exception as e:
                logger.warning(f"Failed to initialize AntiCaptcha: {e}")
        
        self.capsolver_client = None
        if CAPSOLVER_AVAILABLE and capsolver_key:
            try:
                self.capsolver_client = CapSolver(capsolver_key)
            except Exception as e:
                logger.warning(f"Failed to initialize CapSolver: {e}")
    
    async def solve_recaptcha_v2(
        self,
        site_key: str,
        page_url: str,
        service: Optional[CaptchaService] = None,
    ) -> Optional[str]:
        """Solve reCAPTCHA v2.
        
        Args:
            site_key: reCAPTCHA site key
            page_url: Page URL where CAPTCHA appears
            service: Service to use (default: auto)
            
        Returns:
            Solution token or None if failed
        """
        service = service or self.default_service
        
        if service == CaptchaService.AUTO:
            # Try CapSolver first (faster for Turnstile/Cloudflare)
            if self.capsolver_client:
                try:
                    return await self._solve_recaptcha_v2_capsolver(site_key, page_url)
                except Exception as e:
                    logger.warning(f"CapSolver failed: {e}")
            
            # Fallback to AntiCaptcha
            if self.anticaptcha_client:
                try:
                    return await self._solve_recaptcha_v2_anticaptcha(site_key, page_url)
                except Exception as e:
                    logger.warning(f"AntiCaptcha failed: {e}")
        elif service == CaptchaService.CAPSOLVER and self.capsolver_client:
            return await self._solve_recaptcha_v2_capsolver(site_key, page_url)
        elif service == CaptchaService.ANTICAPTCHA and self.anticaptcha_client:
            return await self._solve_recaptcha_v2_anticaptcha(site_key, page_url)
        
        logger.error("No CAPTCHA solving service available")
        return None
    
    async def _solve_recaptcha_v2_anticaptcha(
        self,
        site_key: str,
        page_url: str,
    ) -> Optional[str]:
        """Solve reCAPTCHA v2 using AntiCaptcha."""
        if not self.anticaptcha_client:
            return None
        
        try:
            task = NoCaptchaTaskProxylessTask(page_url, site_key)
            job = self.anticaptcha_client.createTask(task)
            job.join()
            return job.get_solution_response()
        except Exception as e:
            logger.error(f"AntiCaptcha solving failed: {e}")
            return None
    
    async def _solve_recaptcha_v2_capsolver(
        self,
        site_key: str,
        page_url: str,
    ) -> Optional[str]:
        """Solve reCAPTCHA v2 using CapSolver."""
        if not self.capsolver_client:
            return None
        
        try:
            result = self.capsolver_client.recaptcha_v2_task_proxyless(
                website_url=page_url,
                website_key=site_key,
            )
            return result.get("gRecaptchaResponse") or result.get("token")
        except Exception as e:
            logger.error(f"CapSolver solving failed: {e}")
            return None
    
    async def solve_hcaptcha(
        self,
        site_key: str,
        page_url: str,
        service: Optional[CaptchaService] = None,
    ) -> Optional[str]:
        """Solve hCaptcha.
        
        Args:
            site_key: hCaptcha site key
            page_url: Page URL where CAPTCHA appears
            service: Service to use (default: auto)
            
        Returns:
            Solution token or None if failed
        """
        service = service or self.default_service
        
        if service == CaptchaService.CAPSOLVER and self.capsolver_client:
            try:
                result = self.capsolver_client.hcaptcha_task_proxyless(
                    website_url=page_url,
                    website_key=site_key,
                )
                return result.get("gRecaptchaResponse") or result.get("token")
            except Exception as e:
                logger.error(f"CapSolver hCaptcha solving failed: {e}")
                return None
        
        logger.warning("hCaptcha solving not available with current service")
        return None
    
    async def solve_turnstile(
        self,
        site_key: str,
        page_url: str,
        service: Optional[CaptchaService] = None,
    ) -> Optional[str]:
        """Solve Cloudflare Turnstile.
        
        Args:
            site_key: Turnstile site key
            page_url: Page URL where CAPTCHA appears
            service: Service to use (default: auto)
            
        Returns:
            Solution token or None if failed
        """
        service = service or self.default_service
        
        if service == CaptchaService.CAPSOLVER and self.capsolver_client:
            try:
                result = self.capsolver_client.cloudflare_turnstile_task_proxyless(
                    website_url=page_url,
                    website_key=site_key,
                )
                return result.get("token")
            except Exception as e:
                logger.error(f"CapSolver Turnstile solving failed: {e}")
                return None
        
        logger.warning("Turnstile solving not available with current service")
        return None
    
    async def solve_image_captcha(
        self,
        image_data: bytes,
        service: Optional[CaptchaService] = None,
    ) -> Optional[str]:
        """Solve image-based CAPTCHA.
        
        Args:
            image_data: CAPTCHA image bytes
            service: Service to use (default: auto)
            
        Returns:
            Solution text or None if failed
        """
        service = service or self.default_service
        
        if service == CaptchaService.ANTICAPTCHA and self.anticaptcha_client:
            try:
                task = ImageToTextTask(image_data)
                job = self.anticaptcha_client.createTask(task)
                job.join()
                return job.get_captcha_text()
            except Exception as e:
                logger.error(f"AntiCaptcha image solving failed: {e}")
                return None
        
        logger.warning("Image CAPTCHA solving not available with current service")
        return None
    
    def is_available(self) -> bool:
        """Check if any CAPTCHA solving service is available."""
        return (self.anticaptcha_client is not None) or (self.capsolver_client is not None)


# Global instance
_captcha_solver = None

def get_captcha_solver(
    anticaptcha_key: Optional[str] = None,
    capsolver_key: Optional[str] = None,
) -> Optional[CaptchaSolver]:
    """Get global CAPTCHA solver instance."""
    global _captcha_solver
    
    # Initialize from environment if not provided
    import os
    anticaptcha_key = anticaptcha_key or os.getenv("ANTICAPTCHA_API_KEY")
    capsolver_key = capsolver_key or os.getenv("CAPSOLVER_API_KEY")
    
    if not anticaptcha_key and not capsolver_key:
        return None
    
    if _captcha_solver is None:
        _captcha_solver = CaptchaSolver(
            anticaptcha_key=anticaptcha_key,
            capsolver_key=capsolver_key,
        )
    
    return _captcha_solver if _captcha_solver.is_available() else None

