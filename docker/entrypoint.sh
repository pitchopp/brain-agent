#!/bin/sh
# Container entrypoint.
#
# If CLAUDE_OAUTH_CREDENTIALS_B64 is set, decode it into
# ~/.claude/.credentials.json before launching the app. This lets us ship the
# developer's Claude Code OAuth session into the container via a Dokploy
# secret, which bills the Claude Max/Pro subscription instead of the API key.
#
# The Python-side resolver in brain_agent.agent.auth will pick up the file
# automatically and prefer it over ANTHROPIC_API_KEY.

set -eu

if [ -n "${CLAUDE_OAUTH_CREDENTIALS_B64:-}" ]; then
    mkdir -p "$HOME/.claude"
    # `base64 -d` is the BusyBox/GNU form; both are available in debian slim.
    printf '%s' "$CLAUDE_OAUTH_CREDENTIALS_B64" | base64 -d > "$HOME/.claude/.credentials.json"
    chmod 600 "$HOME/.claude/.credentials.json"
    echo "entrypoint: wrote Claude OAuth credentials to $HOME/.claude/.credentials.json"
else
    echo "entrypoint: no CLAUDE_OAUTH_CREDENTIALS_B64 set, will rely on ANTHROPIC_API_KEY"
fi

exec "$@"
