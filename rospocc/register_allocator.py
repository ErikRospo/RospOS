"""
Register Allocator Tracker: Tracks variable-to-register mappings during code generation.

This module maintains a detailed record of which variables/temporaries are allocated
to which registers at each output line of the generated assembly code. This information
is exported to a sidecar .rosc.regalloc file for use by the assembler and VM.
"""

from typing import Dict, List, Optional, Tuple
import json


class RegAllocation:
    """Represents a single register allocation at a specific output line."""

    def __init__(
        self,
        output_line: int,
        register: str,
        variable_name: str,
        variable_type: str,
        var_kind: str = "local",
        origin: Optional[str] = None,
        action: str = "allocate",
    ):
        """
        Initialize a register allocation record.

        Args:
            output_line: The output line number where this allocation is active
            register: The register name (e.g., "r0", "r1")
            variable_name: The name of the variable/temporary
            variable_type: The type hint of the variable ("int", "char_ptr", struct name, etc.)
            var_kind: Kind of variable ("local", "param", "temp", "label")
            origin: Optional origin info (e.g., "if_block_123", "for_loop_456", "_entry_point")
        """
        self.output_line = output_line
        self.register = register
        self.variable_name = variable_name
        self.variable_type = variable_type
        self.var_kind = var_kind
        self.origin = origin
        self.action = action

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "output_line": self.output_line,
            "register": self.register,
            "variable_name": self.variable_name,
            "variable_type": self.variable_type,
            "var_kind": self.var_kind,
            "origin": self.origin,
            "action": self.action,
        }


class RegisterAllocator:
    """
    Tracks register-to-variable mappings throughout code generation.

    This tracker maintains a log of register allocations and deallocations as code
    is emitted, allowing precise tracking of what each register holds at each point
    in the generated assembly.
    """

    def __init__(self):
        """Initialize the register allocator tracker."""
        self.allocations: List[RegAllocation] = []
        self.current_output_line = 0
        # Current active allocations: register -> (var_name, var_type, var_kind, origin)
        self.active_allocations: Dict[
            str, Tuple[str, str, str, Optional[str]]
        ] = {}

    def set_output_line(self, line_num: int):
        """Update the current output line number."""
        self.current_output_line = line_num

    def allocate(
        self,
        register: str,
        variable_name: str,
        variable_type: str,
        var_kind: str = "local",
        origin: Optional[str] = None,
    ):
        """
        Record a register allocation.

        Args:
            register: The register being allocated
            variable_name: Name of the variable/temporary
            variable_type: Type hint of the variable
            var_kind: Kind of variable ("local", "param", "temp", "label")
            origin: Optional origin info for synthetic variables
        """
        # Mark this allocation as active
        self.active_allocations[register] = (
            variable_name,
            variable_type,
            var_kind,
            origin,
        )

        # Log the allocation
        alloc = RegAllocation(
            output_line=self.current_output_line,
            register=register,
            variable_name=variable_name,
            variable_type=variable_type,
            var_kind=var_kind,
            origin=origin,
        )
        self.allocations.append(alloc)

    def deallocate(self, register: str):
        """
        Record that a register is no longer allocated.

        Args:
            register: The register being freed
        """
        if register in self.active_allocations:
            # Log deallocation event so downstream can remove tooltip metadata.
            alloc = RegAllocation(
                output_line=self.current_output_line,
                register=register,
                variable_name="",
                variable_type="",
                var_kind="",
                origin=None,
                action="free",
            )
            self.allocations.append(alloc)
            del self.active_allocations[register]

    def get_active_allocations(self) -> Dict[str, Tuple[str, str, str, Optional[str]]]:
        """
        Get the current active allocations for all registers.

        Returns:
            Dictionary mapping register names to (var_name, var_type, var_kind, origin) tuples
        """
        return self.active_allocations.copy()

    def export_allocations(self) -> List[Dict]:
        """
        Export all allocations as a list of dictionaries for JSON serialization.

        Returns:
            List of allocation dictionaries
        """
        return [alloc.to_dict() for alloc in self.allocations]

    def write_to_file(self, filepath: str):
        """
        Write register allocation data to a sidecar file.

        The file format is JSON with the following structure:
        {
            "version": 1,
            "allocations": [
                {
                    "output_line": <line_num>,
                    "register": "<reg_name>",
                    "variable_name": "<var_name>",
                    "variable_type": "<type>",
                    "var_kind": "<kind>",
                    "origin": "<origin_info>" or null
                },
                ...
            ]
        }

        Args:
            filepath: Path to write the sidecar file to
        """
        data = {
            "version": 1,
            "allocations": self.export_allocations(),
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
