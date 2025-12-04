"""State machine generator from recordings."""

import logging
from typing import List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class StateType(Enum):
    """State type."""
    INITIAL = "initial"
    INTERMEDIATE = "intermediate"
    FINAL = "final"
    LOOP = "loop"


@dataclass
class State:
    """State in state machine."""
    
    id: str
    name: str
    url: str
    type: StateType
    snapshot: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Transition:
    """Transition between states."""
    
    from_state: str
    to_state: str
    action: str  # "click", "navigate", etc.
    condition: Optional[str] = None


@dataclass
class ExtractionPoint:
    """Data extraction point."""
    
    state_id: str
    selector: str
    field_name: str
    extractor_type: str = "text"  # "text", "attribute", "html"


@dataclass
class StateMachine:
    """State machine representation."""
    
    states: List[State] = field(default_factory=list)
    transitions: List[Transition] = field(default_factory=list)
    initial_state: Optional[State] = None
    data_extraction_points: List[ExtractionPoint] = field(default_factory=list)


class StateMachineGenerator:
    """Generates state machines from recordings."""
    
    def analyze_recording(self, recording) -> StateMachine:
        """Analyze recording and generate state machine."""
        sm = StateMachine()
        
        # Create states from snapshots
        for i, snapshot in enumerate(recording.state_snapshots):
            state = State(
                id=f"state_{i}",
                name=f"State {i}",
                url=snapshot.url,
                type=StateType.INITIAL if i == 0 else StateType.INTERMEDIATE,
            )
            sm.states.append(state)
            
            if i == 0:
                sm.initial_state = state
        
        # Create transitions from events
        current_state_idx = 0
        for event in recording.events:
            if event.type.value == "navigate":
                # New state
                new_state = State(
                    id=f"state_{len(sm.states)}",
                    name=f"State {len(sm.states)}",
                    url=event.data.get("url", ""),
                    type=StateType.INTERMEDIATE,
                )
                sm.states.append(new_state)
                
                # Transition
                transition = Transition(
                    from_state=sm.states[current_state_idx].id,
                    to_state=new_state.id,
                    action="navigate",
                )
                sm.transitions.append(transition)
                current_state_idx = len(sm.states) - 1
        
        return sm
    
    def identify_states(self, recording) -> List[State]:
        """Identify distinct states in recording."""
        sm = self.analyze_recording(recording)
        return sm.states
    
    def identify_transitions(self, recording) -> List[Transition]:
        """Identify transitions in recording."""
        sm = self.analyze_recording(recording)
        return sm.transitions
    
    def find_loops(self, recording) -> List[Dict[str, Any]]:
        """Find loops in recording."""
        # Detect repetitive patterns
        loops = []
        # Implementation would analyze event patterns
        return loops
    
    def find_conditions(self, recording) -> List[Dict[str, Any]]:
        """Find conditional branches in recording."""
        conditions = []
        # Implementation would analyze branching patterns
        return conditions



