"""FunctionTool callables for the NgReact agent."""
from .angular_parser import parse_angular_source
from .react_validator import validate_react_code

__all__ = [
    "parse_angular_source",
    "validate_react_code",
]
