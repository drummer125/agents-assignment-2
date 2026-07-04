# Assignment 2: Google Workspace Assistant + MCP Server

**UCLA Extension - Agentic AI Course**

---

## Overview

| Part | Focus | Points |
|------|-------|--------|
| **Part 1** | Build a Google Workspace agent with ADK | 70 |
| **Part 2** | Connect to GitHub via MCP Server | 30 |

## Project Structure

```
workspace_assistant/
├── agent.py                  # STUDENT: Main agent definition
├── main.py                   # Given: CLI entry point
├── tools/
│   ├── auth.py               # Given: Google OAuth helper
│   ├── calendar_tools.py     # STUDENT (Option A): Calendar tools
│   ├── tasks_tools.py        # STUDENT (Option B): Tasks tools
│   └── mcp_tools.py          # STUDENT: GitHub MCP integration
├── config/
│   ├── settings.py           # Given: Configuration from .env
│   ├── mcp_servers.json      # Given: MCP server config (optional)
│   └── credentials/          # Your OAuth files (gitignored)
├── tests/
│   ├── test_tools.py         # Part 1 verification
│   └── test_mcp.py           # Part 2 verification
└── docs/
    ├── google_auth_setup.md  # Google OAuth setup guide
    ├── github_mcp_setup.md   # GitHub token setup guide
    └── reflection_template.md
```

### Files You Edit

| File | What to implement |
|------|-------------------|
| `tools/calendar_tools.py` | Option A: 3+ calendar tools |
| `tools/tasks_tools.py` | Option B: 3+ tasks tools |
| `agent.py` | System instruction + `LlmAgent` with your tools |
| `tools/mcp_tools.py` | Part 2: GitHub `McpToolset` configuration |

### Files Provided (Do Not Edit)

| File | What it provides |
|------|-----------------|
| `tools/auth.py` | `get_calendar_service()` and `get_tasks_service()` — authenticated Google API clients |
| `config/settings.py` | `Settings` class — loads model name, credentials path, and options from `.env` |
| `main.py` | CLI with `--interactive` mode using `rich` |
| `tests/test_tools.py` | Checks tool count, docstrings, type hints, naming, error handling |
| `tests/test_mcp.py` | Checks GitHub token and `McpToolset` presence in agent |

---

# Part 1: Google Workspace Assistant (70 points)

Build an AI agent using **Agent Development Kit (ADK)**.

**Choose ONE option:**

| Option | Focus |
|--------|-------|
| **A** | Calendar Assistant - Schedule meetings, find free time, manage conflicts |
| **B** | Tasks Manager - Create tasks, track to-dos, manage deadlines |

## Requirements

1. **Minimum 3 tools** with clear names and descriptions
2. **Error handling** with user-friendly messages
3. **System instruction** that guides the agent's behavior

## Provided: Authentication Helpers

The `tools/auth.py` file is **already implemented** and gives you authenticated Google API clients:

```python
from tools.auth import get_calendar_service  # Option A
from tools.auth import get_tasks_service     # Option B

# Use inside your tools:
service = get_calendar_service()  # Returns authorized Calendar API client
service = get_tasks_service()     # Returns authorized Tasks API client
```

First-time use triggers an OAuth browser flow. See [docs/google_auth_setup.md](workspace_assistant/docs/google_auth_setup.md) for setup.

## How to Implement Tools

Define each tool as a plain Python function with a clear docstring and type hints — ADK reads these to build the tool schema and auto-wraps the function when you pass it to the agent. Each tool should call the Google API and return a dict:

```python
from tools.auth import get_calendar_service

def list_upcoming_events(max_results: int = 10) -> dict:
    """List upcoming calendar events.

    Args:
        max_results: Maximum number of events to return.

    Returns:
        dict with 'status' and 'events' keys.
    """
    try:
        service = get_calendar_service()
        events_result = service.events().list(
            calendarId='primary', maxResults=max_results, ...
        ).execute()
        return {"status": "success", "events": events_result.get("items", [])}
    except Exception as e:
        return {"status": "error", "message": str(e)}
```

Add your completed tools to the list at the bottom of the file:

```python
calendar_tools = [list_upcoming_events, find_available_slots, create_event]
```

