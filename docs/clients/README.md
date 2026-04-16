# MCP Client Configuration

Ready-to-paste config snippets for connecting MCP clients to the Palace MCP server
running locally on `http://localhost:8080/mcp` (streamable-HTTP transport).

> **Prerequisite:** The Palace stack must be running before connecting a client.
> Start it with:
> ```bash
> docker compose --profile review up -d
> ```

---

## Claude Desktop

1. Open (or create) `~/Library/Application Support/Claude/claude_desktop_config.json`
   on macOS, or `%APPDATA%\Claude\claude_desktop_config.json` on Windows.
2. Merge the contents of [`claude-desktop.json`](./claude-desktop.json) into that file.
   If `mcpServers` already exists, add the `"palace"` key inside it.
3. Restart Claude Desktop.

**Verify:** Open a new chat and ask "What MCP tools are available?" — you should see
Palace tools listed.

---

## Cursor

1. Copy [`cursor.json`](./cursor.json) to `.cursor/mcp.json` at the root of your
   workspace (or merge the `mcpServers.palace` entry if the file already exists).
2. Reload the Cursor window (`Cmd/Ctrl + Shift + P` → *Reload Window*).

**Verify:** Open the Cursor MCP panel (`Cmd/Ctrl + Shift + P` → *MCP: List Tools*)
and confirm `palace` appears.

---

## Configuration reference

| Field | Value | Notes |
|-------|-------|-------|
| `mcpServers.palace.url` | `http://localhost:8080/mcp` | Streamable-HTTP endpoint served by `palace-mcp` |

The `url` field follows the
[MCP streamable-HTTP transport spec](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports#streamable-http).
No API key is required for local use.
