"""GraphQL specific utilities."""

import logging
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)


class GraphQLClient:
    """GraphQL client for introspection and queries."""
    
    def __init__(self, endpoint: str):
        self.endpoint = endpoint
    
    async def introspect(self) -> Optional[Dict[str, Any]]:
        """Run GraphQL introspection."""
        from ..network.api_discovery import APIDiscoveryEngine
        
        discovery = APIDiscoveryEngine()
        return await discovery.run_introspection(self.endpoint)
    
    async def query(self, query: str, variables: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        """Execute a GraphQL query."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.endpoint,
                    json={
                        "query": query,
                        "variables": variables or {},
                    },
                    timeout=30.0,
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"GraphQL query failed: {response.status_code}")
                    return None
        
        except Exception as e:
            logger.error(f"Error executing GraphQL query: {e}")
            return None


