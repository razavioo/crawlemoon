"""CLI main entry point."""

import asyncio
import argparse
import logging
import sys
from typing import Optional

from ..core.browser.pool import BrowserPool
from ..core.browser.stealth import create_stealth_context
from ..intelligence.network.interceptor import DeepNetworkInterceptor
from ..intelligence.network.api_discovery import APIDiscoveryEngine
from ..intelligence.recorder.session import SessionRecorder
from ..intelligence.generator.crawler_gen import CrawlerGenerator

logger = logging.getLogger(__name__)


async def deep_analyze(url: str, full: bool = False):
    """Analyze a website deeply."""
    print(f"Analyzing {url}...")
    
    pool = BrowserPool()
    await pool.initialize()
    
    try:
        context = await create_stealth_context(pool)
        page = await context.new_page()
        
        interceptor = DeepNetworkInterceptor()
        await interceptor.start_intercepting(page)
        
        await page.goto(url, wait_until="networkidle")
        
        requests = await interceptor.capture_all_requests()
        responses = await interceptor.capture_all_responses()
        
        discovery = APIDiscoveryEngine()
        rest_endpoints = discovery.detect_rest_endpoints(requests, responses)
        graphql = discovery.detect_graphql(requests, responses)
        
        print(f"\nResults:")
        print(f"  REST APIs: {len(rest_endpoints)}")
        print(f"  GraphQL: {'Yes' if graphql else 'No'}")
        print(f"  Network requests: {len(requests)}")
        
        await page.close()
        await context.close()
    
    finally:
        await pool.close()


async def discover_apis(url: str, include_hidden: bool = False):
    """Discover APIs on a website."""
    print(f"Discovering APIs on {url}...")
    
    pool = BrowserPool()
    await pool.initialize()
    
    try:
        context = await create_stealth_context(pool)
        page = await context.new_page()
        
        interceptor = DeepNetworkInterceptor()
        await interceptor.start_intercepting(page)
        
        await page.goto(url, wait_until="networkidle")
        
        requests = await interceptor.capture_all_requests()
        responses = await interceptor.capture_all_responses()
        
        discovery = APIDiscoveryEngine()
        rest_endpoints = discovery.detect_rest_endpoints(requests, responses)
        
        if include_hidden:
            internal = discovery.find_undocumented_endpoints(requests)
            print(f"\nUndocumented APIs: {len(internal)}")
            for api in internal[:5]:  # Show first 5
                print(f"  - {api.method} {api.url}")
        
        print(f"\nREST Endpoints ({len(rest_endpoints)}):")
        for ep in rest_endpoints[:10]:  # Show first 10
            print(f"  - {ep.method} {ep.path}")
        
        await page.close()
        await context.close()
    
    finally:
        await pool.close()


async def graphql_schema(endpoint: str):
    """Introspect GraphQL schema."""
    print(f"Introspecting GraphQL schema at {endpoint}...")
    
    discovery = APIDiscoveryEngine()
    schema = await discovery.run_introspection(endpoint)
    
    if schema:
        print("\nSchema extracted successfully!")
        print(f"Operations: {len(discovery.extract_queries_mutations(schema))}")
    else:
        print("Failed to introspect schema.")


async def record_session(url: str, output: str):
    """Record a session."""
    print(f"Recording session starting at {url}...")
    print(f"Output will be saved to {output}")
    print("Recording... (Ctrl+C to stop)")
    
    pool = BrowserPool()
    await pool.initialize()
    
    try:
        context = await create_stealth_context(pool)
        page = await context.new_page()
        
        recorder = SessionRecorder()
        recording = await recorder.start_recording(page)
        
        await page.goto(url)
        
        # Keep recording until interrupted
        try:
            await asyncio.sleep(3600)  # Wait up to 1 hour
        except KeyboardInterrupt:
            pass
        
        final_recording = await recorder.stop_recording()
        
        # Save full recording to file
        import json
        from datetime import datetime
        
        # Serialize recording to JSON
        recording_data = {
            "id": final_recording.id,
            "duration": final_recording.duration,
            "start_time": final_recording.start_time.isoformat() if final_recording.start_time else None,
            "end_time": final_recording.end_time.isoformat() if final_recording.end_time else None,
            "events": [
                {
                    "type": event.type.value,
                    "timestamp": event.timestamp.isoformat(),
                    "data": event.data,
                    "selector": event.selector,
                }
                for event in final_recording.events
            ],
            "network": [
                {
                    "type": net.type,
                    "url": net.url,
                    "method": net.method,
                    "timestamp": net.timestamp.isoformat(),
                    "data": net.data,
                }
                for net in final_recording.network
            ],
            "state_snapshots": [
                {
                    "url": snap.url,
                    "html": snap.html,
                    "timestamp": snap.timestamp.isoformat(),
                    "cookies": snap.cookies,
                    "local_storage": snap.local_storage,
                }
                for snap in final_recording.state_snapshots
            ],
        }
        
        with open(output, 'w') as f:
            json.dump(recording_data, f, indent=2)
        
        print(f"\nRecording saved to {output}")
        
        await page.close()
        await context.close()
    
    finally:
        await pool.close()


