"""Timeline management for video segments with gap adjustments."""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import streamlit as st


@dataclass
class TimelineSegment:
    """Represents a video segment on the timeline with connection metadata."""
    index: int  # Original segment index
    start: float  # Start time in original video
    end: float  # End time in original video
    gap_after: float = 0.0  # Gap duration after this segment (seconds)
    enabled: bool = True  # Whether this segment is included in output
    
    @property
    def duration(self) -> float:
        """Calculate segment duration."""
        return self.end - self.start
    
    def __str__(self) -> str:
        """String representation for debugging."""
        return f"Segment {self.index}: {self.start:.1f}s-{self.end:.1f}s (gap: {self.gap_after:.1f}s)"


@dataclass
class Timeline:
    """Manages the timeline of video segments with gap adjustments."""
    segments: List[TimelineSegment] = field(default_factory=list)
    
    @classmethod
    def from_time_ranges(cls, time_ranges: List[Tuple[float, float]]) -> 'Timeline':
        """Create a timeline from time ranges."""
        segments = []
        for i, (start, end) in enumerate(time_ranges):
            segment = TimelineSegment(
                index=i,
                start=start,
                end=end,
                gap_after=0.0  # Default no gap
            )
            segments.append(segment)
        return cls(segments=segments)
    
    def get_enabled_segments(self) -> List[TimelineSegment]:
        """Get only enabled segments."""
        return [seg for seg in self.segments if seg.enabled]
    
    def get_total_duration(self) -> float:
        """Calculate total duration including gaps."""
        total = 0.0
        enabled_segments = self.get_enabled_segments()
        
        for i, segment in enumerate(enabled_segments):
            total += segment.duration
            # Add gap if not the last segment
            if i < len(enabled_segments) - 1:
                total += segment.gap_after
                
        return total
    
    def get_segment_positions(self) -> List[Tuple[int, float, float]]:
        """Get positions of segments in the output timeline.
        
        Returns:
            List of (index, output_start, output_end) tuples
        """
        positions = []
        current_time = 0.0
        
        for segment in self.get_enabled_segments():
            output_start = current_time
            output_end = current_time + segment.duration
            positions.append((segment.index, output_start, output_end))
            
            current_time = output_end + segment.gap_after
            
        return positions
    
    def to_time_ranges_with_gaps(self) -> List[Tuple[float, float, float]]:
        """Convert to time ranges with gap information.
        
        Returns:
            List of (start, end, gap_after) tuples
        """
        return [
            (seg.start, seg.end, seg.gap_after)
            for seg in self.get_enabled_segments()
        ]
    
    def save_to_session_state(self, key: str = "timeline"):
        """Save timeline to Streamlit session state."""
        st.session_state[key] = self
    
    @classmethod
    def load_from_session_state(cls, key: str = "timeline") -> Optional['Timeline']:
        """Load timeline from Streamlit session state."""
        return st.session_state.get(key)