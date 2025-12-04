"""API Discovery Engine for REST, GraphQL, and hidden APIs."""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
from urllib.parse import urlparse, parse_qs
from enum import Enum

from .interceptor import CapturedRequest, CapturedResponse

logger = logging.getLogger(__name__)


class APIType(Enum):
    """API type."""
    REST = "rest"
    GraphQL = "graphql"
    GRPC = "grpc"
    WebSocket = "websocket"
    UNKNOWN = "unknown"


@dataclass
class RESTEndpoint:
    """REST API endpoint."""
    
    url: str
    method: str
    path: str
    base_url: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    example_request: Optional[Dict] = None
    example_response: Optional[Dict] = None


@dataclass
class GraphQLEndpoint:
    """GraphQL endpoint."""
    
    url: str
    schema_url: Optional[str] = None
    introspection_enabled: bool = False
    queries: List[str] = field(default_factory=list)
    mutations: List[str] = field(default_factory=list)
    subscriptions: List[str] = field(default_factory=list)


@dataclass
class Operation:
    """GraphQL operation."""
    
    name: str
    type: str  # "query", "mutation", "subscription"
    fields: List[str]
    variables: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InternalAPI:
    """Internal or undocumented API."""
    
    url: str
    method: str
    evidence: List[str] = field(default_factory=list)  # Why it's considered internal
    confidence: float = 0.0  # 0-1


@dataclass
class OpenAPISpec:
    """OpenAPI specification."""
    
    endpoints: List[RESTEndpoint]
    base_url: str
    version: Optional[str] = None


