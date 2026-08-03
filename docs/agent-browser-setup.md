# agent-browser MCP — host setup (GB10)

[`vercel-labs/agent-browser`](https://github.com/vercel-labs/agent-browser) drives a real Chromium,
so frontend work on this project can be **inspected rather than guessed at** — read the rendered DOM,
click things, measure layout, screenshot. Registered project-wide in [`../.mcp.json`](../.mcp.json).

Installed 2026-08-03. Everything below is **no-root**: `ishan` is not in sudoers on
`helix-gb10-intern` (verified again during this install — `sudo` returns *"user ishan may not run
sudo"*; the Tailscale console shows *tailnet* ownership, which is a different thing).

## What was installed

| Component | Version | Location | Why |
|---|---|---|---|
| Node.js | v24.19.0 (arm64) | `~/.local/node`, symlinked into `~/.local/bin` | No system Node existed |
| `agent-browser` | 0.33.2 | `~/.local/node/bin/agent-browser` | The MCP server |
| Chromium | 131.0.6778.33 (Playwright build 1148) | `~/.cache/ms-playwright/chromium-1148/` | See below |

## Two GB10-specific gotchas

**1. `agent-browser install` does not work here.** Chrome for Testing publishes no Linux ARM64
build, and its suggested fallback (`sudo apt install chromium-browser`) needs root. Playwright *does*
ship an arm64 Chromium, and downloading it needs no root:

```bash
npx --yes playwright@1.49.1 install chromium
```

**2. Chromium needs `--no-sandbox` on this host.** Ubuntu 24.04 restricts unprivileged user
namespaces via AppArmor, so Chromium aborts with *"No usable sandbox!"*. `.mcp.json` sets
`AGENT_BROWSER_ARGS=--no-sandbox`.

> This does weaken the browser sandbox. It is acceptable here because navigation is pinned to
> `localhost,127.0.0.1` via `AGENT_BROWSER_ALLOWED_DOMAINS` — the only thing this browser ever visits
> is the demo running on this box. Widen that deliberately, not casually.

## Reproducing from scratch

```bash
# 1. Node (arm64, user-local)
curl -sSLo /tmp/node.tar.xz https://nodejs.org/dist/v24.19.0/node-v24.19.0-linux-arm64.tar.xz
mkdir -p ~/.local/node && tar -xJf /tmp/node.tar.xz -C ~/.local/node --strip-components=1
export PATH="$HOME/.local/node/bin:$PATH"

# 2. agent-browser
npm install -g agent-browser

# 3. Chromium (Chrome for Testing has no arm64 build)
npx --yes playwright@1.49.1 install chromium
```

Then confirm the MCP server starts:

```bash
export AGENT_BROWSER_EXECUTABLE_PATH=~/.cache/ms-playwright/chromium-1148/chrome-linux/chrome
export AGENT_BROWSER_ARGS=--no-sandbox
agent-browser mcp --tools core,debug,react   # speaks JSON-RPC on stdio; Ctrl-C to exit
```

Verified 2026-08-03: `initialize` returns `agent-browser 0.33.2`, `tools/list` returns **64 tools**
including `agent_browser_open`, `agent_browser_eval`, `agent_browser_screenshot`.

## Quick CLI use (outside MCP)

```bash
AB="agent-browser --executable-path $HOME/.cache/ms-playwright/chromium-1148/chrome-linux/chrome --args --no-sandbox"
$AB open "http://localhost:8081/?view=dataset&scenario=component-shortage-shock"
$AB eval "document.querySelector('section p.text-lg').innerText"
```

Smoke-tested against the live dataset view: it read back the real hero sentence, the real tiles
(17 locations / 28 products / 30 lanes) and counted the **2 disrupted lanes** drawn in the SVG.

## Relationship to `make web-check`

They do different jobs and both stay:

- **`make web-check`** is the repeatable regression gate — fixed assertions, runs in CI-style,
  fails loudly. It is what proves Level 1 still fits above the fold.
- **agent-browser** is for *exploration* during development — poke at a page, read the DOM, try a
  click, see why something looks wrong. Findings that matter get promoted into `web-check`.

## Known rough edge

`agent-browser wait --selector "svg[role=img]"` timed out even though the element was present and a
subsequent `eval` read it fine. Not chased; use `eval` with a retry, or `snapshot`, until it is
understood.
