"""Performance benchmark tests."""

import pytest
import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.mark.performance
@pytest.mark.asyncio
async def test_browser_pool_under_load():
    """Test concurrent browser operations."""
    from src.core.browser.pool import BrowserPool
    
    with patch("src.core.browser.pool.async_playwright") as mock_playwright:
        mock_p = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        
        mock_p.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_playwright.return_value.__aenter__ = AsyncMock(return_value=mock_p)
        mock_playwright.return_value.__aexit__ = AsyncMock()
        mock_playwright.return_value.start = AsyncMock(return_value=mock_p)
        
        pool = BrowserPool(max_size=10)
        pool._playwright = mock_p
        pool._browser = mock_browser
        
        # Override acquire to return mock contexts
        original_acquire = pool.acquire
        
        async def mock_acquire(*args, **kwargs):
            return mock_context
        
        pool.acquire = mock_acquire
        
        # Benchmark concurrent acquisitions
        num_operations = 100
        start_time = time.time()
        
        tasks = [pool.acquire() for _ in range(num_operations)]
        results = await asyncio.gather(*tasks)
        
        elapsed = time.time() - start_time
        
        # All operations should succeed
        assert len(results) == num_operations
        assert all(r is not None for r in results)
        
        # Performance check: should complete within reasonable time
        # With mocking, this should be very fast
        assert elapsed < 5.0, f"Operations took {elapsed}s, expected < 5s"
        
        ops_per_second = num_operations / elapsed
        print(f"\nBrowser pool: {ops_per_second:.2f} ops/sec ({num_operations} ops in {elapsed:.2f}s)")


@pytest.mark.performance
@pytest.mark.asyncio
async def test_rate_limiter_throughput():
    """Test rate limiter efficiency."""
    from src.core.rate_limiter import RateLimiter
    
    limiter = RateLimiter()
    limiter.set_default_rate_limit(requests_per_second=1000.0)  # High limit for throughput test
    
    num_requests = 500
    start_time = time.time()
    
    # Make many requests
    for i in range(num_requests):
        await limiter.wait_if_needed(f"https://example{i % 10}.com/page{i}")
    
    elapsed = time.time() - start_time
    
    # Should process quickly with high rate limit
    assert elapsed < 10.0, f"Rate limiting took {elapsed}s, expected < 10s"
    
    throughput = num_requests / elapsed
    print(f"\nRate limiter: {throughput:.2f} req/sec ({num_requests} requests in {elapsed:.2f}s)")


@pytest.mark.performance
@pytest.mark.asyncio
async def test_rate_limiter_with_multiple_domains():
    """Test rate limiter with many different domains."""
    from src.core.rate_limiter import RateLimiter
    
    limiter = RateLimiter()
    limiter.set_default_rate_limit(requests_per_second=100.0)
    
    domains = [f"example{i}.com" for i in range(50)]
    num_requests_per_domain = 20
    
    start_time = time.time()
    
    for _ in range(num_requests_per_domain):
        for domain in domains:
            await limiter.wait_if_needed(f"https://{domain}/page")
    
    elapsed = time.time() - start_time
    total_requests = len(domains) * num_requests_per_domain
    
    throughput = total_requests / elapsed
    print(f"\nRate limiter (multi-domain): {throughput:.2f} req/sec ({total_requests} across {len(domains)} domains)")


@pytest.mark.performance
def test_large_recording_serialization():
    """Test large recording serialization performance."""
    from src.core.recording_storage import RecordingStorage
    from src.intelligence.recorder.session import SessionRecording, Event, EventType
    from datetime import datetime
    import tempfile
    import json
    
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = RecordingStorage(storage_dir=tmpdir)
        
        # Create a large recording with many events
        num_events = 1000
        events = []
        for i in range(num_events):
            events.append(Event(
                type=EventType.CLICK,
                timestamp=datetime.now(),
                data={
                    "x": i * 10,
                    "y": i * 5,
                    "selector": f"#element-{i}",
                    "text": f"Clicked element {i}",
                }
            ))
        
        recording = SessionRecording(
            id=f"large-recording-{num_events}",
            events=events,
            start_time=datetime.now(),
        )
        
        # Benchmark serialization
        start_time = time.time()
        serialized = storage._serialize_recording(recording)
        serialize_time = time.time() - start_time
        
        # Benchmark deserialization
        start_time = time.time()
        deserialized = storage._deserialize_recording(serialized)
        deserialize_time = time.time() - start_time
        
        # Verify correctness
        assert deserialized.id == recording.id
        assert len(deserialized.events) == num_events
        
        # Performance checks
        assert serialize_time < 2.0, f"Serialization took {serialize_time}s, expected < 2s"
        assert deserialize_time < 2.0, f"Deserialization took {deserialize_time}s, expected < 2s"
        
        size_kb = len(json.dumps(serialized)) / 1024
        print(f"\nRecording serialization ({num_events} events, {size_kb:.1f}KB):")
        print(f"  Serialize: {serialize_time*1000:.2f}ms")
        print(f"  Deserialize: {deserialize_time*1000:.2f}ms")


