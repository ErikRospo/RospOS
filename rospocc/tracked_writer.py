"""
TrackedWriter: A file wrapper that tracks source line mappings during code generation.

This module provides real-time tracking of which source lines produced which output lines,
eliminating the need for heuristic matching after the fact.
"""

from typing import Optional, TextIO


class TrackedWriter:
    """
    A wrapper around a file object that tracks source line mappings as code is written.
    
    Each write operation can optionally specify the source file and line that originated it.
    The tracker maintains a mapping from output line numbers to source locations.
    """
    
    def __init__(self, file_handle: TextIO, source_file: str):
        """
        Initialize the tracked writer.
        
        Args:
            file_handle: The underlying file object to write to
            source_file: Path to the source file being compiled
        """
        self.file = file_handle
        self.source_file = source_file
        self.current_output_line = 1
        self.current_source_line: Optional[int] = None
        self.current_source_text: Optional[str] = None
        self.mappings = []  # List of (output_line, source_line, source_text) tuples
        self.buffer = ""  # Buffer for incomplete lines
        
    def set_source_context(self, line: Optional[int], text: Optional[str] = None):
        """
        Set the current source context for subsequent writes.
        
        Args:
            line: The source line number, or None to clear context
            text: Optional source text for this line
        """
        self.current_source_line = line
        self.current_source_text = text
        
    def write(self, text: str):
        """
        Write text to the file and track source mappings.
        
        Args:
            text: The text to write
        """
        if not text:
            return
            
        self.file.write(text)
        
        # Split into lines and track each one
        self.buffer += text
        lines = self.buffer.split('\n')
        
        # All complete lines (all but the last fragment)
        for line in lines[:-1]:
            # Record mapping for this output line
            self.mappings.append({
                'output_line': self.current_output_line,
                'source_line': self.current_source_line or 1,
                'source_text': self.current_source_text or "",
                'output_text': line
            })
            self.current_output_line += 1
        
        # Keep the last incomplete line in buffer
        self.buffer = lines[-1]
        
    def flush(self):
        """Flush any remaining buffered data."""
        if self.buffer:
            # Record final incomplete line if it exists
            self.mappings.append({
                'output_line': self.current_output_line,
                'source_line': self.current_source_line or 1,
                'source_text': self.current_source_text or "",
                'output_text': self.buffer
            })
            self.buffer = ""
        self.file.flush()
        
    def get_mappings(self):
        """
        Get all recorded source-to-output mappings.
        
        Returns:
            List of mapping dictionaries
        """
        return self.mappings
        
    def close(self):
        """Close the writer and flush any remaining data."""
        self.flush()
