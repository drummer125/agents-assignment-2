# Assignment 2 Reflection

**Name:** Emilio Oropeza
**Option:** A — Google Calendar Assistant with GitHub MCP Integration
**Date:** July 2026

---

## Tool Design Decisions

### Tools Implemented

**Calendar tools (Part 1):**

1. **list_upcoming_events(max_results, days_ahead)** — Returns the user's next N events over a configurable window. Used for "what do I have this week?", "show my calendar", overview queries.

2. **find_available_slots(duration_minutes, start_date, end_date, working_hours_start, working_hours_end)** — Scans the primary calendar and returns free slots of the requested duration that fall inside working hours. This is the tool with the most non-trivial logic in the crew: it walks the range in 30-minute steps and emits non-overlapping slots.

3. **create_event(summary, start_datetime, end_datetime, description, location, attendees)** — Creates a new event. Sends invites automatically when attendees are provided.

4. **check_conflicts(start_datetime, end_datetime)** — Returns whether an existing event overlaps a proposed time range. Designed to be called as a pre-flight before `create_event`.

5. **reschedule_event(event_id, new_start_datetime, new_end_datetime)** — Moves an existing event. Fetches the original first to preserve attendees, description, and location — only the time changes.

**GitHub MCP tools (Part 2):** the agent connects to the `@modelcontextprotocol/server-github` server via `StdioServerParameters` and exposes GitHub's tool catalog. In the baseline agent, the full catalog (~20 tools) is loaded; in the bonus agent, a `tool_filter` limits the exposed set to four high-value tools (`search_repositories`, `list_issues`, `get_file_contents`, `list_pull_requests`).

**Bonus meta-tool:** `search_github_tools(query)` — a static catalog search that lets the model discover tool names by keyword before invoking them (see `mcp_tools.py`, `GITHUB_TOOLS_CATALOG`).

### Why These Tools?

I chose Option A (Calendar) over Tasks because calendars are inherently richer as a design surface: they have overlapping intervals, working-hour constraints, attendees, timezones, and the notion of "conflict" — all of which force meaningful decisions in tool design. Tasks would have been a simpler CRUD wrapper. The Calendar option maximises the surface area for demonstrating tool disambiguation and prompt design, which is exactly what the rubric weights.

The five tools mirror the workflow a real calendar assistant needs to support: **view** (`list_upcoming_events`), **plan** (`find_available_slots`), **schedule** (`create_event`), **validate** (`check_conflicts`), and **adjust** (`reschedule_event`). Together they cover the full lifecycle a user talks about naturally ("what do I have", "when am I free", "book a meeting", "am I free at 3pm", "move that call").

`check_conflicts` deserves special mention because it is the tool that unlocks a graceful behaviour: the agent can warn about overlaps before creating an event, rather than silently double-booking. In practice, well-scoped defensive tools like this reduce user friction more than adding another "capability" tool would.

### Description Strategy

The design lesson I carried over from Assignment 1 and from the ADK quiz (Q4 and Q17-Q19) is that tool description quality has an outsized effect on selection accuracy. Terse descriptions cause the model to confuse similar tools; overly verbose ones bloat the context. My approach followed three explicit rules:

**Rule 1 — Use-when AND do-NOT-use-when.** Each tool's docstring names both the intended cases and the near-neighbours it should not be confused with. Example from `list_upcoming_events`:

> Use this tool when the user asks what is on their calendar... Do NOT use this tool when the user wants to find a specific free time slot (use `find_available_slots`) or check a single time range for conflicts (use `check_conflicts`).

Without the "do NOT use" clause, `list_upcoming_events` and `check_conflicts` collide semantically because both query a time range.

**Rule 2 — Concrete argument guidance.** Rather than "days_ahead: number of days" I wrote "days_ahead: use 1 for today, 7 for this week, 30 for this month." Anchoring parameter meaning in canonical values reduces the model's guesswork when it needs to normalise a user phrasing.

**Rule 3 — Return format documented explicitly.** Every docstring specifies both the success and error shapes as literal `dict` schemas. This becomes contract text the system instruction can reference ("if `status` is 'error', surface the message and stop").

For the GitHub MCP tools I did not control the descriptions — they come from the MCP server. But I did control the `search_github_tools` meta-tool description, and there I applied the same discipline: named cases where to use it, named cases where to skip it (calendar tasks), and documented the return shape.

---

## Challenges Encountered

### Challenge 1: Import paths broke between `adk web` and the local test harness

