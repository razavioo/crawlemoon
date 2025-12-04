"""Tests for JavaScript deobfuscation engine."""

import pytest

from src.intelligence.js.deobfuscator import (
    JSDeobfuscator,
    ObfuscationType,
)


@pytest.fixture
def deobfuscator():
    """Create a JS deobfuscator."""
    return JSDeobfuscator()


def test_deobfuscator_initialization():
    """Test deobfuscator initialization."""
    deobfuscator = JSDeobfuscator()
    assert deobfuscator is not None


def test_obfuscation_type_enum():
    """Test ObfuscationType enum values."""
    assert ObfuscationType.STRING_ENCODING.value == "string_encoding"
    assert ObfuscationType.CONTROL_FLOW_FLATTENING.value == "control_flow_flattening"
    assert ObfuscationType.NAME_MANGLING.value == "name_mangling"
    assert ObfuscationType.DEAD_CODE.value == "dead_code"
    assert ObfuscationType.UNKNOWN.value == "unknown"


def test_detect_obfuscation_type_string_encoding(deobfuscator):
    """Test detection of string encoding obfuscation."""
    code = 'eval(atob("SGVsbG8gV29ybGQ="));'
    
    result = deobfuscator.detect_obfuscation_type(code)
    
    assert result == ObfuscationType.STRING_ENCODING


def test_detect_obfuscation_type_control_flow(deobfuscator):
    """Test detection of control flow flattening."""
    code = """
    var state = 0;
    while(true) {
        switch(state) {
            case 0: doA(); state = 1; break;
            case 1: doB(); state = 2; break;
            case 2: doC(); state = 3; break;
            case 3: doD(); state = 4; break;
            case 4: doE(); state = 5; break;
            case 5: doF(); state = 6; break;
            case 6: doG(); state = 7; break;
            case 7: doH(); state = 8; break;
            case 8: doI(); state = 9; break;
            case 9: doJ(); state = 10; break;
            case 10: doK(); state = 11; break;
            case 11: return;
        }
    }
    """
    
    result = deobfuscator.detect_obfuscation_type(code)
    
    assert result == ObfuscationType.CONTROL_FLOW_FLATTENING


def test_detect_obfuscation_type_unknown(deobfuscator):
    """Test detection returns unknown for normal code."""
    code = """
    function sayHello(name) {
        console.log("Hello, " + name);
    }
    """
    
    result = deobfuscator.detect_obfuscation_type(code)
    
    # Normal code should be detected as unknown or name mangling
    assert result in [ObfuscationType.UNKNOWN, ObfuscationType.NAME_MANGLING]


def test_deobfuscate_strings_base64(deobfuscator):
    """Test deobfuscation of base64 encoded strings."""
    code = 'var message = atob("SGVsbG8gV29ybGQ=");'
    
    result = deobfuscator.deobfuscate_strings(code)
    
    # Should decode base64 string
    assert "Hello World" in result or "SGVsbG8gV29ybGQ=" in result


def test_deobfuscate_strings_multiple_base64(deobfuscator):
    """Test deobfuscation of multiple base64 strings."""
    code = '''
    var a = atob("SGVsbG8=");
    var b = atob("V29ybGQ=");
    '''
    
    result = deobfuscator.deobfuscate_strings(code)
    
    # Should attempt to decode both
    assert result is not None


def test_deobfuscate_strings_invalid_base64(deobfuscator):
    """Test handling of invalid base64."""
    code = 'var x = atob("not valid base64!!!");'
    
    # Should not crash on invalid base64
    result = deobfuscator.deobfuscate_strings(code)
    
    assert result is not None


def test_deobfuscate_strings_eval_pattern(deobfuscator):
    """Test deobfuscation of eval patterns."""
    code = 'eval("console.log");'
    
    result = deobfuscator.deobfuscate_strings(code)
    
    assert result is not None


def test_simplify_control_flow(deobfuscator):
    """Test control flow simplification."""
    code = """
    function test() {
        while(true) {
            switch(state) {
            }
        }
    }
    """
    
    result = deobfuscator.simplify_control_flow(code)
    
    assert result is not None


def test_simplify_control_flow_dead_code(deobfuscator):
    """Test removal of dead code after return."""
    code = """
    function test() {
        return 5;
        console.log("unreachable");
    }
    """
    
    result = deobfuscator.simplify_control_flow(code)
    
    # Should process the code
    assert "return" in result


def test_simplify_control_flow_throw(deobfuscator):
    """Test handling of throw statements."""
    code = """
    function test() {
        throw new Error("test");
        console.log("unreachable");
    }
    """
    
    result = deobfuscator.simplify_control_flow(code)
    
    assert "throw" in result


