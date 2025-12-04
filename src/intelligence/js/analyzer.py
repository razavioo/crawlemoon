"""Static JavaScript code analyzer with AST support."""

import re
import logging
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field

try:
    import esprima
    ESPRIMA_AVAILABLE = True
except ImportError:
    ESPRIMA_AVAILABLE = False
    logger.warning("esprima not available, falling back to regex-based analysis")

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
    """Static JavaScript code analyzer with AST and regex support."""
    
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
    
    def _extract_from_ast(self, code: str) -> Dict[str, Any]:
        """Extract information using AST parsing."""
        if not ESPRIMA_AVAILABLE:
            return {}
        
        try:
            tree = esprima.parseScript(code, {'loc': True, 'tolerant': True})
            return self._analyze_ast(tree)
        except Exception as e:
            logger.debug(f"AST parsing failed: {e}, falling back to regex")
            return {}
    
    def _analyze_ast(self, tree: Any) -> Dict[str, Any]:
        """Analyze AST tree to extract API calls and patterns."""
        api_calls = []
        urls = []
        constants = {}
        auth_patterns = []
        
        def visit_node(node: Any, parent: Any = None):
            """Recursively visit AST nodes."""
            if not node or not hasattr(node, 'type'):
                return
            
            node_type = node.type
            
            # Extract API calls
            if node_type == 'CallExpression':
                callee = node.callee
                
                # Fetch calls
                if callee.type == 'Identifier' and callee.name == 'fetch':
                    if node.arguments and len(node.arguments) > 0:
                        arg = node.arguments[0]
                        if arg.type == 'Literal' and isinstance(arg.value, str):
                            method = 'GET'
                            if len(node.arguments) > 1:
                                options = node.arguments[1]
                                if options.type == 'ObjectExpression':
                                    for prop in options.properties:
                                        if prop.key.name == 'method' and prop.value.type == 'Literal':
                                            method = prop.value.value
                            
                            api_calls.append({
                                'url': arg.value,
                                'method': method,
                                'type': 'fetch',
                                'line': arg.loc.start.line if hasattr(arg, 'loc') else None,
                            })
                
                # Axios calls
                if (callee.type == 'MemberExpression' and 
                    callee.object.type == 'Identifier' and 
                    callee.object.name == 'axios'):
                    method = callee.property.name.upper() if hasattr(callee.property, 'name') else 'GET'
                    if node.arguments and len(node.arguments) > 0:
                        arg = node.arguments[0]
                        if arg.type == 'Literal' and isinstance(arg.value, str):
                            api_calls.append({
                                'url': arg.value,
                                'method': method,
                                'type': 'axios',
                                'line': arg.loc.start.line if hasattr(arg, 'loc') else None,
                            })
                
                # XHR.open calls
                if (callee.type == 'MemberExpression' and
                    callee.property.type == 'Identifier' and
                    callee.property.name == 'open'):
                    if len(node.arguments) >= 2:
                        method = node.arguments[0].value if node.arguments[0].type == 'Literal' else 'GET'
                        url = node.arguments[1].value if node.arguments[1].type == 'Literal' else None
                        if url:
                            api_calls.append({
                                'url': url,
                                'method': method,
                                'type': 'xhr',
                                'line': node.arguments[1].loc.start.line if hasattr(node.arguments[1], 'loc') else None,
                            })
            
            # Extract URLs from string literals
            if node_type == 'Literal' and isinstance(node.value, str):
                if node.value.startswith(('http://', 'https://')):
                    urls.append(node.value)
            
            # Extract constants
            if node_type == 'VariableDeclarator':
                if node.id.type == 'Identifier' and node.init:
                    if node.init.type == 'Literal':
                        constants[node.id.name] = node.init.value
            
            # Extract auth patterns
            if node_type == 'MemberExpression':
                if (hasattr(node.object, 'name') and 
                    node.object.name in ('localStorage', 'sessionStorage') and
                    hasattr(node.property, 'name') and
                    node.property.name == 'setItem'):
                    auth_patterns.append('token_storage')
            
            # Recursively visit child nodes
            for key, value in vars(node).items():
                if key.startswith('_') or key in ('type', 'loc', 'range'):
                    continue
                if isinstance(value, list):
                    for item in value:
                        visit_node(item, node)
                elif isinstance(value, dict):
                    visit_node(value, node)
                elif hasattr(value, 'type'):
                    visit_node(value, node)
        
        visit_node(tree)
        
        return {
            'api_calls': api_calls,
            'urls': urls,
            'constants': constants,
            'auth_patterns': auth_patterns,
        }
    
    def extract_api_calls(self, code: str) -> List[APICall]:
        """Extract API calls from JavaScript code using AST and regex."""
        api_calls = []
        
        # Try AST first
        if ESPRIMA_AVAILABLE:
            try:
                ast_result = self._extract_from_ast(code)
                ast_calls = ast_result.get('api_calls', [])
                for call in ast_calls:
                    api_calls.append(APICall(
                        url=call['url'],
                        method=call.get('method', 'GET'),
                        type=call['type'],
                        line_number=call.get('line', 0),
                    ))
            except Exception as e:
                logger.debug(f"AST extraction failed: {e}, using regex fallback")
        
        # Fallback to regex if AST didn't work or not available
        if not api_calls:
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
        """Find hardcoded URLs in code using AST and regex."""
        urls = []
        
        # Try AST first
        if ESPRIMA_AVAILABLE:
            try:
                ast_result = self._extract_from_ast(code)
                urls.extend(ast_result.get('urls', []))
            except Exception:
                pass
        
        # Fallback to regex
        for match in self.url_pattern.finditer(code):
            url = match.group(1)
            if url.startswith(('http://', 'https://')):
                urls.append(url)
        
        return list(set(urls))  # Remove duplicates
    
    def extract_constants(self, code: str) -> Dict[str, Any]:
        """Extract constants and configuration values using AST and regex."""
        constants = {}
        
        # Try AST first
        if ESPRIMA_AVAILABLE:
            try:
                ast_result = self._extract_from_ast(code)
                constants.update(ast_result.get('constants', {}))
            except Exception:
                pass
        
        # Fallback to regex
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



