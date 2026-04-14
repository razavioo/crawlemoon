"""Crawler generator from state machines and recordings.

Converts a :class:`~intelligence.recorder.session.SessionRecording` or a
:class:`~intelligence.recorder.state_machine.StateMachine` into an executable
crawler definition that can be serialised to Python, YAML, or a Playwright
test script.
"""

import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from ..recorder.session import SessionRecording
from ..recorder.state_machine import StateMachine, StateType
from ...exceptions import CrawlerGenerationError

logger = logging.getLogger(__name__)


@dataclass
class CrawlerDefinition:
    """A portable crawler definition."""

    name: str
    description: str
    steps: List[Dict[str, Any]] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Action-type helpers
# ---------------------------------------------------------------------------

_EVENT_TYPE_MAP = {
    "click": "click",
    "type": "fill",
    "scroll": "scroll",
    "navigate": "navigate",
    "wait": "wait",
    "hover": "hover",
}


class CrawlerGenerator:
    """Generates crawlers from recordings or state machines."""

    # ------------------------------------------------------------------
    # Core generators
    # ------------------------------------------------------------------

    def from_state_machine(self, sm: StateMachine) -> CrawlerDefinition:
        """Generate a crawler from a :class:`~recorder.state_machine.StateMachine`.

        The generator walks each state in topological order (initial → … →
        final) and emits the corresponding transition action as a step.

        Args:
            sm: A populated state machine, typically produced by
                :class:`~recorder.state_machine.StateMachineGenerator`.

        Returns:
            A :class:`CrawlerDefinition` whose steps reproduce the state machine.

        Raises:
            CrawlerGenerationError: When the state machine contains no states.
        """
        if not sm.states:
            raise CrawlerGenerationError(
                "Cannot generate a crawler from an empty state machine."
            )

        logger.info(
            "Generating crawler from state machine (%d states, %d transitions)",
            len(sm.states),
            len(sm.transitions),
        )

        steps: List[Dict[str, Any]] = []

        # Navigate to the initial state URL
        if sm.initial_state and sm.initial_state.url:
            steps.append({"action": "navigate", "url": sm.initial_state.url})

        # Build a mapping from state_id → state for fast lookup
        state_by_id = {s.id: s for s in sm.states}

        # Emit one step per transition, in order
        for transition in sm.transitions:
            to_state = state_by_id.get(transition.to_state)
            action = transition.action

            if action == "navigate" and to_state:
                steps.append({"action": "navigate", "url": to_state.url})
            elif action == "click":
                step: Dict[str, Any] = {"action": "click"}
                if transition.condition:
                    step["selector"] = transition.condition
                steps.append(step)
            else:
                # Generic action passthrough
                step = {"action": action}
                if transition.condition:
                    step["condition"] = transition.condition
                if to_state:
                    step["target_url"] = to_state.url
                steps.append(step)

        # Emit data-extraction steps at their respective states
        for ep in sm.data_extraction_points:
            steps.append({
                "action": "extract",
                "selector": ep.selector,
                "field": ep.field_name,
                "extractor": ep.extractor_type,
                "at_state": ep.state_id,
            })

        initial_url = sm.initial_state.url if sm.initial_state else ""
        return CrawlerDefinition(
            name="generated_crawler",
            description=(
                f"Generated from state machine with {len(sm.states)} states"
            ),
            steps=steps,
            config={"initial_url": initial_url},
        )

    def from_recording(self, recording: SessionRecording) -> CrawlerDefinition:
        """Generate a crawler from a :class:`~recorder.session.SessionRecording`.

        Args:
            recording: A completed session recording.

        Returns:
            A :class:`CrawlerDefinition` that replays the recording.
        """
        steps: List[Dict[str, Any]] = []

        for event in recording.events:
            action = _EVENT_TYPE_MAP.get(event.type.value, event.type.value)

            if event.type.value == "navigate":
                url = event.data.get("url", "")
                if url:
                    steps.append({"action": "navigate", "url": url})

            elif event.type.value == "click":
                step: Dict[str, Any] = {"action": "click"}
                if event.selector:
                    step["selector"] = event.selector
                if event.data:
                    step["data"] = event.data
                steps.append(step)

            elif event.type.value == "type":
                step = {"action": "fill"}
                if event.selector:
                    step["selector"] = event.selector
                step["value"] = event.data.get("value", "")
                steps.append(step)

            elif event.type.value == "scroll":
                steps.append({
                    "action": "scroll",
                    "x": event.data.get("x", 0),
                    "y": event.data.get("y", 0),
                })

            elif event.type.value == "hover":
                step = {"action": "hover"}
                if event.selector:
                    step["selector"] = event.selector
                steps.append(step)

            elif event.type.value == "wait":
                steps.append({
                    "action": "wait",
                    "timeout": event.data.get("timeout", 1000),
                })

        initial_url = (
            recording.state_snapshots[0].url if recording.state_snapshots else ""
        )
        return CrawlerDefinition(
            name=f"crawler_{recording.id}",
            description=f"Generated from recording {recording.id}",
            steps=steps,
            config={"initial_url": initial_url},
        )

    # ------------------------------------------------------------------
    # Optimiser
    # ------------------------------------------------------------------

    def optimize_crawler(self, crawler: CrawlerDefinition) -> CrawlerDefinition:
        """Optimise a crawler definition by removing redundant steps.

        Optimisations applied:
        - Consecutive ``navigate`` steps to the same URL are deduplicated.
        - ``wait`` steps immediately followed by a ``navigate`` are dropped
          (navigation itself implies a wait).
        - Empty ``fill`` steps (no value) are dropped.

        Args:
            crawler: The crawler to optimise.

        Returns:
            A new :class:`CrawlerDefinition` with optimised steps.
        """
        if not crawler.steps:
            return crawler

        optimised: List[Dict[str, Any]] = []
        prev: Optional[Dict[str, Any]] = None

        for i, step in enumerate(crawler.steps):
            action = step.get("action")

            # Drop wait immediately before navigate
            if (
                prev is not None
                and prev.get("action") == "wait"
                and action == "navigate"
            ):
                optimised.pop()

            # Deduplicate consecutive navigations to same URL
            if (
                prev is not None
                and action == "navigate"
                and prev.get("action") == "navigate"
                and step.get("url") == prev.get("url")
            ):
                prev = step
                continue

            # Drop empty fill steps
            if action == "fill" and not step.get("value"):
                prev = step
                continue

            optimised.append(step)
            prev = step

        total_removed = len(crawler.steps) - len(optimised)
        if total_removed:
            logger.info(
                "Optimised crawler '%s': removed %d redundant step(s)",
                crawler.name,
                total_removed,
            )

        return CrawlerDefinition(
            name=crawler.name,
            description=crawler.description,
            steps=optimised,
            config=crawler.config,
        )

    # ------------------------------------------------------------------
    # Serialisers
    # ------------------------------------------------------------------

    def to_yaml(self, crawler: CrawlerDefinition) -> str:
        """Serialise a crawler to YAML.

        Args:
            crawler: The crawler to serialise.

        Returns:
            YAML string.
        """
        import yaml  # type: ignore[import]

        return yaml.dump(
            {
                "name": crawler.name,
                "description": crawler.description,
                "config": crawler.config,
                "steps": crawler.steps,
            },
            default_flow_style=False,
        )

    def to_python_code(self, crawler: CrawlerDefinition) -> str:
        """Serialise a crawler to a standalone async Python script.

        Args:
            crawler: The crawler to serialise.

        Returns:
            Python source code string.
        """
        lines = [
            f"# Generated crawler: {crawler.name}",
            "from playwright.async_api import async_playwright",
            "",
            "",
            "async def run_crawler():",
            "    async with async_playwright() as p:",
            "        browser = await p.chromium.launch(headless=True)",
            "        context = await browser.new_context()",
            "        page = await context.new_page()",
            "",
        ]

        for step in crawler.steps:
            action = step.get("action")
            if action == "navigate":
                lines.append(f'        await page.goto("{step.get("url")}")')
            elif action == "click":
                sel = step.get("selector", "")
                lines.append(f'        await page.click("{sel}")')
            elif action == "fill":
                sel = step.get("selector", "")
                val = step.get("value", "")
                lines.append(f'        await page.fill("{sel}", "{val}")')
            elif action == "scroll":
                x, y = step.get("x", 0), step.get("y", 0)
                lines.append(f"        await page.evaluate('window.scrollTo({x}, {y})')")
            elif action == "hover":
                sel = step.get("selector", "")
                lines.append(f'        await page.hover("{sel}")')
            elif action == "wait":
                t = step.get("timeout", 1000)
                lines.append(f"        await page.wait_for_timeout({t})")
            elif action == "extract":
                sel = step.get("selector", "")
                field_name = step.get("field", "data")
                lines.append(
                    f'        {field_name} = await page.locator("{sel}").inner_text()'
                )

        lines += [
            "",
            "        await browser.close()",
            "",
            "",
            'if __name__ == "__main__":',
            "    import asyncio",
            "    asyncio.run(run_crawler())",
            "",
        ]
        return "\n".join(lines)

    def to_playwright_script(self, crawler: CrawlerDefinition) -> str:
        """Serialise a crawler to a pytest-playwright test script.

        Args:
            crawler: The crawler to serialise.

        Returns:
            Python source code string containing a pytest test function.
        """
        func_name = (
            crawler.name.lower()
            .replace(" ", "_")
            .replace("-", "_")
        )
        lines = [
            f'"""Generated Playwright test for: {crawler.description}"""',
            "",
            "import pytest",
            "from playwright.sync_api import Page",
            "",
            "",
            f"def test_{func_name}(page: Page) -> None:",
        ]

        for step in crawler.steps:
            action = step.get("action")
            if action == "navigate":
                lines.append(f'    page.goto("{step.get("url")}")')
            elif action == "click":
                sel = step.get("selector", "")
                lines.append(f'    page.locator("{sel}").click()')
            elif action == "fill":
                sel = step.get("selector", "")
                val = step.get("value", "")
                lines.append(f'    page.locator("{sel}").fill("{val}")')
            elif action == "wait":
                t = step.get("timeout", 1000)
                lines.append(f"    page.wait_for_timeout({t})")
            elif action == "scroll":
                x, y = step.get("x", 0), step.get("y", 0)
                lines.append(f"    page.evaluate('window.scrollTo({x}, {y})')")
            elif action == "hover":
                sel = step.get("selector", "")
                lines.append(f'    page.locator("{sel}").hover()')
            elif action == "screenshot":
                path = step.get("path", "screenshot.png")
                lines.append(f'    page.screenshot(path="{path}")')

        if not any(
            s.get("action") not in ("extract",) for s in crawler.steps
        ):
            lines.append("    pass")

        lines.append("")
        return "\n".join(lines)
