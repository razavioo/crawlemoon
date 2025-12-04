"""Sitemap and robots.txt analyzer."""

import logging
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)


@dataclass
class SitemapEntry:
    """Sitemap entry."""
    
    url: str
    lastmod: Optional[str] = None
    changefreq: Optional[str] = None
    priority: Optional[float] = None


@dataclass
class RobotsRule:
    """Robots.txt rule."""
    
    user_agent: str
    allow: List[str] = field(default_factory=list)
    disallow: List[str] = field(default_factory=list)
    crawl_delay: Optional[float] = None


@dataclass
class SitemapAnalysis:
    """Sitemap analysis results."""
    
    sitemap_url: str
    entries: List[SitemapEntry] = field(default_factory=list)
    sitemap_type: str = "sitemap"  # sitemap, sitemap_index, rss
    total_urls: int = 0
    errors: List[str] = field(default_factory=list)


@dataclass
class RobotsAnalysis:
    """Robots.txt analysis results."""
    
    robots_url: str
    rules: List[RobotsRule] = field(default_factory=list)
    sitemaps: List[str] = field(default_factory=list)
    valid: bool = True
    errors: List[str] = field(default_factory=list)


class SitemapAnalyzer:
    """Analyzes sitemaps and robots.txt files."""
    
    async def analyze_sitemap(self, sitemap_url: str) -> SitemapAnalysis:
        """Analyze a sitemap.xml file."""
        analysis = SitemapAnalysis(sitemap_url=sitemap_url)
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(sitemap_url)
                response.raise_for_status()
                content = response.text
            
            # Parse XML
            try:
                root = ET.fromstring(content)
            except ET.ParseError as e:
                analysis.errors.append(f"XML parse error: {e}")
                return analysis
            
            # Check if it's a sitemap index
            if root.tag.endswith('sitemapindex'):
                analysis.sitemap_type = "sitemap_index"
                # Extract sitemap URLs
                for sitemap_elem in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap'):
                    loc_elem = sitemap_elem.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
                    if loc_elem is not None:
                        # Recursively analyze nested sitemap
                        nested_url = loc_elem.text
                        nested_analysis = await self.analyze_sitemap(nested_url)
                        analysis.entries.extend(nested_analysis.entries)
                        analysis.total_urls += nested_analysis.total_urls
                        if nested_analysis.errors:
                            analysis.errors.extend(nested_analysis.errors)
            
            # Regular sitemap
            elif root.tag.endswith('urlset'):
                analysis.sitemap_type = "sitemap"
                namespace = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
                
                for url_elem in root.findall(f'.//{namespace}url'):
                    loc_elem = url_elem.find(f'{namespace}loc')
                    if loc_elem is not None:
                        entry = SitemapEntry(url=loc_elem.text)
                        
                        # Extract optional fields
                        lastmod_elem = url_elem.find(f'{namespace}lastmod')
                        if lastmod_elem is not None:
                            entry.lastmod = lastmod_elem.text
                        
                        changefreq_elem = url_elem.find(f'{namespace}changefreq')
                        if changefreq_elem is not None:
                            entry.changefreq = changefreq_elem.text
                        
                        priority_elem = url_elem.find(f'{namespace}priority')
                        if priority_elem is not None:
                            try:
                                entry.priority = float(priority_elem.text)
                            except ValueError:
                                pass
                        
                        analysis.entries.append(entry)
                        analysis.total_urls += 1
            
            # RSS feed (sometimes used as sitemap)
            elif root.tag == 'rss' or root.tag.endswith('rss'):
                analysis.sitemap_type = "rss"
                # Extract URLs from RSS items
                for item in root.findall('.//item'):
                    link_elem = item.find('link')
                    if link_elem is not None:
                        entry = SitemapEntry(url=link_elem.text)
                        analysis.entries.append(entry)
                        analysis.total_urls += 1
        
        except Exception as e:
            analysis.errors.append(f"Error analyzing sitemap: {e}")
            logger.error(f"Error analyzing sitemap {sitemap_url}: {e}", exc_info=True)
        
        return analysis
    
    async def analyze_robots(self, base_url: str) -> RobotsAnalysis:
        """Analyze robots.txt file."""
        parsed = urlparse(base_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        
        analysis = RobotsAnalysis(robots_url=robots_url)
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(robots_url)
                response.raise_for_status()
                content = response.text
            
            # Parse robots.txt
            current_agent = "*"
            rules: Dict[str, RobotsRule] = {}
            
            for line in content.split('\n'):
                line = line.strip()
                
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                
                # Parse directive
                if ':' in line:
                    directive, value = line.split(':', 1)
                    directive = directive.strip().lower()
                    value = value.strip()
                    
                    if directive == 'user-agent':
                        current_agent = value
                        if current_agent not in rules:
                            rules[current_agent] = RobotsRule(user_agent=current_agent)
                    
                    elif directive == 'allow':
                        if current_agent in rules:
                            rules[current_agent].allow.append(value)
                    
                    elif directive == 'disallow':
                        if current_agent in rules:
                            rules[current_agent].disallow.append(value)
                    
                    elif directive == 'crawl-delay':
                        if current_agent in rules:
                            try:
                                rules[current_agent].crawl_delay = float(value)
                            except ValueError:
                                pass
                    
                    elif directive == 'sitemap':
                        analysis.sitemaps.append(value)
            
            analysis.rules = list(rules.values())
        
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                analysis.errors.append("robots.txt not found")
            else:
                analysis.errors.append(f"HTTP error: {e.response.status_code}")
        except Exception as e:
            analysis.errors.append(f"Error analyzing robots.txt: {e}")
            analysis.valid = False
            logger.error(f"Error analyzing robots.txt {robots_url}: {e}", exc_info=True)
        
        return analysis
    
    def check_url_allowed(self, robots_analysis: RobotsAnalysis, url: str, user_agent: str = "*") -> bool:
        """Check if a URL is allowed by robots.txt rules."""
        parsed = urlparse(url)
        path = parsed.path
        
        # Find matching rule
        matching_rule = None
        for rule in robots_analysis.rules:
            if rule.user_agent == user_agent or rule.user_agent == "*":
                matching_rule = rule
                break
        
        if not matching_rule:
            return True  # No rules = allowed
        
        # Check disallow first (more specific)
        for disallow_path in matching_rule.disallow:
            if path.startswith(disallow_path):
                # Check if there's a more specific allow
                for allow_path in matching_rule.allow:
                    if path.startswith(allow_path) and len(allow_path) > len(disallow_path):
                        return True
                return False
        
        return True

