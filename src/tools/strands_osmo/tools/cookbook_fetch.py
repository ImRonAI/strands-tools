"""Fetch a workflow spec from the OSMO cookbook."""
from __future__ import annotations

from pathlib import Path

from strands import tool

from ._common import err, ok

_COOKBOOK_BASE = (
    "https://raw.githubusercontent.com/NVIDIA/OSMO/main/cookbook"
)


@tool
def osmo_cookbook_fetch(category: str, recipe: str = "", local_root: str = "") -> dict:
    """Fetch a workflow spec from the OSMO cookbook.

    The OSMO cookbook ships pre-baked workflow YAMLs for common Physical AI
    pipelines (Cosmos, GR00T, Isaac Sim SDG, RL, ROS, mobility-gen, NIMs, …).
    Recipes live in nested subdirectories like
    ``cookbook/<category>/<subcategory>/<recipe>.yaml``.

    Args:
        category: Cookbook subdirectory, e.g. ``"reinforcement_learning"``,
                  ``"synthetic_data_generation"``, ``"cosmos"``, ``"groot"``,
                  ``"ros"``, ``"mobility_gen"``, ``"hil"``, ``"nims"``,
                  ``"nut_pouring"``, ``"dnn_training"``,
                  ``"integration_and_tools"``.
        recipe: Specific recipe path *relative to the category root*, e.g.
                ``"single_gpu/train"`` or ``"turtlebot/turtlebot_demo"``
                (omit ``.yaml``). When empty, lists every YAML in the category
                tree.
        local_root: If set, reads from a local OSMO checkout (e.g.
                    ``"./OSMO/cookbook"``) instead of GitHub raw.
    """
    if not category:
        return err("category is required")

    if local_root:
        root = Path(local_root).expanduser() / category
        if not root.exists():
            return err(f"local cookbook category not found: {root}")
        if not recipe:
            files = sorted(
                str(p.relative_to(root)).removesuffix(".yaml")
                for p in root.rglob("*.yaml")
            )
            return ok(
                text=f"{len(files)} recipes in {category}",
                data={"category": category, "recipes": files, "root": str(root)},
            )
        target = root / f"{recipe}.yaml"
        if not target.exists():
            return err(f"recipe not found: {target}")
        return ok(text=target.read_text(), data={"path": str(target)})

    if not recipe:
        listing_url = f"https://github.com/NVIDIA/OSMO/tree/main/cookbook/{category}"
        return ok(
            text=(
                f"Browse recipes at {listing_url}\n"
                f"(GitHub raw has no listing API - clone OSMO and pass "
                f"local_root='./OSMO/cookbook' to enumerate)"
            ),
            data={"listing_url": listing_url},
        )

    try:
        import urllib.request
    except Exception as e:
        return err(f"urllib unavailable: {e}")

    url = f"{_COOKBOOK_BASE}/{category}/{recipe}.yaml"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            content = resp.read().decode("utf-8")
    except Exception as e:
        return err(f"fetch failed for {url}: {type(e).__name__}: {e}")
    return ok(text=content, data={"url": url, "size": len(content)})
