"""Request Analyzer for deep analysis of HTTP requests."""

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum
from urllib.parse import urlparse, parse_qs

from .interceptor import CapturedRequest

logger = logging.getLogger(__name__)


class AuthType(Enum):
    """Authentication type."""
    BEARER = "bearer"
    COOKIE = "cookie"
    API_KEY = "api_key"
    OAUTH = "oauth"
    BASIC = "basic"
    NONE = "none"


@dataclass
class PaginationInfo:
    """Pagination information."""
    
    type: str  # "offset", "cursor", "page"
    param_name: str
    current_value: Optional[Any] = None
    pattern: Optional[str] = None


@dataclass
class FilterParam:
    """Filter parameter."""
    
    name: str
    value: Any
    type: str = "string"  # string, number, boolean, date


@dataclass
class AnalyzedRequest:
    """Deep analysis of a request."""
    
    url: str
    method: str
    headers: Dict[str, str]
    body: Any
    
    # Analysis results
    auth_type: AuthType = AuthType.NONE
    auth_token: Optional[str] = None
    pagination_params: Optional[PaginationInfo] = None
    filter_params: List[FilterParam] = field(default_factory=list)
    
    # Dependencies
    depends_on: List[str] = field(default_factory=list)  # URLs that must be called first
    provides: List[str] = field(default_factory=list)    # Data this request provides
    
    # Additional metadata
    is_api_call: bool = False
    content_type: Optional[str] = None
    base_url: str = ""
    path: str = ""


