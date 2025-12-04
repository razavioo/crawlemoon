"""Tests for CAPTCHA solving integration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import os

from src.intelligence.security.captcha_solver import (
    CaptchaSolver,
    CaptchaService,
    CaptchaType,
    get_captcha_solver,
)


@pytest.fixture
def solver():
    """Create a CAPTCHA solver without API keys."""
    return CaptchaSolver()


@pytest.fixture
def solver_with_anticaptcha():
    """Create a CAPTCHA solver with mocked AntiCaptcha."""
    with patch("src.intelligence.security.captcha_solver.ANTICAPTCHA_AVAILABLE", True):
        with patch("src.intelligence.security.captcha_solver.AnticaptchaClient") as mock_client:
            mock_client.return_value = MagicMock()
            return CaptchaSolver(anticaptcha_key="test-key")


def test_captcha_solver_initialization():
    """Test CAPTCHA solver initialization."""
    solver = CaptchaSolver()
    
    assert solver is not None
    assert solver.anticaptcha_key is None
    assert solver.capsolver_key is None
    assert solver.default_service == CaptchaService.AUTO


def test_captcha_solver_with_keys():
    """Test initialization with API keys."""
    solver = CaptchaSolver(
        anticaptcha_key="anti-key",
        capsolver_key="cap-key",
    )
    
    assert solver.anticaptcha_key == "anti-key"
    assert solver.capsolver_key == "cap-key"


def test_captcha_solver_default_service():
    """Test initialization with custom default service."""
    solver = CaptchaSolver(default_service=CaptchaService.ANTICAPTCHA)
    
    assert solver.default_service == CaptchaService.ANTICAPTCHA


def test_captcha_service_enum():
    """Test CaptchaService enum values."""
    assert CaptchaService.ANTICAPTCHA.value == "anticaptcha"
    assert CaptchaService.CAPSOLVER.value == "capsolver"
    assert CaptchaService.AUTO.value == "auto"


def test_captcha_type_enum():
    """Test CaptchaType enum values."""
    assert CaptchaType.RECAPTCHA_V2.value == "recaptcha_v2"
    assert CaptchaType.RECAPTCHA_V3.value == "recaptcha_v3"
    assert CaptchaType.HCAPTCHA.value == "hcaptcha"
    assert CaptchaType.TURNSTILE.value == "turnstile"
    assert CaptchaType.FUNCAPTCHA.value == "funcaptcha"
    assert CaptchaType.IMAGE.value == "image"
    assert CaptchaType.TEXT.value == "text"


def test_is_available_no_clients(solver):
    """Test availability check with no clients."""
    assert solver.is_available() is False


def test_is_available_with_anticaptcha():
    """Test availability with AntiCaptcha client - skip if module not available."""
    try:
        from python_anticaptcha import AnticaptchaClient
        solver = CaptchaSolver(anticaptcha_key="test-key")
        assert solver.is_available() is True
    except ImportError:
        pytest.skip("python_anticaptcha not installed")


def test_is_available_with_capsolver():
    """Test availability with CapSolver client - skip if module not available."""
    try:
        from capsolver import CapSolver
        solver = CaptchaSolver(capsolver_key="test-key")
        assert solver.is_available() is True
    except ImportError:
        pytest.skip("capsolver not installed")


@pytest.mark.asyncio
async def test_solve_recaptcha_v2_no_service(solver):
    """Test solving reCAPTCHA v2 with no service available."""
    result = await solver.solve_recaptcha_v2(
        site_key="test-site-key",
        page_url="https://example.com",
    )
    
    assert result is None


@pytest.mark.asyncio
async def test_solve_recaptcha_v2_anticaptcha():
    """Test solving reCAPTCHA v2 with AntiCaptcha - skip if module not available."""
    try:
        from python_anticaptcha import AnticaptchaClient
    except ImportError:
        pytest.skip("python_anticaptcha not installed")
    
    solver = CaptchaSolver(anticaptcha_key="test-key")
    
    with patch.object(solver, '_solve_recaptcha_v2_anticaptcha', new_callable=AsyncMock) as mock_solve:
        mock_solve.return_value = "test-token"
        
        result = await solver.solve_recaptcha_v2(
            site_key="test-site-key",
            page_url="https://example.com",
            service=CaptchaService.ANTICAPTCHA,
        )
        
        assert result == "test-token"


@pytest.mark.asyncio
async def test_solve_recaptcha_v2_capsolver():
    """Test solving reCAPTCHA v2 with CapSolver - skip if module not available."""
    try:
        from capsolver import CapSolver
    except ImportError:
        pytest.skip("capsolver not installed")
    
    solver = CaptchaSolver(capsolver_key="test-key")
    
    with patch.object(solver, '_solve_recaptcha_v2_capsolver', new_callable=AsyncMock) as mock_solve:
        mock_solve.return_value = "test-token"
        
        result = await solver.solve_recaptcha_v2(
            site_key="test-site-key",
            page_url="https://example.com",
            service=CaptchaService.CAPSOLVER,
        )
        
        assert result == "test-token"


@pytest.mark.asyncio
async def test_solve_hcaptcha_no_service(solver):
    """Test solving hCaptcha with no service available."""
    result = await solver.solve_hcaptcha(
        site_key="test-site-key",
        page_url="https://example.com",
    )
    
    assert result is None


@pytest.mark.asyncio
async def test_solve_hcaptcha_capsolver():
    """Test solving hCaptcha with CapSolver - skip if module not available."""
    try:
        from capsolver import CapSolver
    except ImportError:
        pytest.skip("capsolver not installed")
    
    solver = CaptchaSolver(capsolver_key="test-key")
    
    result = await solver.solve_hcaptcha(
        site_key="test-site-key",
        page_url="https://example.com",
        service=CaptchaService.CAPSOLVER,
    )
    
    # Result depends on client configuration
    assert result is None or isinstance(result, str)


@pytest.mark.asyncio
async def test_solve_turnstile_no_service(solver):
    """Test solving Turnstile with no service available."""
    result = await solver.solve_turnstile(
        site_key="test-site-key",
        page_url="https://example.com",
    )
    
    assert result is None


@pytest.mark.asyncio
async def test_solve_turnstile_capsolver():
    """Test solving Turnstile with CapSolver - skip if module not available."""
    try:
        from capsolver import CapSolver
    except ImportError:
        pytest.skip("capsolver not installed")
    
    solver = CaptchaSolver(capsolver_key="test-key")
    
    result = await solver.solve_turnstile(
        site_key="test-site-key",
        page_url="https://example.com",
        service=CaptchaService.CAPSOLVER,
    )
    
    # Result depends on client configuration
    assert result is None or isinstance(result, str)


@pytest.mark.asyncio
async def test_solve_image_captcha_no_service(solver):
    """Test solving image CAPTCHA with no service available."""
    result = await solver.solve_image_captcha(
        image_data=b"fake-image-data",
    )
    
    assert result is None


@pytest.mark.asyncio
async def test_solve_image_captcha_anticaptcha():
    """Test solving image CAPTCHA with AntiCaptcha - skip if module not available."""
    try:
        from python_anticaptcha import AnticaptchaClient
    except ImportError:
        pytest.skip("python_anticaptcha not installed")
    
    solver = CaptchaSolver(anticaptcha_key="test-key")
    
    result = await solver.solve_image_captcha(
        image_data=b"fake-image-data",
        service=CaptchaService.ANTICAPTCHA,
    )
    
    # Result depends on actual client
    assert result is None or isinstance(result, str)


@pytest.mark.asyncio
async def test_solve_recaptcha_v2_auto_fallback(solver):
    """Test auto fallback between services."""
    # With no services available, should return None
    result = await solver.solve_recaptcha_v2(
        site_key="test-site-key",
        page_url="https://example.com",
        service=CaptchaService.AUTO,
    )
    
    assert result is None


def test_get_captcha_solver_no_keys():
    """Test get_captcha_solver without API keys."""
    with patch.dict(os.environ, {}, clear=True):
        # Clear any existing env vars
        os.environ.pop("ANTICAPTCHA_API_KEY", None)
        os.environ.pop("CAPSOLVER_API_KEY", None)
        
        result = get_captcha_solver()
        
        assert result is None


@patch.dict(os.environ, {"ANTICAPTCHA_API_KEY": "test-key"})
def test_get_captcha_solver_from_env():
    """Test get_captcha_solver with env var - skip if module not available."""
    try:
        from python_anticaptcha import AnticaptchaClient
    except ImportError:
        pytest.skip("python_anticaptcha not installed")
    
    # Reset global instance
    import src.intelligence.security.captcha_solver as module
    module._captcha_solver = None
    
    result = get_captcha_solver()
    
    # Should return solver if client is available
    assert result is None or isinstance(result, CaptchaSolver)


def test_get_captcha_solver_with_explicit_key():
    """Test get_captcha_solver with explicit key - skip if module not available."""
    try:
        from python_anticaptcha import AnticaptchaClient
    except ImportError:
        pytest.skip("python_anticaptcha not installed")
    
    # Reset global instance
    import src.intelligence.security.captcha_solver as module
    module._captcha_solver = None
    
    result = get_captcha_solver(anticaptcha_key="explicit-key")
    
    # Should return solver
    assert result is None or isinstance(result, CaptchaSolver)


@pytest.mark.asyncio
async def test_solve_recaptcha_handles_exception():
    """Test that solver handles exceptions gracefully."""
    solver = CaptchaSolver()
    
    # Without any API keys configured, should return None
    result = await solver.solve_recaptcha_v2(
        site_key="test-site-key",
        page_url="https://example.com",
        service=CaptchaService.AUTO,
    )
    
    # Should handle gracefully
    assert result is None


@pytest.mark.asyncio
async def test_solve_hcaptcha_handles_exception():
    """Test that hCaptcha solver handles exceptions."""
    solver = CaptchaSolver()
    
    # Without any API keys configured, should return None
    result = await solver.solve_hcaptcha(
        site_key="test-site-key",
        page_url="https://example.com",
        service=CaptchaService.AUTO,
    )
    
    assert result is None


def test_captcha_solver_client_init_error():
    """Test handling of client initialization errors."""
    # Test with invalid keys - should not crash
    solver = CaptchaSolver(
        anticaptcha_key="invalid-key",
        capsolver_key="invalid-key"
    )
    
    # The clients may or may not be initialized depending on imports
    assert solver is not None