## Option A: Calendar Tools

Implement in **`tools/calendar_tools.py`** using `get_calendar_service()`:

| Tool | Purpose |
|------|---------|
| `list_upcoming_events` | Get events for a date range |
| `find_available_slots` | Find free time between participants |
| `create_event` | Schedule a new meeting |
| `check_conflicts` | Detect scheduling conflicts |
| `reschedule_event` | Move an existing event |

## Option B: Tasks Tools

Implement in **`tools/tasks_tools.py`** using `get_tasks_service()`:

| Tool | Purpose |
|------|---------|
| `list_tasks` | Get tasks from a list |
| `create_task` | Add a new task |
| `complete_task` | Mark a task as done |
| `update_task` | Modify task details |
| `delete_task` | Remove a task |

## Creating Your Agent

In **`agent.py`**, wire your tools into an `LlmAgent`:

```python
from google.adk.agents import LlmAgent
from config.settings import Settings
from tools.calendar_tools import calendar_tools  # or tasks_tools

def create_agent() -> LlmAgent:
    settings = Settings()

    instruction = """You are a Google Workspace assistant that helps users
    manage their calendar. You can list events, find free time, create
    meetings, check for conflicts, and reschedule events. Always confirm
    before making changes..."""

    return LlmAgent(
        name="workspace_assistant",
        model=settings.model_name,
        instruction=instruction,
        tools=calendar_tools,
    )
```

---

# Part 2: GitHub MCP Server (30 points)

Extend your agent to interact with GitHub using **McpToolset**.

## What You Need to Do

1. Create a GitHub Personal Access Token with `repo` scope
2. Configure `McpToolset` to connect to the GitHub MCP server
3. Update your system instruction to include GitHub capabilities

## Key Classes

```python
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
```

## GitHub MCP Server

### Required: Direct Configuration
```python
server_params = StdioServerParameters(
    command="npx",
    args=["-y", "@modelcontextprotocol/server-github"],
    env={"GITHUB_PERSONAL_ACCESS_TOKEN": token}
)

toolset = McpToolset(
    connection_params=StdioConnectionParams(server_params=server_params)
)
```

### Optional: File-based Configuration
Alternatively, load from `config/mcp_servers.json`:
```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PERSONAL_ACCESS_TOKEN}"
      }
    }
  }
}
```

Use the provided `load_mcp_config()` helper to load and parse this config.

## Required GitHub Functionality

Your agent should handle:
1. "List my GitHub repositories"
2. "Show open issues in [repo]"
3. "Create an issue in [repo] about [topic]"

---

## Evaluation Rubric

### Part 1: Google Workspace (70 pts)

| Component | Points |
|-----------|--------|
| Tool Design | 18 |
| Agent Instructions | 14 |
| Error Handling | 14 |
| Functionality | 14 |
| Code Quality | 10 |

### Part 2: GitHub MCP (30 pts)

| Component | Points |
|-----------|--------|
| McpToolset Configured | 10 |
| GitHub Queries Work | 15 |
| Error Handling | 5 |

**Bonus (+25):** Implement tool search with `defer_loading`

### Bonus: Tool Search Pattern (+25 pts)

**What:** Implement the `defer_loading` pattern so your agent doesn't load all 15+ GitHub MCP tools upfront—only searches and loads what it needs.

**Why:** Reduces token usage by ~80% (from ~8K to ~1.5K tokens for GitHub tools).

**How:**
1. Add a `search_github_tools` tool to your agent (10 pts)
2. Configure McpToolset with `defer_loading=True` (10 pts)
3. Implement `create_agent_with_tool_search()` in agent.py (5 pts)

**Required Comparison:**
In your reflection, include a comparison showing token/context bloat:
- Run your agent **without** `defer_loading` and note the context size
- Run your agent **with** `defer_loading` and note the context size
- Calculate the % reduction in tokens

Example comparison:
| Mode | Tools Loaded | Approx Tokens |
|------|--------------|---------------|
| Without defer_loading | 15+ GitHub tools | ~8,000 |
| With defer_loading | 1-2 tools + search | ~1,500 |
| **Savings** | | **~80%** |

See `tools/mcp_tools.py` for scaffolding

---

## Getting Started