class RequestAnalyzer:
    """Analyzes requests for authentication, pagination, filters, etc."""
    
    def analyze(self, request: CapturedRequest) -> AnalyzedRequest:
        """Perform deep analysis on a request."""
        parsed_url = urlparse(request.url)
        
        analyzed = AnalyzedRequest(
            url=request.url,
            method=request.method,
            headers=request.headers,
            body=request.post_data,
            base_url=f"{parsed_url.scheme}://{parsed_url.netloc}",
            path=parsed_url.path,
        )
        
        # Detect content type
        analyzed.content_type = request.headers.get("Content-Type", "")
        
        # Detect if API call
        analyzed.is_api_call = self._is_api_call(request)
        
        # Analyze authentication
        auth_info = self._analyze_auth(request)
        analyzed.auth_type = auth_info["type"]
        analyzed.auth_token = auth_info.get("token")
        
        # Analyze pagination
        analyzed.pagination_params = self._analyze_pagination(request, parsed_url)
        
        # Analyze filters
        analyzed.filter_params = self._analyze_filters(request, parsed_url)
        
        # Extract dependencies (if body references other endpoints)
        analyzed.depends_on = self._extract_dependencies(request)
        
        return analyzed
    
    def _is_api_call(self, request: CapturedRequest) -> bool:
        """Determine if request is an API call."""
        url = request.url.lower()
        path = urlparse(url).path.lower()
        content_type = request.headers.get("Content-Type", "").lower()
        accept = request.headers.get("Accept", "").lower()
        
        api_indicators = [
            "/api/",
            "/v1/", "/v2/", "/v3/",
            "/graphql",
            "/rest/",
            ".json",
        ]
        
        # Check string indicators
        has_string_indicator = any(indicator in url or indicator in path for indicator in api_indicators)
        
        # Check content type indicators
        has_json_content = "application/json" in content_type or "application/json" in accept
        
        return has_string_indicator or has_json_content
    
    def _analyze_auth(self, request: CapturedRequest) -> Dict[str, Any]:
        """Analyze authentication mechanism."""
        headers = request.headers
        result = {"type": AuthType.NONE}
        
        # Check Authorization header
        auth_header = headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            result["type"] = AuthType.BEARER
            result["token"] = auth_header[7:]
        elif auth_header.startswith("Basic "):
            result["type"] = AuthType.BASIC
            result["token"] = auth_header[6:]
        
        # Check for API key in headers
        api_key_headers = ["X-API-Key", "API-Key", "X-Auth-Token", "Api-Key"]
        for key_header in api_key_headers:
            if key_header in headers:
                result["type"] = AuthType.API_KEY
                result["token"] = headers[key_header]
                break
        
        # Check cookies for session/auth tokens
        cookie_header = headers.get("Cookie", "")
        if any(name in cookie_header for name in ["session", "auth", "token", "jwt"]):
            result["type"] = AuthType.COOKIE
        
        # Check OAuth
        if "oauth" in auth_header.lower() or "token" in cookie_header.lower():
            if result["type"] == AuthType.NONE:
                result["type"] = AuthType.OAUTH
        
        return result
    
    def _analyze_pagination(
        self,
        request: CapturedRequest,
        parsed_url
    ) -> Optional[PaginationInfo]:
        """Analyze pagination parameters."""
        query_params = parse_qs(parsed_url.query)
        body_params = {}
        
        # Parse body if JSON
        if request.post_data:
            try:
                body_params = json.loads(request.post_data)
            except:
                pass
        
        # Common pagination parameter names
        offset_params = ["offset", "skip"]
        limit_params = ["limit", "count", "size", "per_page"]
        page_params = ["page", "page_number"]
        cursor_params = ["cursor", "next_token", "after", "before"]
        
        # Check for offset-based pagination
        for param in offset_params:
            if param in query_params:
                return PaginationInfo(
                    type="offset",
                    param_name=param,
                    current_value=query_params[param][0] if query_params[param] else None,
                )
            if isinstance(body_params, dict) and param in body_params:
                return PaginationInfo(
                    type="offset",
                    param_name=param,
                    current_value=body_params[param],
                )
        
        # Check for page-based pagination
        for param in page_params:
            if param in query_params:
                return PaginationInfo(
                    type="page",
                    param_name=param,
                    current_value=query_params[param][0] if query_params[param] else None,
                )
            if isinstance(body_params, dict) and param in body_params:
                return PaginationInfo(
                    type="page",
                    param_name=param,
                    current_value=body_params[param],
                )
        
        # Check for cursor-based pagination
        for param in cursor_params:
            if param in query_params:
                return PaginationInfo(
                    type="cursor",
                    param_name=param,
                    current_value=query_params[param][0] if query_params[param] else None,
                )
            if isinstance(body_params, dict) and param in body_params:
                return PaginationInfo(
                    type="cursor",
                    param_name=param,
                    current_value=body_params[param],
                )
        
        return None
    
    def _analyze_filters(
        self,
        request: CapturedRequest,
        parsed_url
    ) -> List[FilterParam]:
        """Analyze filter parameters."""
        filters = []
        query_params = parse_qs(parsed_url.query)
        body_params = {}
        
        if request.post_data:
            try:
                body_params = json.loads(request.post_data)
            except:
                pass
        
        # Common filter parameter patterns
        filter_keywords = [
            "filter", "where", "search", "q", "query",
            "sort", "order", "orderby",
            "from", "to", "start", "end",
            "min", "max", "range",
        ]
        
        # Check query params
        for param, values in query_params.items():
            param_lower = param.lower()
            if any(keyword in param_lower for keyword in filter_keywords):
                filters.append(FilterParam(
                    name=param,
                    value=values[0] if values else None,
                ))
        
        # Check body params
        if isinstance(body_params, dict):
            for key, value in body_params.items():
                key_lower = key.lower()
                if any(keyword in key_lower for keyword in filter_keywords):
                    filters.append(FilterParam(
                        name=key,
                        value=value,
                    ))
        
        return filters
    
    def _extract_dependencies(self, request: CapturedRequest) -> List[str]:
        """Extract dependencies (other endpoints this request depends on)."""
        dependencies = []
        
        # Parse body for URL references
        if request.post_data:
            try:
                data = json.loads(request.post_data)
                # Look for URL-like strings in the data
                if isinstance(data, dict):
                    for value in data.values():
                        if isinstance(value, str) and ("http://" in value or "https://" in value):
                            dependencies.append(value)
            except:
                pass
        
        return dependencies


