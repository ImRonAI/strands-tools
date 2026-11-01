"""
Asciimatics UI Tool - Dynamic Terminal UI Generation

High-level tool for creating dynamic terminal UIs using asciimatics.
Supports effects, widgets, renderers, particles, and scenes.
"""

from typing import Any, Dict, List, Optional
from strands import tool
import json
import subprocess
import tempfile
import os
import sys


@tool
def asciimatics_ui(
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create dynamic terminal UIs with asciimatics - effects, widgets, animations, particles.
    
    Args:
        config: UI configuration with structure:
            {
                "type": "effect" | "widget" | "form" | "animation",
                "scenes": [
                    {
                        "name": "scene_name",
                        "duration": 100,  # frames (-1 for infinite)
                        "clear": true,
                        "effects": [
                            {
                                "type": "Print" | "Matrix" | "Snow" | "Stars" | "BannerText" | "Scroll" | ...,
                                "renderer": {
                                    "type": "FigletText" | "Fire" | "Rainbow" | "BarChart" | ...,
                                    "params": {...}
                                },
                                "params": {...}
                            }
                        ],
                        "widgets": [
                            {
                                "type": "Frame",
                                "params": {
                                    "height": 20,
                                    "width": 80,
                                    "title": "My Form",
                                    "layouts": [
                                        {
                                            "columns": [1, 2, 1],
                                            "widgets": [
                                                {"type": "Label", "text": "Name:"},
                                                {"type": "Text", "name": "name"},
                                                ...
                                            ]
                                        }
                                    ]
                                }
                            }
                        ],
                        "particles": [
                            {
                                "type": "PalmFirework" | "StarFirework" | "Rain" | "Explosion" | ...,
                                "params": {...}
                            }
                        ]
                    }
                ],
                "palette": {
                    "background": (Screen.COLOUR_BLACK, Screen.A_NORMAL, Screen.COLOUR_BLACK),
                    ...
                },
                "stop_on_resize": false,
                "unhandled_input": "default"  # "default" | "stop" | "ignore"
            }
    
    Returns:
        Dict with status and results
        
    ## 🎨 AVAILABLE EFFECTS (18+):
        Matrix, Snow, Stars, Print, Scroll, BannerText, Clock, Cog, Cycle, 
        Julia, Mirage, RandomNoise, Wipe, Background
    
    ## 🖼️ AVAILABLE RENDERERS (15+):
        - Text: FigletText, Rainbow, Box, SpeechBubble
        - Graphics: Fire, Plasma, Kaleidoscope, ImageFile, ColourImageFile
        - Charts: BarChart, VBarChart (need callable functions, not static data!)
        - Special: AnsiArtPlayer, AsciinemaPlayer
    
    ## 📦 AVAILABLE WIDGETS (15+):
        Frame, Label, Text, TextBox, Button, CheckBox, RadioButtons,
        Divider, VerticalDivider, DatePicker, TimePicker, FileBrowser,
        ListBox, MultiColumnListBox, DropdownList, PopUpDialog, PopupMenu
    
    ## 🎆 AVAILABLE PARTICLES (20+):
        Fireworks: PalmFirework, StarFirework, RingFirework, SerpentFirework
        Explosions: Explosion, PalmExplosion, StarExplosion, RingExplosion, SerpentExplosion
        Effects: Rain, Splash, Rocket, StarTrail, ExplosionFlames
    
    ## ⚠️ COMMON ERRORS & SOLUTIONS:
    
    1. **Matrix Effect - NO height parameter**
       ❌ {"type": "Matrix", "params": {"height": 20}}
       ✅ {"type": "Matrix"}  # No params needed!
    
    2. **Fire Renderer - spot must be > 0**
       ❌ "spot": 0  # Causes randrange error
       ✅ "spot": 10  # Must be positive integer
       
       Required params: emitter (string), height, width, intensity, spot
       Example: {"emitter": "X" * 70, "height": 15, "width": 70, "intensity": 1, "spot": 10}
    
    3. **Fireworks - need life_time parameter**
       ❌ {"type": "PalmFirework", "params": {"x": 40, "y": 15}}
       ✅ {"type": "PalmFirework", "params": {"x": 40, "y": 15, "life_time": 100}}
    
    4. **Print Effect - x, y go in params**
       ❌ {"type": "Print", "x": 5, "y": 3, "renderer": {...}}
       ✅ {"type": "Print", "params": {"x": 5, "y": 3}, "renderer": {...}}
    
    5. **BarChart - uses "colour" not "colours"**
       ❌ "colours": 8
       ✅ "colour": 2
       
       Also: functions must be callables, NOT static arrays!
       Use Fire/Plasma/ImageFile for visual data representation instead.
    
    6. **ImageFile vs ColourImageFile**
       - ImageFile: Simple, just filename + height + colours
       - ColourImageFile: Advanced, needs screen object (auto-provided)
       
       ✅ {"type": "ImageFile", "params": {"filename": "/path/to/image.png", "height": 30, "colours": 256}}
    
    7. **Rainbow Renderer - needs another renderer inside**
       ❌ {"type": "Rainbow", "params": {...}}
       ✅ Rainbow wraps other renderers - use FigletText/Fire/etc as base, then wrap with Rainbow
    
    ## 🚀 WORKING EXAMPLES:
    
    ### Example 1: Simple Matrix Effect
    ```json
    {
        "scenes": [{
            "duration": 100,
            "effects": [{"type": "Matrix"}]
        }]
    }
    ```
    
    ### Example 2: Banner with FigletText
    ```json
    {
        "scenes": [{
            "duration": -1,
            "effects": [{
                "type": "Print",
                "params": {"x": 5, "y": 3},
                "renderer": {
                    "type": "FigletText",
                    "params": {"text": "DevDuck!", "font": "banner"}
                }
            }]
        }]
    }
    ```
    
    ### Example 3: Image Rendering (ASCII art from image)
    ```json
    {
        "scenes": [{
            "duration": -1,
            "effects": [{
                "type": "Print",
                "params": {"x": 5, "y": 3},
                "renderer": {
                    "type": "ImageFile",
                    "params": {
                        "filename": "/tmp/avatar.png",
                        "height": 30,
                        "colours": 256
                    }
                }
            }]
        }]
    }
    ```
    
    ### Example 4: Fire Effect (realistic fire animation)
    ```json
    {
        "scenes": [{
            "duration": 100,
            "effects": [{
                "type": "Print",
                "params": {"x": 5, "y": 3},
                "renderer": {
                    "type": "Fire",
                    "params": {
                        "emitter": "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
                        "height": 15,
                        "width": 70,
                        "intensity": 1,
                        "spot": 10,
                        "colours": 8
                    }
                }
            }]
        }]
    }
    ```
    
    ### Example 5: Plasma Effect (trippy colors)
    ```json
    {
        "scenes": [{
            "duration": 100,
            "effects": [{
                "type": "Print",
                "params": {"x": 10, "y": 5},
                "renderer": {
                    "type": "Plasma",
                    "params": {
                        "height": 20,
                        "width": 60,
                        "colours": 256
                    }
                }
            }]
        }]
    }
    ```
    
    ### Example 6: Fireworks Show
    ```json
    {
        "scenes": [{
            "duration": 200,
            "particles": [
                {
                    "type": "PalmFirework",
                    "params": {"x": 40, "y": 15, "life_time": 100}
                },
                {
                    "type": "StarFirework",
                    "params": {"x": 80, "y": 10, "life_time": 100}
                }
            ]
        }]
    }
    ```
    
    ### Example 7: Multi-Scene Demo
    ```json
    {
        "scenes": [
            {
                "name": "Scene 1: Matrix",
                "duration": 50,
                "effects": [{"type": "Matrix"}]
            },
            {
                "name": "Scene 2: Banner",
                "duration": 50,
                "effects": [{
                    "type": "Print",
                    "params": {"x": 5, "y": 3},
                    "renderer": {
                        "type": "FigletText",
                        "params": {"text": "DevDuck", "font": "banner"}
                    }
                }]
            },
            {
                "name": "Scene 3: Plasma",
                "duration": 50,
                "effects": [{
                    "type": "Print",
                    "params": {"x": 10, "y": 5},
                    "renderer": {
                        "type": "Plasma",
                        "params": {"height": 15, "width": 60, "colours": 256}
                    }
                }]
            },
            {
                "name": "Scene 4: Winter",
                "duration": 50,
                "effects": [
                    {"type": "Snow"},
                    {"type": "Stars", "params": {"count": 200}}
                ]
            }
        ]
    }
    ```
    
    ### Example 8: Form with Widgets
    ```json
    {
        "type": "widget",
        "scenes": [{
            "widgets": [{
                "type": "Frame",
                "params": {
                    "height": 15,
                    "width": 60,
                    "title": "User Form",
                    "layouts": [{
                        "columns": [1],
                        "widgets": [
                            {"type": "Label", "text": "Name:"},
                            {"type": "Text", "name": "name", "label": "Name:"},
                            {"type": "Text", "name": "email", "label": "Email:"},
                            {"type": "Button", "text": "Submit", "on_click": "submit"}
                        ]
                    }]
                }
            }]
        }]
    }
    ```
    
    ## 💡 PRO TIPS:
    - Use duration: -1 for infinite/manual scenes (user must press Q to quit)
    - Combine effects in one scene for complex visuals (Snow + Stars = winter night!)
    - Images work best with colours: 256 for full color terminals
    - Fire effect emitter length = width of fire
    - Multiple scenes = slideshow animation
    - Press Q to quit any running scene
    """
    try:
        # Parse config if string
        if isinstance(config, str):
            config = json.loads(config)
        
        # Create a temporary script file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            script_path = f.name
            f.write(_generate_script(config))
        
        try:
            # Get the python executable from the current environment
            python_executable = sys.executable
            
            # Run the script in a subprocess - don't capture output to keep TTY
            result = subprocess.run(
                [python_executable, script_path],
                check=True
            )
            
            return {
                "status": "success",
                "content": [
                    {"text": "UI rendered successfully"}
                ]
            }
        except subprocess.CalledProcessError as e:
            # If it fails, try running again with output capture for debugging
            result = subprocess.run(
                [python_executable, script_path],
                capture_output=True,
                text=True
            )
            return {
                "status": "error",
                "content": [
                    {"text": f"Subprocess error (exit code {result.returncode}):"},
                    {"text": f"STDOUT: {result.stdout}"},
                    {"text": f"STDERR: {result.stderr}"}
                ]
            }
        finally:
            # Clean up the temporary script
            try:
                os.unlink(script_path)
            except:
                pass
        
    except Exception as e:
        import traceback
        return {
            "status": "error",
            "content": [{"text": f"Error: {str(e)}\n{traceback.format_exc()}"}]
        }


def _generate_script(config: Dict[str, Any]) -> str:
    """Generate a Python script that runs the asciimatics UI"""
    config_json = json.dumps(config)
    
    return f'''
import json
from asciimatics.screen import Screen
from asciimatics.scene import Scene
from asciimatics import effects, renderers, widgets, particles

config = json.loads(\'\'\'{config_json}\'\'\')

def screen_wrapper(screen):
    ui_type = config.get("type", "effect")
    scenes_config = config.get("scenes", [])
    palette = config.get("palette", {{}})
    stop_on_resize = config.get("stop_on_resize", False)
    
    # Apply palette if provided
    if palette:
        for key, value in palette.items():
            if hasattr(screen, key):
                setattr(screen, key, value)
    
    # Build scenes with screen context
    all_scenes = []
    
    for scene_config in scenes_config:
        scene_effects = []
        scene_name = scene_config.get("name", f"Scene {{len(all_scenes)}}")
        scene_duration = scene_config.get("duration", -1)
        scene_clear = scene_config.get("clear", True)
        
        # Handle effects
        for effect_config in scene_config.get("effects", []):
            effect = _create_effect(effect_config, screen, effects, renderers)
            if effect:
                scene_effects.append(effect)
        
        # Handle widgets
        for widget_config in scene_config.get("widgets", []):
            widget_effect = _create_widget(widget_config, screen, widgets)
            if widget_effect:
                scene_effects.append(widget_effect)
        
        # Handle particles
        for particle_config in scene_config.get("particles", []):
            particle_effect = _create_particle(particle_config, screen, particles)
            if particle_effect:
                scene_effects.append(particle_effect)
        
        if scene_effects:
            all_scenes.append(
                Scene(scene_effects, duration=scene_duration, clear=scene_clear, name=scene_name)
            )
    
    if not all_scenes:
        raise ValueError("No valid scenes created from config")
    
    # Play scenes
    screen.play(
        all_scenes,
        stop_on_resize=stop_on_resize,
        repeat=False
    )

def _create_effect(effect_config, screen, effects_module, renderers_module):
    """Create an effect from configuration"""
    try:
        effect_type = effect_config.get("type")
        effect_params = effect_config.get("params", {{}}).copy()
        renderer_config = effect_config.get("renderer")
        
        # Create renderer if specified
        renderer = None
        if renderer_config:
            renderer = _create_renderer(renderer_config, screen, renderers_module)
        
        # Get effect class
        effect_class = getattr(effects_module, effect_type)
        
        # Add screen to params
        effect_params['screen'] = screen
        
        # Add renderer if present
        if renderer:
            effect_params['renderer'] = renderer
        
        return effect_class(**effect_params)
        
    except Exception as e:
        print(f"Error creating effect {{effect_config.get('type')}}: {{e}}")
        import traceback
        traceback.print_exc()
        return None

def _create_renderer(renderer_config, screen, renderers_module):
    """Create a renderer from configuration"""
    try:
        renderer_type = renderer_config.get("type")
        renderer_params = renderer_config.get("params", {{}}).copy()
        
        renderer_class = getattr(renderers_module, renderer_type)
        
        # Special handling for renderers that need screen
        if renderer_type == "ColourImageFile":
            renderer_params['screen'] = screen
        
        # Some renderers need width/height from screen if not provided
        if renderer_type in ['BarChart', 'VBarChart', 'Plasma']:
            if 'height' not in renderer_params:
                renderer_params['height'] = screen.height
            if 'width' not in renderer_params:
                renderer_params['width'] = screen.width
        
        return renderer_class(**renderer_params)
        
    except Exception as e:
        print(f"Error creating renderer {{renderer_config.get('type')}}: {{e}}")
        import traceback
        traceback.print_exc()
        return None

def _create_widget(widget_config, screen, widgets_module):
    """Create a widget (Frame) from configuration"""
    try:
        widget_type = widget_config.get("type")
        widget_params = widget_config.get("params", {{}})
        
        if widget_type != "Frame":
            return None
        
        # Create frame
        frame = widgets_module.Frame(
            screen,
            widget_params.get("height", screen.height),
            widget_params.get("width", screen.width),
            has_border=widget_params.get("has_border", True),
            title=widget_params.get("title", ""),
            reduce_cpu=widget_params.get("reduce_cpu", False)
        )
        
        # Add layouts and widgets
        for layout_config in widget_params.get("layouts", []):
            columns = layout_config.get("columns", [1])
            layout = widgets_module.Layout(columns, fill_frame=True)
            frame.add_layout(layout)
            
            for widget_item in layout_config.get("widgets", []):
                widget = _create_single_widget(widget_item, widgets_module, frame)
                if widget:
                    layout.add_widget(widget)
        
        frame.fix()
        return frame
        
    except Exception as e:
        print(f"Error creating widget {{widget_config.get('type')}}: {{e}}")
        import traceback
        traceback.print_exc()
        return None

def _create_single_widget(widget_config, widgets_module, frame):
    """Create individual widgets for layout"""
    try:
        widget_type = widget_config.get("type")
        widget_class = getattr(widgets_module, widget_type)
        
        if widget_type == "Label":
            return widget_class(widget_config.get("text", ""))
        
        elif widget_type == "Text":
            return widget_class(
                label=widget_config.get("label", ""),
                name=widget_config.get("name", "text"),
                max_length=widget_config.get("max_length", 0)
            )
        
        elif widget_type == "TextBox":
            return widget_class(
                height=widget_config.get("height", 5),
                label=widget_config.get("label", ""),
                name=widget_config.get("name", "textbox"),
                as_string=widget_config.get("as_string", True)
            )
        
        elif widget_type == "Button":
            return widget_class(
                text=widget_config.get("text", "Button"),
                on_click=frame._on_close if widget_config.get("on_click") == "submit" else None
            )
        
        elif widget_type == "CheckBox":
            return widget_class(
                text=widget_config.get("text", ""),
                label=widget_config.get("label", ""),
                name=widget_config.get("name", "checkbox")
            )
        
        elif widget_type == "RadioButtons":
            return widget_class(
                options=widget_config.get("options", []),
                label=widget_config.get("label", ""),
                name=widget_config.get("name", "radio")
            )
        
        elif widget_type == "Divider":
            return widget_class()
        
        elif widget_type == "VerticalDivider":
            return widget_class()
        
        else:
            # Generic widget creation
            return widget_class(**widget_config.get("params", {{}}))
        
    except Exception as e:
        print(f"Error creating widget {{widget_config.get('type')}}: {{e}}")
        import traceback
        traceback.print_exc()
        return None

def _create_particle(particle_config, screen, particles_module):
    """Create a particle effect from configuration"""
    try:
        particle_type = particle_config.get("type")
        particle_params = particle_config.get("params", {{}}).copy()
        
        particle_class = getattr(particles_module, particle_type)
        
        # Add screen to params
        particle_params['screen'] = screen
        
        return particle_class(**particle_params)
        
    except Exception as e:
        print(f"Error creating particle {{particle_config.get('type')}}: {{e}}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    Screen.wrapper(screen_wrapper)
'''
