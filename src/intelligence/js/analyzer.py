"""Static JavaScript code analyzer."""

import re
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class APICall:
    """API call found in JavaScript."""
    
    url: str
    method: str
    type: str  # "fetch", "xhr", "axios", "jquery"
    line_number: int


@dataclass
class AuthFlowDefinition:
    """Authentication flow definition."""
    
    flow_type: str
    token_storage: str
    refresh_mechanism: Optional[str] = None


class JSAnalyzer:
    """Static JavaScript code analyzer."""
    
    def __init__(self):
        # URL patterns
        self.url_pattern = re.compile(
            r'["\'](https?://[^"\']+)["\']',
            re.IGNORECASE
        )
        
        # API call patterns
        self.fetch_pattern = re.compile(
            r'fetch\s*\(\s*["\']([^"\']+)["\']',
            re.IGNORECASE
        )
        
        self.xhr_pattern = re.compile(
            r'\.open\s*\(\s*["\']([A-Z]+)["\']\s*,\s*["\']([^"\']+)["\']',
            re.IGNORECASE
        )
        
        self.axios_pattern = re.compile(
            r'axios\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']',
            re.IGNORECASE
        )
    
    def extract_api_calls(self, code: str) -> List[APICall]:
        """Extract API calls from JavaScript code."""
        api_calls = []
        lines = code.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            # Check for fetch
            for match in self.fetch_pattern.finditer(line):
                api_calls.append(APICall(
                    url=match.group(1),
                    method="GET",  # Default, could be enhanced
                    type="fetch",
                    line_number=line_num,
                ))
            
            # Check for XHR
            for match in self.xhr_pattern.finditer(line):
                api_calls.append(APICall(
                    url=match.group(2),
                    method=match.group(1),
                    type="xhr",
                    line_number=line_num,
                ))
            
            # Check for axios
            for match in self.axios_pattern.finditer(line):
                api_calls.append(APICall(
                    url=match.group(2),
                    method=match.group(1).upper(),
                    type="axios",
                    line_number=line_num,
                ))
        
        logger.info(f"Extracted {len(api_calls)} API calls")
        return api_calls
    
    def find_hardcoded_urls(self, code: str) -> List[str]:
        """Find hardcoded URLs in code."""
        urls = []
        
        for match in self.url_pattern.finditer(code):
            url = match.group(1)
            if url.startswith(('http://', 'https://')):
                urls.append(url)
        
        return list(set(urls))  # Remove duplicates
    
    def extract_constants(self, code: str) -> Dict[str, Any]:
        """Extract constants and configuration values."""
        constants = {}
        
        # Pattern for const/let/var declarations
        const_pattern = re.compile(
            r'(?:const|let|var)\s+(\w+)\s*=\s*["\']([^"\']+)["\']',
            re.IGNORECASE
        )
        
        for match in const_pattern.finditer(code):
            constants[match.group(1)] = match.group(2)
        
        return constants
    
    def find_auth_logic(self, code: str) -> Optional[AuthFlowDefinition]:
        """Find authentication logic in code."""
        # Look for token storage patterns
        if 'localStorage.setItem' in code or 'sessionStorage.setItem' in code:
            storage_match = re.search(
                r'(localStorage|sessionStorage)\.setItem\s*\([^,]+,\s*["\']([^"\']+)["\']',
                code
            )
            
            if storage_match:
                return AuthFlowDefinition(
                    flow_type="token-based",
                    token_storage=storage_match.group(1),
                )
        
        # Look for OAuth patterns
        if 'oauth' in code.lower() or 'access_token' in code.lower():
            return AuthFlowDefinition(
                flow_type="oauth",
                token_storage="unknown",
            )
        
        return None