@pytest.mark.performance
def test_js_analyzer_performance():
    """Test JS analyzer with large code."""
    from src.intelligence.js.analyzer import JSAnalyzer
    
    analyzer = JSAnalyzer()
    
    # Generate a large JavaScript code sample
    lines = []
    for i in range(500):
        lines.append(f"const api{i} = fetch('/api/endpoint{i}');")
        lines.append(f"const SECRET_{i} = 'secret-value-{i}';")
        lines.append(f"const url{i} = 'https://api.example.com/v1/resource{i}';")
    
    code = "\n".join(lines)
    code_kb = len(code) / 1024
    
    # Benchmark API call extraction
    start_time = time.time()
    api_calls = analyzer.extract_api_calls(code)
    api_time = time.time() - start_time
    
    # Benchmark URL extraction
    start_time = time.time()
    urls = analyzer.find_hardcoded_urls(code)
    url_time = time.time() - start_time
    
    # Benchmark constant extraction
    start_time = time.time()
    constants = analyzer.extract_constants(code)
    const_time = time.time() - start_time
    
    # Performance checks
    assert api_time < 5.0, f"API extraction took {api_time}s, expected < 5s"
    assert url_time < 5.0, f"URL extraction took {url_time}s, expected < 5s"
    assert const_time < 5.0, f"Constant extraction took {const_time}s, expected < 5s"
    
    print(f"\nJS Analyzer ({code_kb:.1f}KB code):")
    print(f"  API calls: {len(api_calls)} found in {api_time*1000:.2f}ms")
    print(f"  URLs: {len(urls)} found in {url_time*1000:.2f}ms")
    print(f"  Constants: {len(constants)} found in {const_time*1000:.2f}ms")


@pytest.mark.performance
def test_js_deobfuscator_performance():
    """Test JS deobfuscator with complex code."""
    from src.intelligence.js.deobfuscator import JSDeobfuscator
    
    deobfuscator = JSDeobfuscator()
    
    # Generate obfuscated-looking code
    lines = []
    for i in range(200):
        lines.append(f'var _0x{i:04x} = atob("SGVsbG8gV29ybGQ=");')
        lines.append(f'while(true) {{ switch(state{i}) {{ case 0: break; }} }}')
    
    code = "\n".join(lines)
    code_kb = len(code) / 1024
    
    # Benchmark detection
    start_time = time.time()
    obf_type = deobfuscator.detect_obfuscation_type(code)
    detect_time = time.time() - start_time
    
    # Benchmark string deobfuscation
    start_time = time.time()
    deobfuscated = deobfuscator.deobfuscate_strings(code)
    string_time = time.time() - start_time
    
    # Benchmark control flow simplification
    start_time = time.time()
    simplified = deobfuscator.simplify_control_flow(code)
    cf_time = time.time() - start_time
    
    # Performance checks
    assert detect_time < 1.0, f"Detection took {detect_time}s, expected < 1s"
    assert string_time < 5.0, f"String deobfuscation took {string_time}s, expected < 5s"
    assert cf_time < 5.0, f"Control flow simplification took {cf_time}s, expected < 5s"
    
    print(f"\nJS Deobfuscator ({code_kb:.1f}KB code):")
    print(f"  Detection: {detect_time*1000:.2f}ms ({obf_type.value})")
    print(f"  String deobfuscation: {string_time*1000:.2f}ms")
    print(f"  Control flow: {cf_time*1000:.2f}ms")


