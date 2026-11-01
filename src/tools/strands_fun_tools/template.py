"""Template engine for generating text from Jinja2 templates"""

from typing import Dict, Any, Optional, List
import os
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
import json
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from strands import tool

console = Console()

TEMPLATE_DIR = Path.cwd() / "templates"
TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)

env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    trim_blocks=True,
    lstrip_blocks=True,
    autoescape=True,
)


def get_template_path(name: str) -> Path:
    """Get template file path"""
    return TEMPLATE_DIR / f"{name}.j2"


@tool
def template(
    action: str,
    template_name: Optional[str] = None,
    content: Optional[str] = None,
    variables: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Template engine for generating text from Jinja2 templates

    Args:
        action: Action to perform (create, render, list)
        template_name: Template name
        content: Template content for create action
        variables: Variables for rendering

    Returns:
        Dict with status and content
    """
    try:
        if action == "create":
            if not template_name or not content:
                return {
                    "status": "error",
                    "content": [{"text": "❌ Template name and content required"}],
                }

            template_path = get_template_path(template_name)

            syntax = Syntax(content, "jinja", theme="monokai", line_numbers=True)
            console.print(Panel(syntax, title=f"[green]Creating: {template_name}"))

            with open(template_path, "w") as f:
                f.write(content)

            console.print("[green]✓[/green] Template saved!")

            return {
                "status": "success",
                "content": [
                    {"text": f"✅ Created template: {template_name}"},
                    {"text": f"Path: {template_path}"},
                ],
            }

        elif action == "render":
            if not template_name:
                return {
                    "status": "error",
                    "content": [{"text": "❌ Template name required"}],
                }

            template_path = get_template_path(template_name)
            if not template_path.exists():
                return {
                    "status": "error",
                    "content": [{"text": f"❌ Template not found: {template_name}"}],
                }

            vars_dict = variables or {}

            # Show variables
            if vars_dict:
                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("Variable", style="cyan")
                table.add_column("Value", style="green")
                for k, v in vars_dict.items():
                    table.add_row(str(k), str(v))
                console.print(Panel(table, title="[blue]Variables"))

            with open(template_path) as f:
                tmpl_content = f.read()

            tmpl = env.from_string(tmpl_content)
            rendered = tmpl.render(**vars_dict)

            console.print(Panel(rendered, title="[cyan]Rendered"))

            return {
                "status": "success",
                "content": [
                    {"text": "✅ Template rendered"},
                    {"text": f"Output:\n{rendered}"},
                ],
            }

        elif action == "list":
            templates: List[Dict[str, Any]] = []

            for path in TEMPLATE_DIR.glob("*.j2"):
                with open(path) as f:
                    tmpl_content = f.read()
                templates.append(
                    {"name": path.stem, "path": str(path), "content": tmpl_content}
                )

            if templates:
                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("Template", style="cyan")
                table.add_column("Path", style="green")

                for tmpl in sorted(templates, key=lambda x: x["name"]):
                    table.add_row(tmpl["name"], tmpl["path"])

                console.print(Panel(table, title="[yellow]Templates"))
            else:
                console.print("[yellow]No templates found")

            content_list = [{"text": f"✅ Found {len(templates)} templates"}]
            for tmpl in templates:
                content_list.append({"text": f"\n{tmpl['name']}: {tmpl['path']}"})

            return {"status": "success", "content": content_list}

        return {
            "status": "error",
            "content": [{"text": f"❌ Unknown action: {action}"}],
        }

    except Exception as e:
        return {"status": "error", "content": [{"text": f"❌ Error: {str(e)}"}]}
