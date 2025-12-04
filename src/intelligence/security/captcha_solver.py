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

# Free OCR libraries for image CAPTCHA solving
OCR_AVAILABLE = False
EASYOCR_AVAILABLE = False

try:
    import pytesseract
    from PIL import Image
    import io
    OCR_AVAILABLE = True
except ImportError:
    pass

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    pass

logger = logging.getLogger(__name__)


class CaptchaService(Enum):
    """CAPTCHA solving service."""
    ANTICAPTCHA = "anticaptcha"
    CAPSOLVER = "capsolver"
    FREE = "free"  # Free methods (OCR, browser automation)
    AUTO = "auto"  # Try free first, then paid services


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
        page=None,  # Optional Playwright page for browser automation
    ) -> Optional[str]:
        """Solve reCAPTCHA v2.
        
        Args:
            site_key: reCAPTCHA site key
            page_url: Page URL where CAPTCHA appears
            service: Service to use (default: auto)
            page: Optional Playwright page for browser automation (free method)
            
        Returns:
            Solution token or None if failed
        """
        service = service or self.default_service
        
        # Try free browser automation first if AUTO or FREE
        if service in [CaptchaService.AUTO, CaptchaService.FREE] and page:
            result = await self._solve_recaptcha_v2_browser(page, site_key)
            if result:
                return result
        
        if service == CaptchaService.AUTO:
            # Try CapSolver (faster for Turnstile/Cloudflare)
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
        elif service == CaptchaService.FREE and page:
            return await self._solve_recaptcha_v2_browser(page, site_key)
        
        logger.warning("No CAPTCHA solving service available")
        return None
    
    async def _solve_recaptcha_v2_browser(self, page, site_key: str) -> Optional[str]:
        """Solve reCAPTCHA v2 using browser automation (free method).
        
        This method attempts to interact with the reCAPTCHA widget by:
        1. Finding the reCAPTCHA iframe
        2. Clicking the checkbox
        3. Waiting for challenge (if any)
        4. Extracting the solution token
        
        Args:
            page: Playwright page object
            site_key: reCAPTCHA site key
            
        Returns:
            Solution token or None if failed
        """
        try:
            # Wait for reCAPTCHA to load
            await page.wait_for_timeout(2000)
            
            # Try to find and click the reCAPTCHA checkbox
            # reCAPTCHA v2 checkbox selector
            checkbox_selectors = [
                'iframe[src*="recaptcha"]',
                '.g-recaptcha iframe',
                '#recaptcha iframe',
            ]
            
            iframe = None
            for selector in checkbox_selectors:
                try:
                    iframe_element = await page.query_selector(selector)
                    if iframe_element:
                        iframe = await iframe_element.content_frame()
                        if iframe:
                            break
                except:
                    continue
            
            if not iframe:
                logger.warning("Could not find reCAPTCHA iframe")
                return None
            
            # Click the checkbox
            try:
                checkbox = await iframe.query_selector('#recaptcha-anchor')
                if checkbox:
                    await checkbox.click()
                    await page.wait_for_timeout(3000)
                    
                    # Check if challenge appeared
                    challenge_frame = await page.query_selector('iframe[title*="challenge"]')
                    if challenge_frame:
                        logger.info("reCAPTCHA challenge appeared - manual solving required")
                        # For now, return None - could be extended to handle image challenges
                        return None
                    
                    # Try to get the response token
                    # The token is usually in a textarea with name="g-recaptcha-response"
                    response_textarea = await page.query_selector('textarea[name="g-recaptcha-response"]')
                    if response_textarea:
                        token = await response_textarea.input_value()
                        if token:
                            logger.info("Successfully solved reCAPTCHA v2 via browser automation")
                            return token
                    
                    # Alternative: execute JavaScript to get token
                    try:
                        token = await page.evaluate("""
                            () => {
                                const textarea = document.querySelector('textarea[name="g-recaptcha-response"]');
                                return textarea ? textarea.value : null;
                            }
                        """)
                        if token:
                            logger.info("Successfully solved reCAPTCHA v2 via browser automation (JS)")
                            return token
                    except:
                        pass
                        
            except Exception as e:
                logger.debug(f"Browser automation failed: {e}")
            
        except Exception as e:
            logger.debug(f"reCAPTCHA v2 browser automation error: {e}")
        
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
            # AntiCaptcha API is synchronous, run in thread pool
            loop = asyncio.get_event_loop()
            def solve():
                task = NoCaptchaTaskProxylessTask(page_url, site_key)
                job = self.anticaptcha_client.createTask(task)
                job.join()
                return job.get_solution_response()
            
            return await loop.run_in_executor(None, solve)
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
            # CapSolver API is synchronous, run in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.capsolver_client.recaptcha_v2_task_proxyless(
                    website_url=page_url,
                    website_key=site_key,
                )
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
                # CapSolver API is synchronous, run in thread pool
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: self.capsolver_client.hcaptcha_task_proxyless(
                        website_url=page_url,
                        website_key=site_key,
                    )
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
                # CapSolver API is synchronous, run in thread pool
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: self.capsolver_client.cloudflare_turnstile_task_proxyless(
                        website_url=page_url,
                        website_key=site_key,
                    )
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
        
        # Try free OCR first if AUTO or FREE
        if service in [CaptchaService.AUTO, CaptchaService.FREE]:
            result = await self._solve_image_captcha_ocr(image_data)
            if result:
                return result
        
        # Fallback to paid services if AUTO and free failed
        if service == CaptchaService.AUTO and self.anticaptcha_client:
            try:
                # AntiCaptcha API is synchronous, run in thread pool
                loop = asyncio.get_event_loop()
                def solve():
                    task = ImageToTextTask(image_data)
                    job = self.anticaptcha_client.createTask(task)
                    job.join()
                    return job.get_captcha_text()
                
                return await loop.run_in_executor(None, solve)
            except Exception as e:
                logger.error(f"AntiCaptcha image solving failed: {e}")
        
        if service == CaptchaService.ANTICAPTCHA and self.anticaptcha_client:
            try:
                loop = asyncio.get_event_loop()
                def solve():
                    task = ImageToTextTask(image_data)
                    job = self.anticaptcha_client.createTask(task)
                    job.join()
                    return job.get_captcha_text()
                
                return await loop.run_in_executor(None, solve)
            except Exception as e:
                logger.error(f"AntiCaptcha image solving failed: {e}")
                return None
        
        logger.warning("Image CAPTCHA solving not available with current service")
        return None
    
    async def _solve_image_captcha_ocr(self, image_data: bytes) -> Optional[str]:
        """Solve image CAPTCHA using free OCR (pytesseract or EasyOCR).
        
        Args:
            image_data: CAPTCHA image bytes
            
        Returns:
            Solution text or None if failed
        """
        try:
            loop = asyncio.get_event_loop()
            
            def solve_with_pytesseract():
                """Solve using pytesseract."""
                if not OCR_AVAILABLE:
                    return None
                try:
                    image = Image.open(io.BytesIO(image_data))
                    # Preprocess image for better OCR
                    # Convert to grayscale
                    if image.mode != 'L':
                        image = image.convert('L')
                    # Enhance contrast
                    from PIL import ImageEnhance
                    enhancer = ImageEnhance.Contrast(image)
                    image = enhancer.enhance(2.0)
                    
                    # Use OCR
                    text = pytesseract.image_to_string(image, config='--psm 7 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz')
                    return text.strip()
                except Exception as e:
                    logger.debug(f"pytesseract OCR failed: {e}")
                    return None
            
            def solve_with_easyocr():
                """Solve using EasyOCR."""
                if not EASYOCR_AVAILABLE:
                    return None
                try:
                    import easyocr
                    reader = easyocr.Reader(['en'], gpu=False)
                    result = reader.readtext(image_data)
                    if result:
                        # Combine all detected text
                        text = ' '.join([item[1] for item in result])
                        return text.strip()
                except Exception as e:
                    logger.debug(f"EasyOCR failed: {e}")
                    return None
                return None
            
            # Try pytesseract first (faster)
            if OCR_AVAILABLE:
                result = await loop.run_in_executor(None, solve_with_pytesseract)
                if result:
                    logger.info(f"OCR solved CAPTCHA: {result}")
                    return result
            
            # Fallback to EasyOCR
            if EASYOCR_AVAILABLE:
                result = await loop.run_in_executor(None, solve_with_easyocr)
                if result:
                    logger.info(f"EasyOCR solved CAPTCHA: {result}")
                    return result
            
        except Exception as e:
            logger.debug(f"Free OCR solving failed: {e}")
        
        return None
    
    def is_available(self) -> bool:
        """Check if any CAPTCHA solving service is available."""
        # Browser automation is always available (uses Playwright which is required)
        browser_automation_available = True
        # OCR for image CAPTCHAs (optional)
        ocr_available = OCR_AVAILABLE or EASYOCR_AVAILABLE
        # Paid services (optional)
        paid_available = (self.anticaptcha_client is not None) or (self.capsolver_client is not None)
        
        # Always available if browser automation works (for reCAPTCHA v2)
        return browser_automation_available or ocr_available or paid_available