@pytest.mark.performance
@pytest.mark.asyncio
async def test_proxy_pool_rotation_performance():
    """Test proxy rotation performance under load."""
    from src.core.browser.proxy_pool import ProxyPool, RotationStrategy
    
    # Create pool with many proxies
    num_proxies = 100
    proxy_urls = [f"http://proxy{i}:8080" for i in range(num_proxies)]
    
    pool = ProxyPool(
        proxies=proxy_urls,
        rotation_strategy=RotationStrategy.ROUND_ROBIN
    )
    
    num_rotations = 1000
    start_time = time.time()
    
    for _ in range(num_rotations):
        proxy = await pool.get_proxy()
        assert proxy is not None
    
    elapsed = time.time() - start_time
    
    # Performance check
    assert elapsed < 2.0, f"Rotation took {elapsed}s, expected < 2s"
    
    rotations_per_sec = num_rotations / elapsed
    print(f"\nProxy rotation ({num_proxies} proxies): {rotations_per_sec:.2f} rotations/sec")


@pytest.mark.performance
@pytest.mark.asyncio
async def test_concurrent_rate_limiter_stress():
    """Stress test rate limiter with concurrent requests."""
    from src.core.rate_limiter import RateLimiter
    
    limiter = RateLimiter()
    limiter.set_default_rate_limit(requests_per_second=500.0)
    limiter.set_global_rate_limit(requests_per_second=1000.0)
    
    num_concurrent = 50
    requests_per_task = 20
    
    async def make_requests(domain_id):
        for i in range(requests_per_task):
            await limiter.wait_if_needed(f"https://domain{domain_id}.com/page{i}")
    
    start_time = time.time()
    
    tasks = [make_requests(i) for i in range(num_concurrent)]
    await asyncio.gather(*tasks)
    
    elapsed = time.time() - start_time
    total_requests = num_concurrent * requests_per_task
    
    throughput = total_requests / elapsed
    print(f"\nConcurrent rate limiting ({num_concurrent} tasks, {total_requests} total):")
    print(f"  Throughput: {throughput:.2f} req/sec")
    print(f"  Elapsed: {elapsed:.2f}s")


@pytest.mark.performance
def test_content_extractor_performance():
    """Test content extraction performance with various HTML sizes."""
    from src.intelligence.extraction.content import ContentExtractor
    
    extractor = ContentExtractor()
    
    # Generate HTML of various sizes
    sizes = [1, 10, 50, 100]  # KB
    
    print("\nContent extraction performance:")
    for size_kb in sizes:
        # Generate HTML
        paragraphs = []
        while len("\n".join(paragraphs)) < size_kb * 1024:
            paragraphs.append(f"<p>{'Lorem ipsum dolor sit amet. ' * 20}</p>")
        
        html = f"""
        <html>
        <head><title>Test Page</title></head>
        <body>
            <article>
                <h1>Test Article</h1>
                {"".join(paragraphs)}
            </article>
        </body>
        </html>
        """
        
        actual_kb = len(html) / 1024
        
        start_time = time.time()
        result = extractor.extract(html, "https://example.com")
        elapsed = time.time() - start_time
        
        assert result is not None
        print(f"  {actual_kb:.1f}KB: {elapsed*1000:.2f}ms")


@pytest.mark.performance
def test_smart_extractor_performance():
    """Test smart extraction performance."""
    from src.intelligence.extraction.smart import SmartExtractor
    
    extractor = SmartExtractor()
    
    # Generate HTML with product listings
    products = []
    for i in range(100):
        products.append(f"""
        <div class="product">
            <h2 class="title">Product {i}</h2>
            <span class="price">${i * 10 + 9.99}</span>
            <img src="product{i}.jpg" alt="Product {i}">
        </div>
        """)
    
    html = f"""
    <html>
    <body>
        <div class="products">
            {"".join(products)}
        </div>
    </body>
    </html>
    """
    
    queries = [
        "extract all product prices",
        "get product titles",
        "find all images",
    ]
    
    print("\nSmart extraction performance:")
    for query in queries:
        start_time = time.time()
        result = extractor.extract(html, query)
        elapsed = time.time() - start_time
        
        print(f"  '{query}': {elapsed*1000:.2f}ms")

