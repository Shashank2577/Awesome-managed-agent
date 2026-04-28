# Sandbox Dockerfiles

One Dockerfile per harness runtime. CI builds these and pushes them to a
private registry (ECR for the EKS deployment). The image tag is what
`Runtime.image_tag()` returns.

## Image conventions

All sandbox images:

* Run as a non-root user (`atrium:atrium`, uid 10001).
* Have `/workspace` as the working directory (mount point for the
  session filesystem).
* Have `/run/atrium/mcp.sock` as a Unix socket bind mount for the MCP
  gateway.
* Include `ripgrep`, `git`, `curl`, `jq` as standard tools — most
  agentic loops expect them.
* Expect `ATRIUM_SESSION_ID`, `ATRIUM_WORKSPACE_ID`, the model API key,
  and any runtime-specific env vars in the environment.
* Emit JSON-line events on stdout. Anything on stderr is treated as
  debug logs and ignored by the bridge.

## Files (to be added)

| File | Image | Phase |
|------|-------|-------|
| `echo.Dockerfile` | `atrium-echo:*` | 2 |
| `open_agent_sdk.Dockerfile` | `atrium-oas:*` | 3 |
| `direct_anthropic.Dockerfile` | `atrium-anthropic:*` | 3 |
| `openclaude.Dockerfile` | `atrium-openclaude:*` | 4 |

Each Dockerfile is short — a `FROM node:22-slim` or `FROM python:3.12-slim`
base, a few apt installs, a `RUN npm install -g <package>` or `pip install
<package>`, and a CMD that reads stdin / writes stdout in stream-json mode.

## Build automation

A GitHub Actions workflow (`.github/workflows/sandbox-images.yml`, also TBD)
builds and pushes images on tag, with multi-arch support for arm64
(M-series Macs in dev) and amd64 (EKS nodes). Image tags are pinned in the
runtime adapter; bumps go through CI.
