# Syncra MCP Connect Setup Guide

## Key Steps

1. **Generate API Token**: Access your Syncra dashboard at **Configuración → Tokens API** and create a new token. Select "Nunca" for permanent access or set an expiration date.

2. **Configure Your Client**: Register the MCP server by adding it to your client's configuration file with your token and organization slug as headers.

3. **Verify Access**: The documentation notes that "GET https://cfamprdygpngrjtaxzes.supabase.co/functions/v1/mcp-server/health responds `{"status":"ok","service":"syncra-mcp-server"}` without authentication."

4. **Test Tools**: After configuration, use the provided curl command with your token to list available tools for your role.

## Important Security Notes

- Store tokens securely and add config files to `.gitignore` if they're in your project
- Tokens can be revoked anytime from the dashboard
- For unattended operations, include the `x-autonomous: true` header to log automated activity

The setup supports Claude Desktop, Claude Code (CLI), Cursor, Windsurf, and Antigravity IDEs with platform-specific configuration paths provided.

## Syncra Server Info

- **URL**: https://cfamprdygpngrjtaxzes.supabase.co/functions/v1/mcp-server
- **Organization**: disruptivapp
- **Status**: Connected via Claude Code CLI
- **Rate Limit**: 60 requests/minute (respects Retry-After on 429 responses)

## Worker Role Tools

- `create_standalone_task`: Create tasks without assignment
- Task management for workers

## Role-Based Access

- **Workers**: Create standalone tasks
- **Coordinators/Managers**: Assign tasks with `assign_task_to_worker`
- Role determined by token automatically
