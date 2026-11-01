"""Strands Pack YouTube workspace: YouTube Data API, Analytics, Read/Write, and Transcripts."""

from fastmcp.apps.app import FastMCPApp
from prefab_ui.app import PrefabApp
from pydantic import BaseModel

from strands_server.apps.recipes import (
    ColumnSpec,
    ListSpec,
    list_workspace,
    register_detail_backend,
    register_form_backend,
    register_list_backend,
)

GENERATED_TOOLS = frozenset(
    {"youtube", "youtube_read", "youtube_write", "youtube_analytics", "youtube_transcript"}
)


class YouTubeTranscriptForm(BaseModel):
    action: str = "get_transcript"
    video_id: str = "dQw4w9WgXcQ"


COLUMNS = (
    ColumnSpec("name", "Tool"),
    ColumnSpec("suite", "Suite"),
    ColumnSpec("tags", "Tags"),
    ColumnSpec("description", "Description"),
)

app = FastMCPApp("strands-youtube")

youtube_tools_list = register_list_backend(
    app,
    name="youtube_tools_list",
    spec=ListSpec(
        tool="strands_my_catalog",
        data_path=("rows",),
        columns=COLUMNS,
        paging="none",
        static_args={"action": "list_tools", "suite": "youtube"},
    ),
)
youtube_tool_detail = register_detail_backend(
    app,
    name="youtube_tool_detail",
    tool="strands_my_catalog",
    id_param="query",
    static_args={"action": "list_tools", "suite": "youtube"},
)
youtube_transcript_run = register_form_backend(
    app, name="youtube_transcript_run", tool="youtube_transcript", model=YouTubeTranscriptForm
)


def workspace() -> PrefabApp:
    return list_workspace(
        title="Strands Pack YouTube Suite Workspace",
        list_backend=youtube_tools_list,
        columns=COLUMNS,
        detail_backend=youtube_tool_detail,
        detail_fields=(("text", "Details"),),
        create_form=(YouTubeTranscriptForm, youtube_transcript_run),
        notes=(
            "Includes youtube, youtube_read, youtube_write, youtube_analytics, and youtube_transcript from strands-pack.",
        ),
    )


@app.ui("youtube_workspace", description="Open the Strands Pack YouTube suite workspace.")
def youtube_workspace() -> PrefabApp:
    return workspace()
