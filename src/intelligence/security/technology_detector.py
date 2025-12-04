"""Technology stack detection using Wappalyzer."""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

try:
    from Wappalyzer import Wappalyzer, WebPage
    WAPPALYZER_AVAILABLE = True
except ImportError:
    WAPPALYZER_AVAILABLE = False
    Wappalyzer = None
    WebPage = None

logger = logging.getLogger(__name__)


@dataclass
class TechnologyInfo:
    """Detected technology information."""
    
    name: str
    category: str
    confidence: int
    version: Optional[str] = None
    website: Optional[str] = None
    cpe: Optional[str] = None


@dataclass
class TechnologyStack:
    """Complete technology stack for a website."""
    
    cms: List[TechnologyInfo] = None
    frameworks: List[TechnologyInfo] = None
    programming_languages: List[TechnologyInfo] = None
    web_servers: List[TechnologyInfo] = None
    databases: List[TechnologyInfo] = None
    cdn: List[TechnologyInfo] = None
    analytics: List[TechnologyInfo] = None
    advertising: List[TechnologyInfo] = None
    javascript_libraries: List[TechnologyInfo] = None
    other: List[TechnologyInfo] = None
    
    def __post_init__(self):
        if self.cms is None:
            self.cms = []
        if self.frameworks is None:
            self.frameworks = []
        if self.programming_languages is None:
            self.programming_languages = []
        if self.web_servers is None:
            self.web_servers = []
        if self.databases is None:
            self.databases = []
        if self.cdn is None:
            self.cdn = []
        if self.analytics is None:
            self.analytics = []
        if self.advertising is None:
            self.advertising = []
        if self.javascript_libraries is None:
            self.javascript_libraries = []
        if self.other is None:
            self.other = []


class TechnologyDetector:
    """Detect technology stack of websites."""
    
    def __init__(self):
        """Initialize technology detector."""
        self.wappalyzer = None
        if WAPPALYZER_AVAILABLE:
            try:
                self.wappalyzer = Wappalyzer.latest()
            except Exception as e:
                logger.warning(f"Failed to initialize Wappalyzer: {e}")
    
    def detect(
        self,
        html: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> TechnologyStack:
        """Detect technologies from HTML and headers.
        
        Args:
            html: HTML content
            url: Page URL
            headers: Optional HTTP headers
            
        Returns:
            TechnologyStack object
        """
        stack = TechnologyStack()
        
        if not self.wappalyzer:
            logger.warning("Wappalyzer not available")
            return stack
        
        try:
            # Create WebPage object
            webpage = WebPage.new_from_html(html, url)
            
            # Analyze
            technologies = self.wappalyzer.analyze_with_versions_and_categories(webpage)
            
            # Categorize technologies
            category_map = {
                'CMS': stack.cms,
                'Web frameworks': stack.frameworks,
                'Programming languages': stack.programming_languages,
                'Web servers': stack.web_servers,
                'Databases': stack.databases,
                'CDN': stack.cdn,
                'Analytics': stack.analytics,
                'Advertising': stack.advertising,
                'JavaScript libraries': stack.javascript_libraries,
            }
            
            for tech_name, tech_data in technologies.items():
                tech_info = TechnologyInfo(
                    name=tech_name,
                    category=tech_data.get('categories', ['Other'])[0] if tech_data.get('categories') else 'Other',
                    confidence=100,  # Wappalyzer doesn't provide confidence scores
                    version=tech_data.get('version'),
                    website=tech_data.get('website'),
                    cpe=tech_data.get('cpe'),
                )
                
                # Categorize
                categorized = False
                for category, tech_list in category_map.items():
                    if tech_info.category == category:
                        tech_list.append(tech_info)
                        categorized = True
                        break
                
                if not categorized:
                    stack.other.append(tech_info)
        
        except Exception as e:
            logger.error(f"Error detecting technologies: {e}")
        
        return stack
    
    def detect_from_response(
        self,
        response,
        url: Optional[str] = None,
    ) -> TechnologyStack:
        """Detect technologies from HTTP response.
        
        Args:
            response: HTTP response object (with .text and .headers)
            url: Optional URL (extracted from response if not provided)
            
        Returns:
            TechnologyStack object
        """
        if not url:
            url = getattr(response, 'url', '')
        
        headers = dict(getattr(response, 'headers', {}))
        html = getattr(response, 'text', '')
        
        return self.detect(html, url, headers)
    
    def get_protection_technologies(self, stack: TechnologyStack) -> List[str]:
        """Extract protection/security technologies from stack.
        
        Args:
            stack: TechnologyStack object
            
        Returns:
            List of protection technology names
        """
        protection_keywords = [
            'cloudflare', 'akamai', 'imperva', 'datadome', 'perimeterx',
            'shape', 'kasada', 'recaptcha', 'hcaptcha', 'turnstile',
            'aws waf', 'sucuri', 'incapsula', 'f5', 'barracuda'
        ]
        
        protection_techs = []
        
        # Check all categories
        all_techs = (
            stack.cms + stack.frameworks + stack.web_servers +
            stack.cdn + stack.other
        )
        
        for tech in all_techs:
            name_lower = tech.name.lower()
            if any(keyword in name_lower for keyword in protection_keywords):
                protection_techs.append(tech.name)
        
        return protection_techs


# Global instance
_technology_detector = None

def get_technology_detector() -> TechnologyDetector:
    """Get global technology detector instance."""
    global _technology_detector
    if _technology_detector is None:
        _technology_detector = TechnologyDetector()
    return _technology_detector

