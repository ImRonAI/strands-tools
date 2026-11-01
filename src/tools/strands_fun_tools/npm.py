"""Execute NPM packages and Node.js functions dynamically"""

from typing import Dict, Any, List, Optional
import json
import subprocess
from strands import tool


def create_js_script(
    package_name: str, function_name: Optional[str], args: List, kwargs: Dict
) -> str:
    """Create temporary JS script with ESM support"""
    if function_name:
        return f"""
        (async () => {{
            try {{
                let pkg;
                try {{
                    pkg = await import('{package_name}');
                }} catch (e) {{
                    pkg = require('{package_name}');
                }}
                
                // Handle both default and named exports
                const module = pkg.default || pkg;
                const args = {json.dumps(args or [])};
                
                let result;
                if (typeof module.{function_name} === 'function') {{
                    result = await module.{function_name}(...args);
                }} else if (typeof module === 'function') {{
                    result = await module(...args);
                }} else {{
                    throw new Error('Function not found: {function_name}');
                }}
                
                console.log(JSON.stringify({{ status: 'success', result }}));
            }} catch (error) {{
                console.log(JSON.stringify({{ status: 'error', error: error.message }}));
            }}
        }})();
        """
    else:
        return f"""
        (async () => {{
            try {{
                let pkg;
                try {{
                    pkg = await import('{package_name}');
                }} catch (e) {{
                    pkg = require('{package_name}');
                }}
                
                const module = pkg.default || pkg;
                const functions = Object.keys(module).filter(k => typeof module[k] === 'function');
                console.log(JSON.stringify({{ status: 'success', result: functions }}));
            }} catch (error) {{
                console.log(JSON.stringify({{ status: 'error', error: error.message }}));
            }}
        }})();
        """


@tool
def npm(
    package_name: str,
    function_name: Optional[str] = None,
    args: Optional[List] = None,
    kwargs: Optional[Dict] = None,
    list_functions: bool = False,
) -> Dict[str, Any]:
    """Dynamically execute NPM package functions

    Args:
        package_name: Name of the NPM package
        function_name: Function to call
        args: Positional arguments
        kwargs: Keyword arguments
        list_functions: If True, list available functions

    Returns:
        Dict with status and content
    """
    try:
        script = create_js_script(
            package_name,
            None if list_functions else function_name,
            args or [],
            kwargs or {},
        )

        result = subprocess.run(["node", "-e", script], capture_output=True, text=True)

        if result.returncode != 0:
            return {
                "status": "error",
                "content": [{"text": f"❌ Node.js error: {result.stderr}"}],
            }

        output = json.loads(result.stdout)

        if output["status"] == "error":
            return {
                "status": "error",
                "content": [{"text": f"❌ Function error: {output['error']}"}],
            }

        if list_functions:
            return {
                "status": "success",
                "content": [
                    {"text": f"✅ Functions in {package_name}:"},
                    {"text": json.dumps(output["result"], indent=2)},
                ],
            }

        return {
            "status": "success",
            "content": [
                {"text": f"✅ Executed {function_name} from {package_name}"},
                {"text": json.dumps(output["result"], indent=2)},
            ],
        }

    except Exception as e:
        return {"status": "error", "content": [{"text": f"❌ Error: {str(e)}"}]}
