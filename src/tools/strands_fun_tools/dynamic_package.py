"""Dynamically load and execute functions from any Python package"""

from typing import Dict, Any, List, Optional
import inspect
import importlib
import ast
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from strands import tool

console = Console()


def convert_arg(arg):
    """Convert string argument to appropriate Python type"""
    try:
        if isinstance(arg, str) and arg.startswith("import:"):
            module_name = arg.split(":")[1]
            return importlib.import_module(module_name)
        return ast.literal_eval(arg)
    except (ValueError, SyntaxError):
        return arg


@tool
def dynamic_package(
    package_name: str,
    function_name: Optional[str] = None,
    args: Optional[List[str]] = None,
    kwargs: Optional[Dict] = None,
    list_functions: bool = False,
) -> Dict[str, Any]:
    """Dynamically load and execute functions from any installed Python package

    Args:
        package_name: Name of the package (e.g., 'requests', 'numpy')
        function_name: Function to call from the package
        args: Positional arguments (use 'import:module_name' for modules)
        kwargs: Keyword arguments
        list_functions: If True, list available functions

    Returns:
        Dict with status and content
    """
    try:
        console.print(Panel(f"[cyan]Loading package: [yellow]{package_name}"))
        module = importlib.import_module(package_name)

        # List functions
        if list_functions:
            functions = {}
            for name, obj in inspect.getmembers(module):
                if inspect.isfunction(obj) or inspect.ismethod(obj):
                    try:
                        sig = str(inspect.signature(obj))
                        doc = inspect.getdoc(obj) or "No docs"
                        functions[name] = {"sig": sig, "doc": doc.split("\n")[0]}
                    except:
                        pass

            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Function", style="cyan")
            table.add_column("Signature", style="green")

            for name, info in list(functions.items())[:20]:  # Limit to 20
                table.add_row(name, info["sig"])

            console.print(table)

            return {
                "status": "success",
                "content": [
                    {"text": f"✅ Found {len(functions)} functions in {package_name}"}
                ],
            }

        # Execute function
        if function_name:
            console.print(Panel(f"[cyan]Executing: [yellow]{function_name}"))
            func = getattr(module, function_name)

            # Convert arguments
            converted_args = []
            for arg in args or []:
                converted_args.append(convert_arg(arg))

            result = func(*converted_args, **(kwargs or {}))

            console.print(Panel(f"[green]Result:\n{result}"))

            return {
                "status": "success",
                "content": [
                    {"text": f"✅ Executed {function_name} from {package_name}"},
                    {"text": f"Result: {str(result)}"},
                ],
            }

        return {
            "status": "success",
            "content": [
                {
                    "text": f"✅ Package '{package_name}' loaded. Use list_functions=True or specify function_name"
                }
            ],
        }

    except Exception as e:
        return {"status": "error", "content": [{"text": f"❌ Error: {str(e)}"}]}
