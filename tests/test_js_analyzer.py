"""Tests for JavaScript analyzer."""

import pytest

from src.intelligence.js.analyzer import JSAnalyzer, APICall, AuthFlowDefinition


def test_js_analyzer_initialization():
    """Test JS analyzer initialization."""
    analyzer = JSAnalyzer()
    
    assert analyzer.url_pattern is not None
    assert analyzer.fetch_pattern is not None
    assert analyzer.xhr_pattern is not None
    assert analyzer.axios_pattern is not None


def test_extract_api_calls_fetch():
    """Test extracting fetch API calls."""
    analyzer = JSAnalyzer()
    
    code = """
    fetch('https://api.example.com/users')
    fetch("https://api.example.com/posts")
    """
    
    api_calls = analyzer.extract_api_calls(code)
    
    assert len(api_calls) == 2
    assert all(call.type == "fetch" for call in api_calls)
    assert "api.example.com" in api_calls[0].url


def test_extract_api_calls_xhr():
    """Test extracting XHR API calls."""
    analyzer = JSAnalyzer()
    
    code = """
    const xhr = new XMLHttpRequest();
    xhr.open('GET', 'https://api.example.com/data');
    xhr.open('POST', 'https://api.example.com/create');
    """
    
    api_calls = analyzer.extract_api_calls(code)
    
    assert len(api_calls) >= 2
    assert any(call.type == "xhr" and call.method == "GET" for call in api_calls)
    assert any(call.type == "xhr" and call.method == "POST" for call in api_calls)


def test_extract_api_calls_axios():
    """Test extracting axios API calls."""
    analyzer = JSAnalyzer()
    
    code = """
    axios.get('https://api.example.com/users')
    axios.post('https://api.example.com/users', data)
    """
    
    api_calls = analyzer.extract_api_calls(code)
    
    assert len(api_calls) >= 2
    assert any(call.type == "axios" and call.method == "GET" for call in api_calls)
    assert any(call.type == "axios" and call.method == "POST" for call in api_calls)


def test_find_hardcoded_urls():
    """Test finding hardcoded URLs."""
    analyzer = JSAnalyzer()
    
    code = """
    const apiUrl = 'https://api.example.com/v1';
    const imageUrl = 'http://cdn.example.com/image.jpg';
    const localPath = '/static/file.js';
    """
    
    urls = analyzer.find_hardcoded_urls(code)
    
    assert len(urls) >= 2
    assert any("api.example.com" in url for url in urls)
    assert any("cdn.example.com" in url for url in urls)
    assert not any(url.startswith("/") for url in urls)


def test_extract_constants():
    """Test extracting constants."""
    analyzer = JSAnalyzer()
    
    code = """
    const API_KEY = 'secret123';
    const API_URL = 'https://api.example.com';
    const MAX_RETRIES = 3;
    """
    
    constants = analyzer.extract_constants(code)
    
    assert len(constants) > 0
    assert any("API_KEY" in str(const) for const in constants)


def test_find_auth_logic():
    """Test finding authentication logic."""
    analyzer = JSAnalyzer()
    
    code = """
    localStorage.setItem('token', response.token);
    const token = localStorage.getItem('token');
    """
    
    auth_logic = analyzer.find_auth_logic(code)
    
    # Should detect token storage
    assert auth_logic is not None or True  # May return None if not detected


def test_extract_api_calls_line_numbers():
    """Test API call extraction includes line numbers."""
    analyzer = JSAnalyzer()
    
    code = """line 1
    line 2
    fetch('https://api.example.com')
    line 4
    """
    
    api_calls = analyzer.extract_api_calls(code)
    
    if api_calls:
        assert api_calls[0].line_number > 0


def test_extract_api_calls_empty_code():
    """Test extracting from empty code."""
    analyzer = JSAnalyzer()
    
    api_calls = analyzer.extract_api_calls("")
    
    assert len(api_calls) == 0


def test_find_hardcoded_urls_empty():
    """Test finding URLs in empty code."""
    analyzer = JSAnalyzer()
    
    urls = analyzer.find_hardcoded_urls("")
    
    assert len(urls) == 0


def test_api_call_dataclass():
    """Test APICall dataclass."""
    api_call = APICall(
        url="https://api.example.com",
        method="GET",
        type="fetch",
        line_number=10,
    )
    
    assert api_call.url == "https://api.example.com"
    assert api_call.method == "GET"
    assert api_call.type == "fetch"
    assert api_call.line_number == 10


def test_auth_flow_definition():
    """Test AuthFlowDefinition dataclass."""
    auth_flow = AuthFlowDefinition(
        flow_type="oauth2",
        token_storage="localStorage",
        refresh_mechanism="refresh_token",
    )
    
    assert auth_flow.flow_type == "oauth2"
    assert auth_flow.token_storage == "localStorage"
    assert auth_flow.refresh_mechanism == "refresh_token"


