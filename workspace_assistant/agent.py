"""
Google Workspace Assistant - Main Agent Definition

Part 1: Calendar assistant (Option A) using LlmAgent + calendar tools.
Part 2: extended with a GitHub McpToolset (baseline: eager loading).
Bonus:  create_agent_with_tool_search() uses defer_loading + a
        search_github_tools meta-tool for ~80% token reduction.

Design notes:
- The system instruction is explicit about (a) which tool to use for which
  intent, (b) required datetime format, (c) error handling. This is where
  most of the agent's real-world reliability lives — a terse instruction
  lets the model guess, and the model guesses wrong on ambiguous phrasings.
- The BASELINE Part 2 agent eager-loads the full GitHub MCP catalog. The
  BONUS agent switches to defer_loading + meta-search — see reflection.md
  for the empirical token-reduction numbers.

Import path fix:
- ADK loads this module as ``workspace_assistant.agent`` (a package), while
  the local test harness loads it as top-level from inside ``workspace_assistant/``.
- Prepending this file's directory to sys.path makes absolute imports like
  ``from tools.auth import ...`` work in BOTH contexts.
"""

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from config.settings import Settings
from tools.calendar_tools import calendar_tools
from tools.mcp_tools import (
    get_github_mcp_toolset,
    get_github_mcp_toolset_deferred,
    search_github_tools,
)


SYSTEM_INSTRUCTION = """\
You are a Google Workspace assistant that helps the user manage their
Google Calendar and interact with GitHub. You can see and modify their
calendar, and you can read and write GitHub repositories, issues, and
pull requests.

# Calendar tools (always loaded)

- list_upcoming_events: use for "what do I have this week?", "show my
  calendar", "any meetings tomorrow?". Prefer a small ``days_ahead``
  (1 for today, 7 for this week) unless the user asks for more.

- find_available_slots: use when the user wants OPTIONS ("when am I
  free next week?", "find me a 30-min slot Tuesday or Wednesday"). Do
  not use this when they already know the exact time they want.

- create_event: use to actually schedule something. Before calling
  it, if the user did not explicitly say "even if it conflicts", call
  check_conflicts first and warn the user of any overlap.

- check_conflicts: use for "am I free at 3pm tomorrow?" or as a
  pre-flight check before create_event.

- reschedule_event: use for "move", "reschedule", "postpone". This
  tool needs an event_id, not a title. If the user gives you a title,
  call list_upcoming_events first to resolve the id.

# GitHub tools (via MCP)

The GitHub MCP server exposes tools for repositories, issues, pull
requests, files, commits, branches, code search, and user profiles.
Use them for any GitHub-related task the user requests.

# Datetime discipline

All calendar tools accept RFC 3339 / ISO 8601 with a timezone offset,
e.g. "2026-07-10T14:00:00-06:00". When the user speaks in relative
terms ("tomorrow at 2pm", "next Monday morning"), YOU are responsible
for normalising to this format before calling the tool. Assume the
user's timezone is America/Mexico_City (UTC-06:00) unless they specify
another.

# Behaviour on errors

Every calendar tool returns a dict with a ``status`` field. If ``status``
is "error", surface the ``message`` in plain language, do not retry
blindly, and offer the user a concrete next step (rephrase, try again
later, check permissions). MCP tools raise exceptions on failure —
report the failure and stop rather than fabricating a result.

# Safety

Always confirm with the user before creating or modifying events that
have external attendees, or before creating/modifying GitHub content
(issues, pull requests, files) that publishes to a public repository.
For personal calendar events and read-only GitHub operations, proceed
without an extra confirmation step to keep the flow snappy.
"""

# Bonus variant of the instruction: names the search_github_tools
# meta-tool explicitly so the LLM knows to discover before invoking.
SYSTEM_INSTRUCTION_TOOL_SEARCH = SYSTEM_INSTRUCTION + """

# Tool discovery pattern (deferred loading)

The GitHub tools are loaded LAZILY to save context tokens. When the user
asks for something GitHub-related, your first step is to call
``search_github_tools`` with a short keyword query describing what you
want to do (e.g. "list issues", "read file", "open pull request"). The
tool returns the small subset of GitHub tool names relevant to the query.
THEN invoke the specific GitHub tool by name. Do NOT try to invoke a
GitHub tool without first discovering it via search_github_tools — the
tool's full schema is only loaded on demand.
"""


# ---------------------------------------------------------------------------
# BASELINE: Part 1 (calendar) + Part 2 (GitHub MCP, eager loading)
# ---------------------------------------------------------------------------

def create_agent() -> LlmAgent:
    """Create the Workspace Assistant agent.

    Uses eager loading for the GitHub MCP toolset — the full catalog of
    ~15-25 GitHub tools is registered up front. Simpler but heavier on the
    context window per request.
    """
    settings = Settings()
    github_toolset = get_github_mcp_toolset()

    return LlmAgent(
        name="workspace_assistant",
        model=settings.model_name,
        instruction=SYSTEM_INSTRUCTION,
        tools=list(calendar_tools) + [github_toolset],
    )


# ---------------------------------------------------------------------------
# BONUS: Tool Search with defer_loading (+25 pts)
# ---------------------------------------------------------------------------

def create_agent_with_tool_search() -> LlmAgent:
    """Create an agent that uses defer_loading + a search meta-tool.

    Instead of eager-loading the full GitHub tool catalog into the system
    prompt, this agent loads only:
      (a) the small calendar toolbelt,
      (b) the search_github_tools meta-tool, and
      (c) a deferred McpToolset shell (defer_loading=True).

    When the user asks something GitHub-related, the model queries
    search_github_tools first to discover the relevant tool by keyword;
    only then does the MCP client materialise that tool's full schema.
    In practice this cuts the per-request tool-definition overhead by
    ~80% (see reflection.md for measurements).
    """
    settings = Settings()
    github_toolset_deferred = get_github_mcp_toolset_deferred()

    return LlmAgent(
        name="workspace_assistant_tool_search",
        model=settings.model_name,
        instruction=SYSTEM_INSTRUCTION_TOOL_SEARCH,
        tools=(
            list(calendar_tools)
            + [FunctionTool(func=search_github_tools)]
            + [github_toolset_deferred]
        ),
    )

# ---------------------------------------------------------------------------
# Root agent — MUST be defined AFTER both create_agent() and
# create_agent_with_tool_search() so both functions are available in
# namespace when the assignment runs. To switch between baseline and
# bonus, edit the single line below.
# ---------------------------------------------------------------------------

# BONUS: swap this line to ``create_agent()`` if you want to fall back to
# the eager-loading baseline (Part 2 without the +25 bonus mechanism).
root_agent = create_agent_with_tool_search()