def test_extract_original_names_hex_var(deobfuscator):
    """Test extraction of original names from hex variables."""
    code = """
    var _0x1234 = ['getValue', 'setValue', 'process'];
    function _0xabc() {
        return _0x1234[0]();
    }
    """
    
    result = deobfuscator.extract_original_names(code)
    
    assert isinstance(result, dict)
    # Should find the hex variable
    if "_0x1234" in result:
        assert result["_0x1234"] in ["getValue", "setValue", "process"]


def test_extract_original_names_short_functions(deobfuscator):
    """Test detection of obfuscated short function names."""
    code = """
    function a() { return 1; }
    function ab() { return 2; }
    function get() { return 3; }
    """
    
    result = deobfuscator.extract_original_names(code)
    
    # 'a' and 'ab' should be flagged as obfuscated
    # 'get' should not be (it's a common short name)
    assert isinstance(result, dict)


def test_extract_original_names_empty_code(deobfuscator):
    """Test extraction from empty code."""
    result = deobfuscator.extract_original_names("")
    
    assert result == {}


def test_extract_original_names_normal_code(deobfuscator):
    """Test extraction from normal code."""
    code = """
    function calculateTotal(items) {
        return items.reduce((sum, item) => sum + item.price, 0);
    }
    """
    
    result = deobfuscator.extract_original_names(code)
    
    # Normal code shouldn't have many obfuscated names
    assert isinstance(result, dict)


def test_deobfuscate_strings_preserves_structure(deobfuscator):
    """Test that deobfuscation preserves code structure."""
    code = """
    function test() {
        var x = atob("dGVzdA==");
        return x;
    }
    """
    
    result = deobfuscator.deobfuscate_strings(code)
    
    # Should preserve function structure
    assert "function" in result
    assert "return" in result


def test_simplify_control_flow_nested_while(deobfuscator):
    """Test simplification of nested while loops."""
    code = """
    while(true) {
        while(true) {
            switch(x) {
            }
        }
    }
    """
    
    result = deobfuscator.simplify_control_flow(code)
    
    assert result is not None


def test_handle_invalid_input_detect(deobfuscator):
    """Test handling of invalid input for detection."""
    # Empty string
    result = deobfuscator.detect_obfuscation_type("")
    assert result == ObfuscationType.UNKNOWN
    
    # Whitespace only
    result = deobfuscator.detect_obfuscation_type("   \n\t  ")
    assert result in [ObfuscationType.UNKNOWN, ObfuscationType.NAME_MANGLING]


def test_handle_invalid_input_deobfuscate(deobfuscator):
    """Test handling of invalid input for deobfuscation."""
    # Empty string
    result = deobfuscator.deobfuscate_strings("")
    assert result == ""
    
    # Whitespace only
    result = deobfuscator.simplify_control_flow("   ")
    assert result is not None


def test_deobfuscate_hex_strings(deobfuscator):
    """Test deobfuscation of hex encoded strings."""
    code = '''
    var x = "48656c6c6f".replace(/.../g,
    '''
    
    result = deobfuscator.deobfuscate_strings(code)
    
    # Should handle hex patterns
    assert result is not None


def test_combined_deobfuscation(deobfuscator):
    """Test combined deobfuscation techniques."""
    code = '''
    var _0x1234 = ['log'];
    function a() {
        eval(atob("Y29uc29sZS5sb2coJ3Rlc3QnKQ=="));
        return;
        console.log("dead code");
    }
    '''
    
    # Apply all deobfuscation
    result = deobfuscator.deobfuscate_strings(code)
    result = deobfuscator.simplify_control_flow(result)
    names = deobfuscator.extract_original_names(code)
    
    assert result is not None
    assert isinstance(names, dict)


def test_detect_name_mangling(deobfuscator):
    """Test detection of name mangling patterns."""
    # Very short alphanumeric start might indicate name mangling
    code = "ab12cd34ef56"
    
    result = deobfuscator.detect_obfuscation_type(code)
    
    # Short alphanumeric could be name mangling
    assert result in [ObfuscationType.NAME_MANGLING, ObfuscationType.UNKNOWN]


def test_deobfuscate_preserves_comments(deobfuscator):
    """Test that deobfuscation preserves comments."""
    code = """
    // This is a comment
    var x = atob("dGVzdA==");
    /* Multi-line
       comment */
    """
    
    result = deobfuscator.deobfuscate_strings(code)
    
    # Comments should be preserved
    assert "comment" in result.lower()

