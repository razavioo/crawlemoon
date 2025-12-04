"""JavaScript deobfuscation engine."""

import logging
from typing import Dict
from enum import Enum

logger = logging.getLogger(__name__)


class ObfuscationType(Enum):
    """Obfuscation type."""
    STRING_ENCODING = "string_encoding"
    CONTROL_FLOW_FLATTENING = "control_flow_flattening"
    NAME_MANGLING = "name_mangling"
    DEAD_CODE = "dead_code"
    UNKNOWN = "unknown"


class JSDeobfuscator:
    """JavaScript deobfuscator."""
    
    def detect_obfuscation_type(self, code: str) -> ObfuscationType:
        """Detect obfuscation type in code."""
        # Heuristics for detection
        if "eval" in code and "atob" in code:
            return ObfuscationType.STRING_ENCODING
        
        if "while" in code and "switch" in code and code.count("case") > 10:
            return ObfuscationType.CONTROL_FLOW_FLATTENING
        
        if code.replace(" ", "").replace("\n", "")[:50].isalnum():
            # Very short variable names might indicate name mangling
            return ObfuscationType.NAME_MANGLING
        
        return ObfuscationType.UNKNOWN
    
    def deobfuscate_strings(self, code: str) -> str:
        """Deobfuscate encoded strings."""
        import re
        import base64
        
        deobfuscated = code
        
        # Try to decode base64 encoded strings
        # Look for patterns like atob("...") or Buffer.from("...", "base64")
        base64_pattern = r'atob\(["\']([A-Za-z0-9+/=]+)["\']\)'
        matches = re.finditer(base64_pattern, deobfuscated)
        
        for match in list(matches):
            try:
                encoded = match.group(1)
                decoded = base64.b64decode(encoded).decode('utf-8', errors='ignore')
                deobfuscated = deobfuscated.replace(match.group(0), f'"{decoded}"')
            except:
                pass
        
        # Try to decode hex encoded strings
        hex_pattern = r'["\']([0-9a-fA-F]+)["\']\.replace\(/\.\.\./g,'
        matches = re.finditer(hex_pattern, deobfuscated)
        for match in list(matches):
            try:
                hex_str = match.group(1)
                decoded = bytes.fromhex(hex_str).decode('utf-8', errors='ignore')
                deobfuscated = deobfuscated.replace(match.group(0), f'"{decoded}"')
            except:
                pass
        
        # Replace eval() with direct execution where possible
        # This is a simplified version - full implementation would use AST
        eval_pattern = r'eval\(["\']([^"\']+)["\']\)'
        matches = re.finditer(eval_pattern, deobfuscated)
        for match in list(matches):
            try:
                eval_code = match.group(1)
                # Only replace if it's a simple string literal
                if not any(char in eval_code for char in ['+', '(', ')', '{', '}']):
                    deobfuscated = deobfuscated.replace(match.group(0), eval_code)
            except:
                pass
        
        logger.info(f"Deobfuscated strings (original: {len(code)} chars, deobfuscated: {len(deobfuscated)} chars)")
        return deobfuscated
    
    def simplify_control_flow(self, code: str) -> str:
        """Simplify obfuscated control flow."""
        import re
        
        simplified = code
        
        # Remove dead code patterns (unreachable code after return/throw)
        # This is a basic implementation - full version would use AST analysis
        lines = simplified.split('\n')
        cleaned_lines = []
        skip_until_brace = False
        brace_count = 0
        
        for line in lines:
            # Simple dead code removal after return/throw
            if re.search(r'\breturn\b|\bthrow\b', line):
                cleaned_lines.append(line)
                # Check if there's code after return on same line
                if ';' in line and not line.strip().endswith(';'):
                    # Has code after return - keep return part only
                    return_match = re.search(r'(.*?(?:return|throw)[^;]+;)', line)
                    if return_match:
                        cleaned_lines[-1] = return_match.group(1)
            else:
                cleaned_lines.append(line)
        
        simplified = '\n'.join(cleaned_lines)
        
        # Remove redundant while(true) { switch() } patterns
        # This is simplified - full implementation would reconstruct control flow
        while_true_pattern = r'while\s*\(\s*true\s*\)\s*\{[^}]*switch\s*\([^)]+\)\s*\{[^}]*\}'
        simplified = re.sub(while_true_pattern, '', simplified, flags=re.DOTALL)
        
        logger.info(f"Simplified control flow (original: {len(code)} chars, simplified: {len(simplified)} chars)")
        return simplified
    
    def extract_original_names(self, code: str) -> Dict[str, str]:
        """Extract original variable/function names."""
        import re
        
        name_map = {}
        
        # Look for common obfuscation patterns
        # Pattern: var _0x1234 = ['value1', 'value2', ...]
        hex_var_pattern = r'var\s+(_0x[a-f0-9]+)\s*=\s*\[([^\]]+)\]'
        matches = re.finditer(hex_var_pattern, code)
        
        for match in matches:
            var_name = match.group(1)
            values_str = match.group(2)
            # Extract string values
            string_values = re.findall(r'["\']([^"\']+)["\']', values_str)
            if string_values:
                # Try to map to meaningful names
                for i, value in enumerate(string_values):
                    if value and len(value) > 2:
                        # Use first meaningful string as potential original name
                        name_map[var_name] = value
                        break
        
        # Pattern: function names that look obfuscated
        obfuscated_func_pattern = r'function\s+([a-z_$][a-z0-9_$]{1,3})\s*\('
        matches = re.finditer(obfuscated_func_pattern, code)
        for match in matches:
            func_name = match.group(1)
            if len(func_name) <= 3 and func_name not in ['get', 'set', 'has', 'add', 'put']:
                # Likely obfuscated - try to find context
                name_map[func_name] = f"obfuscated_{func_name}"
        
        return name_map