- **Problem:** After implementing the tools, `python -m tests.test_tools` (run from inside `workspace_assistant/`) passed cleanly, but `adk web` failed with `ModuleNotFoundError: No module named 'tools'` and later `No module named 'config'`. The two runners load the agent module in different contexts — the test harness treats `workspace_assistant/` as top-level, so absolute imports like `from tools.auth import ...` resolve, while ADK loads the agent as `workspace_assistant.agent` (a package), which makes the same absolute imports fail because `tools` is not a top-level module in that namespace.

- **Solution:** I first tried a `try/except` fallback (relative import first, absolute second) in each file that touched a sibling module. That fixed `agent.py` but the failure cascaded into `tools/calendar_tools.py`, which also had an absolute import to `tools.auth`. Chasing the try/except pattern into every file was fragile. The cleaner fix — and the one I kept — was to prepend the containing directory to `sys.path` at the top of `agent.py` (`_HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(_HERE))`). After that, all absolute imports resolve regardless of which runner loaded the module. The starter kit's `main.py` already used this pattern, which I did not notice until several failed attempts later — a lesson in reading the scaffolding before designing around it.

### Challenge 2: `defer_loading=True` does not exist in the pinned version of `google-adk`

- **Problem:** The bonus specification asks for `defer_loading=True` on the `McpToolset` constructor. When I wired it up, ADK raised `TypeError: McpToolset.__init__() got an unexpected keyword argument 'defer_loading'`. Inspecting the constructor signature via `inspect.signature` confirmed the kwarg is not present in the installed version — the closest supported parameter is `tool_filter`, which registers only a named subset of tools with the LLM rather than fetching schemas on demand.

- **Solution:** I pivoted from `defer_loading` to `tool_filter=[list_of_high_value_tools]`. Conceptually the goal is the same — reduce the tool-definition tokens the model sees at each turn — but the mechanism is different: `defer_loading` would fetch schemas lazily; `tool_filter` simply hides the rest from the catalog upfront. To preserve the discovery-then-invoke pattern from Q18/Q19, I kept the `search_github_tools` meta-tool with a static catalog of ~20 GitHub tool names and descriptions. The agent can discover any tool by keyword; it can only invoke the four in the filter directly. The reflection quantifies the savings and documents the trade-off honestly rather than hiding it.

---

## Error Handling Approach

Every custom tool follows the same contract: return a dict with a `status` field of `"success"` or `"error"`, plus either the data payload or a human-readable `message`. This uniform shape means the system instruction can reference it once ("if status is error, surface the message and stop") and the agent handles failures consistently regardless of which tool raised them.

The Calendar tools catch three tiers of exceptions:

- **`HttpError` from `googleapiclient`** — surfaced with `e.reason` when available. For `reschedule_event`, I check `e.resp.status == 404` specifically and return a targeted message that suggests calling `list_upcoming_events` first to resolve the correct id. Specific error remediation is more useful than a generic "API error".
- **`ValueError`** — used specifically for `find_available_slots` when the date format cannot be parsed. Returns an example of the correct ISO 8601 format with timezone.
- **Catch-all `Exception`** — returns "Unexpected error: {str(e)}" so nothing crashes the agent's turn silently.

Errors are never fabricated as if they were successes. The system instruction explicitly forbids the agent from retrying blindly or making up a result when a tool returns error status. This is critical because a hallucinated "OK, meeting scheduled" would be actively harmful in a Calendar context.

For MCP tools I do not own the error handling — the MCP client raises exceptions on server failures. But I documented in the system instruction that the agent should report MCP failures plainly rather than fabricate a result. During testing, this discipline caught the `Tool 'fork_repository' not found` case cleanly (see below), rather than producing a plausible-sounding hallucination.

---

## Bonus: Empirical Analysis of `tool_filter` as a `defer_loading` Substitute

The bonus targets an ~80% reduction in tool-definition tokens by loading a small subset upfront and using `search_github_tools` for discovery. My analysis, based on the mechanism I actually shipped (`tool_filter` rather than `defer_loading`):

| Component | Baseline (eager) | With `tool_filter` + meta-tool |
|---|---|---|
| Full GitHub tool schemas (~20 tools × ~350 tokens) | ~7,000 | 0 (only 4 loaded) |
| Four filtered tools (4 × ~350 tokens) | 0 | ~1,400 |
| `search_github_tools` meta-tool | 0 | ~150 |
| **Total tokens for GitHub capability** | **~7,000** | **~1,550** |
| **Reduction** | | **~78%** |

The 78% figure is close to the 80% target and matches the design intent. The savings are real per-request context tokens on every conversation turn.

**Empirical evidence from `adk web`:**

1. **Discovery layer works.** For the query *"Use search_github_tools to find out what GitHub tools are available for working with issues and pull requests"*, the agent invoked the meta-tool twice and reported six tools that are NOT in the filter (`create_pull_request`, `get_pull_request`, `get_pull_request_files`, `list_pull_requests`, `merge_pull_request`, `add_issue_comment`) — proof that the model knows those capabilities exist conceptually even though their schemas are not in context.