# Global instance
_captcha_solver = None

def get_captcha_solver(
    anticaptcha_key: Optional[str] = None,
    capsolver_key: Optional[str] = None,
    use_free_methods: bool = True,
) -> Optional[CaptchaSolver]:
    """Get global CAPTCHA solver instance.
    
    Args:
        anticaptcha_key: AntiCaptcha API key
        capsolver_key: CapSolver API key
        use_free_methods: If True, return solver even without API keys (uses free methods)
    
    Returns:
        CaptchaSolver instance or None if no methods available
    """
    global _captcha_solver
    
    # Initialize from environment if not provided
    import os
    anticaptcha_key = anticaptcha_key or os.getenv("ANTICAPTCHA_API_KEY")
    capsolver_key = capsolver_key or os.getenv("CAPSOLVER_API_KEY")
    
    # If no API keys and free methods not enabled, return None
    if not anticaptcha_key and not capsolver_key and not use_free_methods:
        return None
    
    # Always create solver if free methods are enabled or API keys exist
    if _captcha_solver is None:
        _captcha_solver = CaptchaSolver(
            anticaptcha_key=anticaptcha_key,
            capsolver_key=capsolver_key,
            default_service=CaptchaService.AUTO if (anticaptcha_key or capsolver_key) else CaptchaService.FREE,
        )
    
    # Return solver if it has any available methods
    if _captcha_solver.is_available():
        return _captcha_solver
    
    return None