async def generate_crawler(from_recording: str, output: str):
    """Generate crawler from recording."""
    import json
    import os
    from datetime import datetime
    from ..intelligence.recorder.session import SessionRecording, Event, EventType, StateSnapshot
    
    print(f"Generating crawler from {from_recording}...")
    
    if not os.path.exists(from_recording):
        print(f"Error: Recording file not found: {from_recording}")
        return
    
    # Load recording from file
    try:
        with open(from_recording, 'r') as f:
            data = json.load(f)
        
        # Reconstruct events
        events = []
        for event_data in data.get("events", []):
            try:
                event_type = EventType(event_data.get("type", "click"))
                events.append(Event(
                    type=event_type,
                    timestamp=datetime.fromisoformat(event_data.get("timestamp", datetime.now().isoformat())),
                    data=event_data.get("data", {}),
                    selector=event_data.get("selector"),
                ))
            except Exception as e:
                logger.warning(f"Error loading event: {e}")
        
        # Reconstruct state snapshots
        state_snapshots = []
        for snap_data in data.get("state_snapshots", []):
            try:
                state_snapshots.append(StateSnapshot(
                    url=snap_data.get("url", ""),
                    html=snap_data.get("html", ""),
                    timestamp=datetime.fromisoformat(snap_data.get("timestamp", datetime.now().isoformat())),
                    cookies=snap_data.get("cookies", {}),
                    local_storage=snap_data.get("local_storage", {}),
                ))
            except Exception as e:
                logger.warning(f"Error loading snapshot: {e}")
        
        recording = SessionRecording(
            id=data.get("id", "unknown"),
            events=events,
            state_snapshots=state_snapshots,
            duration=data.get("duration", 0.0),
        )
        
        # Generate crawler
        generator = CrawlerGenerator()
        crawler_def = generator.from_recording(recording)
        crawler_def = generator.optimize_crawler(crawler_def)
        
        # Determine output format from file extension
        output_format = "yaml"
        if output.endswith(".py"):
            output_format = "python"
            output_content = generator.to_python_code(crawler_def)
        elif output.endswith(".yaml") or output.endswith(".yml"):
            output_format = "yaml"
            output_content = generator.to_yaml(crawler_def)
        else:
            output_format = "yaml"
            output_content = generator.to_yaml(crawler_def)
        
        # Write output
        with open(output, 'w') as f:
            f.write(output_content)
        
        print(f"\nCrawler generated successfully!")
        print(f"  Name: {crawler_def.name}")
        print(f"  Steps: {len(crawler_def.steps)}")
        print(f"  Format: {output_format}")
        print(f"  Output: {output}")
        
    except Exception as e:
        print(f"Error generating crawler: {e}")
        logger.error(f"Error generating crawler: {e}", exc_info=True)


async def run_crawler(crawler_file: str, stealth: bool = False):
    """Run a crawler."""
    print(f"Running crawler from {crawler_file}...")
    print("Crawler execution would be implemented here")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Crawilfy - Advanced Web Crawling Platform")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # deep-analyze
    analyze_parser = subparsers.add_parser("deep-analyze", help="Deep analyze a website")
    analyze_parser.add_argument("url", help="URL to analyze")
    analyze_parser.add_argument("--full", action="store_true", help="Full analysis")
    
    # discover-apis
    discover_parser = subparsers.add_parser("discover-apis", help="Discover APIs")
    discover_parser.add_argument("url", help="URL to analyze")
    discover_parser.add_argument("--include-hidden", action="store_true", help="Include hidden APIs")
    
    # graphql-schema
    graphql_parser = subparsers.add_parser("graphql-schema", help="Introspect GraphQL schema")
    graphql_parser.add_argument("endpoint", help="GraphQL endpoint URL")
    
    # record
    record_parser = subparsers.add_parser("record", help="Record a session")
    record_parser.add_argument("url", help="URL to start recording")
    record_parser.add_argument("--output", default="session.json", help="Output file")
    
    # generate
    generate_parser = subparsers.add_parser("generate", help="Generate crawler")
    generate_parser.add_argument("--from-recording", required=True, help="Recording file")
    generate_parser.add_argument("--output", default="crawler.yaml", help="Output file")
    
    # run
    run_parser = subparsers.add_parser("run", help="Run a crawler")
    run_parser.add_argument("crawler", help="Crawler file")
    run_parser.add_argument("--stealth", action="store_true", help="Use stealth mode")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    logging.basicConfig(level=logging.INFO)
    
    if args.command == "deep-analyze":
        asyncio.run(deep_analyze(args.url, args.full))
    elif args.command == "discover-apis":
        asyncio.run(discover_apis(args.url, args.include_hidden))
    elif args.command == "graphql-schema":
        asyncio.run(graphql_schema(args.endpoint))
    elif args.command == "record":
        asyncio.run(record_session(args.url, args.output))
    elif args.command == "generate":
        asyncio.run(generate_crawler(args.from_recording, args.output))
    elif args.command == "run":
        asyncio.run(run_crawler(args.crawler, args.stealth))


if __name__ == "__main__":
    main()