class APIDiscoveryEngine:
    """Discovers APIs from network traffic."""
    
    def __init__(self):
        self.discovered_apis: List[RESTEndpoint] = []
        self.graphql_endpoints: List[GraphQLEndpoint] = []
        self.internal_apis: List[InternalAPI] = []
        
        # Patterns for API detection
        self.api_path_patterns = [
            r"/api/",
            r"/v\d+/",
            r"/graphql",
            r"/rest/",
            r"\.json",
            r"\.xml",
        ]
        
        self.graphql_patterns = [
            r"query\s+\w+",
            r"mutation\s+\w+",
            r"__typename",
            r"__schema",
        ]
    
    def detect_rest_endpoints(
        self,
        requests: List[CapturedRequest],
        responses: List[CapturedResponse]
    ) -> List[RESTEndpoint]:
        """Detect REST API endpoints from requests."""
        endpoints: Dict[str, RESTEndpoint] = {}
        
        for req in requests:
            url = req.url
            parsed = urlparse(url)
            path = parsed.path
            
            # Check if looks like API endpoint
            if not self._is_api_path(path):
                continue
            
            # Extract base URL
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            
            # Create endpoint key
            endpoint_key = f"{req.method}:{path}"
            
            if endpoint_key not in endpoints:
                # Extract path parameters (e.g., /users/{id})
                path_params = self._extract_path_parameters(path)
                query_params = parse_qs(parsed.query)
                
                endpoint = RESTEndpoint(
                    url=url,
                    method=req.method,
                    path=path,
                    base_url=base_url,
                    parameters={"path": path_params, "query": query_params},
                    headers=req.headers,
                )
                
                endpoints[endpoint_key] = endpoint
            
            # Add example request/response
            endpoint = endpoints[endpoint_key]
            if not endpoint.example_request:
                endpoint.example_request = {
                    "headers": req.headers,
                    "body": req.post_data,
                }
        
        # Match with responses
        for resp in responses:
            for endpoint in endpoints.values():
                if endpoint.url == resp.url or endpoint.path in resp.url:
                    if not endpoint.example_response:
                        endpoint.example_response = {
                            "status": resp.status,
                            "headers": resp.headers,
                        }
                    break
        
        self.discovered_apis = list(endpoints.values())
        logger.info(f"Discovered {len(self.discovered_apis)} REST endpoints")
        return self.discovered_apis
    
    def infer_rest_schema(self, endpoints: List[RESTEndpoint]) -> OpenAPISpec:
        """Infer OpenAPI schema from discovered endpoints."""
        if not endpoints:
            return OpenAPISpec(endpoints=[], base_url="")
        
        # Use common base URL
        base_urls = {}
        for endpoint in endpoints:
            base_urls[endpoint.base_url] = base_urls.get(endpoint.base_url, 0) + 1
        
        most_common_base = max(base_urls.items(), key=lambda x: x[1])[0]
        
        return OpenAPISpec(
            endpoints=endpoints,
            base_url=most_common_base,
        )
    
    def detect_graphql(
        self,
        requests: List[CapturedRequest],
        responses: List[CapturedResponse]
    ) -> Optional[GraphQLEndpoint]:
        """Detect GraphQL endpoint."""
        for req in requests:
            # Check URL
            if "/graphql" in req.url.lower() or "/gql" in req.url.lower():
                endpoint = GraphQLEndpoint(url=req.url)
                
                # Check if introspection is enabled
                if req.post_data:
                    if "__schema" in req.post_data or "introspection" in req.post_data.lower():
                        endpoint.introspection_enabled = True
                
                self.graphql_endpoints.append(endpoint)
                logger.info(f"Detected GraphQL endpoint: {req.url}")
                return endpoint
            
            # Check request body for GraphQL patterns
            if req.post_data:
                for pattern in self.graphql_patterns:
                    if re.search(pattern, req.post_data, re.IGNORECASE):
                        endpoint = GraphQLEndpoint(url=req.url)
                        self.graphql_endpoints.append(endpoint)
                        logger.info(f"Detected GraphQL endpoint via body analysis: {req.url}")
                        return endpoint
        
        return None
    
    async def run_introspection(self, endpoint_url: str) -> Optional[Dict]:
        """Run GraphQL introspection query."""
        import httpx
        
        introspection_query = """
        query IntrospectionQuery {
            __schema {
                queryType { name }
                mutationType { name }
                subscriptionType { name }
                types {
                    ...FullType
                }
            }
        }
        
        fragment FullType on __Type {
            kind
            name
            description
            fields(includeDeprecated: true) {
                name
                description
                args {
                    ...InputValue
                }
                type {
                    ...TypeRef
                }
                isDeprecated
                deprecationReason
            }
            inputFields {
                ...InputValue
            }
            interfaces {
                ...TypeRef
            }
            enumValues(includeDeprecated: true) {
                name
                description
                isDeprecated
                deprecationReason
            }
            possibleTypes {
                ...TypeRef
            }
        }
        
        fragment InputValue on __InputValue {
            name
            description
            type { ...TypeRef }
            defaultValue
        }
        
        fragment TypeRef on __Type {
            kind
            name
            ofType {
                kind
                name
                ofType {
                    kind
                    name
                    ofType {
                        kind
                        name
                        ofType {
                            kind
                            name
                            ofType {
                                kind
                                name
                                ofType {
                                    kind
                                    name
                                    ofType {
                                        kind
                                        name
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        """
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    endpoint_url,
                    json={"query": introspection_query},
                    timeout=10.0,
                )
                
                if response.status_code == 200:
                    data = response.json()
                    logger.info("GraphQL introspection successful")
                    return data
                else:
                    logger.warning(f"GraphQL introspection failed: {response.status_code}")
                    return None
        
        except Exception as e:
            logger.error(f"Error during GraphQL introspection: {e}")
            return None
    
    def extract_queries_mutations(self, schema: Dict) -> List[Operation]:
        """Extract queries and mutations from GraphQL schema."""
        operations = []
        
        try:
            schema_data = schema.get("data", {}).get("__schema", {})
            
            # Extract queries
            query_type = schema_data.get("queryType")
            if query_type:
                # This would need more parsing of the schema
                operations.append(Operation(
                    name="queries",
                    type="query",
                    fields=[],
                ))
            
            # Extract mutations
            mutation_type = schema_data.get("mutationType")
            if mutation_type:
                operations.append(Operation(
                    name="mutations",
                    type="mutation",
                    fields=[],
                ))
        
        except Exception as e:
            logger.error(f"Error extracting operations: {e}")
        
        return operations
    
    def find_undocumented_endpoints(
        self,
        requests: List[CapturedRequest],
        known_endpoints: Optional[List[str]] = None
    ) -> List[InternalAPI]:
        """Find undocumented or internal API endpoints."""
        known = set(known_endpoints or [])
        internal = []
        
        for req in requests:
            url = req.url
            parsed = urlparse(url)
            path = parsed.path
            
            # Skip if already known
            if url in known or path in known:
                continue
            
            evidence = []
            confidence = 0.0
            
            # Check for internal indicators
            if "/internal" in path.lower():
                evidence.append("Contains '/internal' in path")
                confidence += 0.3
            
            if "/private" in path.lower():
                evidence.append("Contains '/private' in path")
                confidence += 0.3
            
            if "api" in path.lower() and path not in [e.path for e in self.discovered_apis]:
                evidence.append("API-like path but not in discovered endpoints")
                confidence += 0.2
            
            # Check for non-standard ports
            if parsed.port and parsed.port not in [80, 443, 8080, 8443]:
                evidence.append(f"Non-standard port: {parsed.port}")
                confidence += 0.1
            
            if evidence and confidence > 0.3:
                internal_api = InternalAPI(
                    url=url,
                    method=req.method,
                    evidence=evidence,
                    confidence=min(confidence, 1.0),
                )
                internal.append(internal_api)
        
        self.internal_apis = internal
        logger.info(f"Found {len(internal)} undocumented endpoints")
        return internal
    
    def detect_internal_apis(
        self,
        requests: List[CapturedRequest]
    ) -> List[InternalAPI]:
        """Detect internal APIs based on various heuristics."""
        return self.find_undocumented_endpoints(requests)
    
    def _is_api_path(self, path: str) -> bool:
        """Check if path looks like an API endpoint."""
        for pattern in self.api_path_patterns:
            if re.search(pattern, path, re.IGNORECASE):
                return True
        return False
    
    def _extract_path_parameters(self, path: str) -> List[str]:
        """Extract parameter names from path (e.g., /users/{id} -> ['id'])."""
        # Simple regex to find {param} or :param patterns
        params = re.findall(r'[{:](\w+)', path)
        return params


