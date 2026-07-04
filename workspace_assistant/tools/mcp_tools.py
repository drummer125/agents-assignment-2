"""
Part 2: GitHub MCP Integration

Configure McpToolset to connect to the GitHub MCP server.

Required: Direct configuration in Python code
Optional: File-based configuration from config/mcp_servers.json
"""

import json
import os
from pathlib import Path
from dotenv import load_dotenv
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

load_dotenv()

# Path to MCP server configuration (for Option B)
MCP_CONFIG_PATH = Path(__file__).parent.parent / "config" / "mcp_servers.json"


# =============================================================================
# REQUIRED: Direct Configuration
# =============================================================================
# TODO: Implement get_github_mcp_toolset()
# Configure the GitHub MCP server directly in Python code.
#
# Example structure:
#
# def get_github_mcp_toolset() -> McpToolset:
#     token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
#     if not token:
#         raise ValueError("GITHUB_PERSONAL_ACCESS_TOKEN not set in .env")
#
#     server_params = StdioServerParameters(
#         command="npx",
#         args=["-y", "@modelcontextprotocol/server-github"],
#         env={"GITHUB_PERSONAL_ACCESS_TOKEN": token}
#     )
#
#     return McpToolset(
#         connection_params=StdioConnectionParams(server_params=server_params)
#     )


# =============================================================================
# OPTIONAL: File-based Configuration
# =============================================================================
def load_mcp_config() -> dict:
    """Load MCP server configuration from JSON file."""
    if not MCP_CONFIG_PATH.exists():
        raise FileNotFoundError(f"MCP config not found: {MCP_CONFIG_PATH}")

    with open(MCP_CONFIG_PATH) as f:
        config = json.load(f)

    # Replace environment variable placeholders
    github_config = config.get("mcpServers", {}).get("github", {})
    env = github_config.get("env", {})
    for key, value in env.items():
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            env_var = value[2:-1]
            env[key] = os.getenv(env_var, "")

    return config


# TODO: Implement get_github_mcp_toolset_from_config()
# Load configuration from config/mcp_servers.json
#
# Example structure:
#
# def get_github_mcp_toolset_from_config() -> McpToolset:
#     config = load_mcp_config()
#     github = config["mcpServers"]["github"]
#
#     token = github["env"].get("GITHUB_PERSONAL_ACCESS_TOKEN")
#     if not token:
#         raise ValueError("GITHUB_PERSONAL_ACCESS_TOKEN not set in .env")
#
#     server_params = StdioServerParameters(
#         command=github["command"],
#         args=github["args"],
#         env=github["env"]
#     )
#
#     return McpToolset(
#         connection_params=StdioConnectionParams(server_params=server_params)
#     )


# =============================================================================
# BONUS (+25 points) - Tool Search Pattern
# =============================================================================
# Implement defer_loading to reduce token usage by ~80%
#
# Why: GitHub MCP has 15+ tools (~8K tokens). Loading all upfront is wasteful.
# With defer_loading, tools are discovered on-demand (~1.5K tokens).
#
# Points breakdown:
# - search_github_tools function (10 pts)
# - defer_loading=True configured (10 pts)
# - create_agent_with_tool_search works (5 pts)
#
# Steps:
# 1. Create a search_github_tools tool that searches available MCP tools
# 2. Configure McpToolset with defer_loading=True
# 3. Keep only 1-2 frequently-used tools always loaded
#
# REQUIRED: In your reflection, compare context/token usage:
# - Run WITHOUT defer_loading, note context size (~8K tokens for 15+ tools)
# - Run WITH defer_loading, note context size (~1.5K tokens)
# - Calculate and report the % reduction
#
# Example structure:
#
# from google.adk.tools import FunctionTool
#
# def search_github_tools(query: str) -> dict:
#     """Search for available GitHub tools by keyword.
#
#     Args:
#         query: Search term (e.g., "issues", "repository", "pull request")
#
#     Returns:
#         dict with matching tool names and descriptions
#     """
#     # TODO: Implement tool search logic
#     pass
#
#
# def get_github_mcp_toolset_deferred() -> McpToolset:
#     """Create McpToolset with defer_loading for on-demand tool discovery."""
#     token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
#     if not token:
#         raise ValueError("GITHUB_PERSONAL_ACCESS_TOKEN not set")
#
#     server_params = StdioServerParameters(
#         command="npx",
#         args=["-y", "@modelcontextprotocol/server-github"],
#         env={"GITHUB_PERSONAL_ACCESS_TOKEN": token}
#     )
#
#     return McpToolset(
#         connection_params=StdioConnectionParams(server_params=server_params),
#         defer_loading=True  # Key: tools loaded on-demand
#     )


mcp_tools = [
    # Add your McpToolset here after implementing one of the options above
    # Example: get_github_mcp_toolset()
    # Example: get_github_mcp_toolset_from_config()
]