### Step 1: Environment Setup

```bash
conda create -n workspace-agent python=3.11 -y
conda activate workspace-agent
pip install -r requirements.txt
cp .env.example .env
```

### Step 2: Google OAuth Setup

Follow [docs/google_auth_setup.md](workspace_assistant/docs/google_auth_setup.md) to:
1. Create a Google Cloud project with Calendar/Tasks API enabled
2. Download OAuth credentials to `config/credentials/credentials.json`
3. The first tool call will open a browser for authorization

### Step 3: Implement Part 1

1. Implement 3+ tools in `tools/calendar_tools.py` or `tools/tasks_tools.py`
2. Create your agent in `agent.py` with system instruction + tools
3. Verify:

```bash
cd workspace_assistant
python -m tests.test_tools
```

4. Test interactively:

```bash
adk web                        # ADK Web UI
# or
python main.py --interactive   # CLI mode
```

### Step 4: Implement Part 2

1. Get a GitHub Personal Access Token (see [docs/github_mcp_setup.md](workspace_assistant/docs/github_mcp_setup.md))
2. Add `GITHUB_PERSONAL_ACCESS_TOKEN=ghp_...` to `.env`
3. Implement `get_github_mcp_toolset()` in `tools/mcp_tools.py`
4. Add the toolset to your agent in `agent.py` and update the system instruction
5. Verify:

```bash
python -m tests.test_mcp
```

---

## Testing with ADK Web UI

ADK provides a built-in web interface for testing your agent interactively.

### Start the Web UI

```bash
cd workspace_assistant
adk web
```

This launches a local web server (typically at `http://localhost:8000`).

### Using the Web UI

1. **Select your agent** from the dropdown (should show your `workspace_assistant`)
2. **Type queries** in the chat interface to test your tools
3. **View tool calls** - the UI shows which tools are invoked and their responses
4. **Debug errors** - see full error messages and stack traces

### Test Queries to Try

**Part 1 - Calendar (Option A):**
- "What meetings do I have tomorrow?"
- "Find a free slot for a 1-hour meeting next week"
- "Schedule a team sync for Monday at 2pm"

**Part 1 - Tasks (Option B):**
- "Show my tasks"
- "Add a task: Review PR by Friday"
- "Mark the first task as complete"

**Part 2 - GitHub MCP:**
- "List my GitHub repositories"
- "Show open issues in octocat/Hello-World"
- "Create an issue in my-repo about fixing the login bug"

### Troubleshooting

| Issue | Solution |
|-------|----------|
| Agent not appearing | Ensure `agent.py` has a valid `create_agent()` function |
| Tools not showing | Check that tools are added to the agent's `tools` list |
| MCP connection failed | Verify `GITHUB_PERSONAL_ACCESS_TOKEN` in `.env` |
| Import errors | Run `pip install -r requirements.txt` |

---

## Submission

This assignment uses **GitHub Classroom**. Your work is submitted by pushing to your repository's `main` branch.

### Steps

1. Test your agent with `adk web` and verify all functionality works
2. Run the verification tests:
   ```bash
   cd workspace_assistant
   python -m tests.test_tools
   python -m tests.test_mcp
   ```
3. Complete `docs/reflection_template.md`
4. Commit and push your changes:
   ```bash
   git add -A
   git commit -m "Submit assignment 2"
   git push origin main
   ```
5. Verify your submission on GitHub — go to your repository page and confirm all files are present

### How Grading Works

- When you push to `main`, the autograder automatically creates a **Pull Request** with your grading results
- Check the **Pull Requests** tab on your GitHub repository to see your score and feedback
- You can push multiple times before the deadline; each push triggers a new grading run

### Important

- **Do NOT commit sensitive files** — `credentials/`, `token.json`, and `.env` are already in `.gitignore`
- Make sure your code passes the local tests before pushing

---

## Resources

- [ADK Documentation](https://google.github.io/adk-docs/)
- [ADK MCP Tools](https://google.github.io/adk-docs/tools-custom/mcp-tools/)
- [Google Calendar API](https://developers.google.com/calendar/api)
- [Google Tasks API](https://developers.google.com/tasks)
- [GitHub MCP Server](https://github.com/modelcontextprotocol/servers)