2. **Trade-off is real and observable.** For *"Fork the octocat/Hello-World repository"*, the agent went directly to `fork_repository` (which is not in the filter) and ADK raised `ValueError: Tool 'fork_repository' not found. Available tools: [10 tools listed]`. This is exactly the failure mode Q18 predicts: token savings come at the cost of the agent needing an extra reasoning step to know when to discover before invoking.

3. **Discovery-first prompting fixes the trade-off.** When I re-issued the same intent as *"First use search_github_tools to find a tool for forking, then tell me if it's available"*, the agent behaved correctly: it called `search_github_tools("fork")`, received `fork_repository` from the catalog, and responded honestly that the tool exists but is not currently available for direct invocation.

The lesson is that `tool_filter` is a viable adaptation of the pattern in this ADK version, but its success in production depends on system-instruction discipline — the model has to reliably discover before invoking when the requested capability is outside the filter. My current instruction encourages this but does not enforce it in all cases, which is why the `fork_repository` failure surfaced.

---

## Ideas for Improvement

1. **Dynamic tool filter expansion.** The current filter is static. A more sophisticated implementation would let `search_github_tools` return not just a description but a signal that the runtime should register the discovered tool into the agent's active toolset for the next turn. This would give the model the "discover once, invoke thereafter" ergonomics of true `defer_loading` on top of a filtered baseline.

2. **A citation/fact-checker agent for GitHub answers.** Similar to the fifth agent I recommended in Assignment 1's reflection, a lightweight verifier could re-read the raw MCP responses and confirm the summarised answer matches. This would catch cases where the model paraphrases a `list_issues` response and slightly misstates a number or attribution.

3. **A pre-flight `check_conflicts` guard baked into `create_event`.** Right now the system instruction asks the agent to call `check_conflicts` before `create_event`. Enforcing this at the tool level — `create_event` internally runs the conflict check unless a `force=True` flag is passed — would remove the possibility of the model skipping the safety step under prompt drift. This is the standard defensive-tool-design pattern from operational tooling: make the safe path the default, require explicit opt-out to bypass.

4. **Confirmation flow for write operations.** External-attendee invites are automatically sent by `create_event`. In a production deployment I would gate this behind an explicit user confirmation ("You are about to invite alice@example.com, bob@example.com. Confirm?") rather than trusting the agent's judgement, especially since ADK's `require_confirmation` parameter on `McpToolset` supports exactly this pattern.

---

## Key Learnings

The most important thing this assignment reinforced is that **the failure modes in agentic systems are almost never in the agent code itself — they are in the interfaces around it**. Two of the biggest blockers were completely orthogonal to the actual tool logic: an import-path mismatch between the runner (`adk web`) and the local test harness that made the same file work in one context and fail in the other, and a version mismatch between the assignment specification (`defer_loading=True`) and the installed ADK. In both cases the tool code was correct; the environment lied to me. This maps closely to what I see in cybersecurity consulting — most incidents I investigate turn out to be misconfigurations at the boundary between systems rather than bugs in the systems themselves. Agentic frameworks appear to be the same category of software: composed of many moving parts (MCP, LLM, runner, credentials, subprocess environment), and the seams between them are where friction lives.

The second learning is about **prompt engineering as failure-mode naming**. The bonus mechanism (whether `defer_loading` or `tool_filter`) exposes an entirely new class of runtime failure: the agent asks for a tool that "should" exist but is not currently registered. The naive response is to alucinate a call to that tool and get a ValueError from ADK. The disciplined response is to discover first. My system instruction encourages the disciplined path but does not enforce it, which is why the `fork_repository` failure surfaced in testing. The general pattern I want to internalise from this course is that prompts should name the specific failure modes that would otherwise occur — not tell the model to "be careful" but tell it what "being careful" means in the concrete case at hand. This is the same pattern that fixed the SourceHunter in Assignment 1 (where naming the "survey bias" failure was what unlocked correct behaviour), and now again here.

Finally, the pragmatic reality of frontier frameworks like ADK is that specifications and installed versions drift constantly. The `defer_loading` mismatch is not a rare edge case — it is the common case in fast-moving agent tooling. What matters is that when specs and reality disagree, you diagnose honestly (via `inspect.signature`, or reading the actual code, not guessing), adapt the mechanism to what the current API offers, and document the substitution and its trade-offs cleanly. That is the same discipline required in any technology adoption at scale, and it maps directly to the cloud-security engagements I lead — where matching architectural intent to whatever the current tool version actually supports is half the work.
