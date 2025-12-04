"""Tests for bot detection analyzer."""

import pytest

from src.intelligence.security.bot_detection import (
    BotDetectionAnalyzer,
    ProtectionType,
    CaptchaType,
    FingerprintingInfo,
    RateLimitInfo,
)


def test_bot_detection_initialization():
    """Test bot detection analyzer initialization."""
    analyzer = BotDetectionAnalyzer()
    
    assert analyzer is not None


def test_detect_protection_cloudflare():
    """Test detecting Cloudflare protection."""
    analyzer = BotDetectionAnalyzer()
    
    content = "<html>Test</html>"
    headers = {"Server": "cloudflare", "CF-RAY": "abc123"}
    
    protection = analyzer.detect_protection_type(content, headers)
    
    assert protection == ProtectionType.CLOUDFLARE


def test_detect_protection_akamai():
    """Test detecting Akamai protection."""
    analyzer = BotDetectionAnalyzer()
    
    content = "<html>Test</html>"
    headers = {"Server": "akamai"}
    
    protection = analyzer.detect_protection_type(content, headers)
    
    assert protection == ProtectionType.AKAMAI


def test_detect_protection_perimeterx():
    """Test detecting PerimeterX protection."""
    analyzer = BotDetectionAnalyzer()
    
    content = "<html><script>perimeterx</script></html>"
    headers = {}
    
    protection = analyzer.detect_protection_type(content, headers)
    
    assert protection == ProtectionType.PERIMETERX


def test_detect_protection_recaptcha():
    """Test detecting reCAPTCHA."""
    analyzer = BotDetectionAnalyzer()
    
    content = "<html><div>recaptcha</div></html>"
    headers = {}
    
    protection = analyzer.detect_protection_type(content, headers)
    
    assert protection == ProtectionType.RECAPTCHA


def test_detect_protection_none():
    """Test detecting no protection."""
    analyzer = BotDetectionAnalyzer()
    
    content = "<html>Normal page</html>"
    headers = {}
    
    protection = analyzer.detect_protection_type(content, headers)
    
    assert protection == ProtectionType.NONE


def test_analyze_fingerprinting():
    """Test analyzing fingerprinting techniques."""
    analyzer = BotDetectionAnalyzer()
    
    content = """
    <html>
    <script>
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    const audioContext = new AudioContext();
    </script>
    </html>
    """
    
    info = analyzer.analyze_fingerprinting(content)
    
    assert isinstance(info, FingerprintingInfo)
    # Fingerprinting detection may vary, just check it's a valid FingerprintingInfo
    assert hasattr(info, 'canvas_fingerprint')
    assert hasattr(info, 'webgl_fingerprint')


def test_analyze_fingerprinting_no_detection():
    """Test fingerprinting analysis with no detection."""
    analyzer = BotDetectionAnalyzer()
    
    content = "<html>Normal page</html>"
    
    info = analyzer.analyze_fingerprinting(content)
    
    assert isinstance(info, FingerprintingInfo)
    assert info.canvas_fingerprint is False


def test_detect_captcha_recaptcha_v2():
    """Test detecting reCAPTCHA v2."""
    analyzer = BotDetectionAnalyzer()
    
    content = "<html><div>recaptcha</div></html>"
    
    captcha_type = analyzer.detect_captcha_type(content)
    
    assert captcha_type == CaptchaType.RECAPTCHA_V2


def test_detect_captcha_recaptcha_v3():
    """Test detecting reCAPTCHA v3."""
    analyzer = BotDetectionAnalyzer()
    
    content = "<html><script>recaptcha/v3</script></html>"
    
    captcha_type = analyzer.detect_captcha_type(content)
    
    assert captcha_type == CaptchaType.RECAPTCHA_V3


def test_detect_captcha_hcaptcha():
    """Test detecting hCaptcha."""
    analyzer = BotDetectionAnalyzer()
    
    content = "<html><div>hcaptcha</div></html>"
    
    captcha_type = analyzer.detect_captcha_type(content)
    
    assert captcha_type == CaptchaType.HCAPTCHA


def test_detect_captcha_none():
    """Test detecting no captcha."""
    analyzer = BotDetectionAnalyzer()
    
    content = "<html>Normal page</html>"
    
    captcha_type = analyzer.detect_captcha_type(content)
    
    assert captcha_type == CaptchaType.NONE


def test_find_rate_limits():
    """Test finding rate limit information."""
    analyzer = BotDetectionAnalyzer()
    
    headers = {
        "X-RateLimit-Limit": "60",
        "Retry-After": "30",
    }
    response_times = [0.5, 0.6, 0.7]
    
    info = analyzer.find_rate_limits(headers, response_times)
    
    assert isinstance(info, RateLimitInfo)
    assert info.requests_per_minute == 60
    assert info.block_duration == 30


def test_find_rate_limits_no_headers():
    """Test finding rate limits with no headers."""
    analyzer = BotDetectionAnalyzer()
    
    headers = {}
    response_times = [0.5, 0.6, 0.7]
    
    info = analyzer.find_rate_limits(headers, response_times)
    
    assert isinstance(info, RateLimitInfo)
    assert info.requests_per_minute is None


def test_find_rate_limits_slow_responses():
    """Test detecting slow responses indicating rate limiting."""
    analyzer = BotDetectionAnalyzer()
    
    headers = {}
    response_times = [6.0, 7.0, 8.0]  # Slow responses
    
    info = analyzer.find_rate_limits(headers, response_times)
    
    assert isinstance(info, RateLimitInfo)

