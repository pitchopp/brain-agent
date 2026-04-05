FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

# System dependencies:
# - git, openssh-client : cloning and pushing the brain repo
# - ripgrep             : used by the SDK's Grep tool
# - curl, ca-certificates, gnupg : for NodeSource + uv installers
# - nodejs              : required because the Claude Agent SDK spawns the
#                         Claude Code CLI as a subprocess
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        openssh-client \
        ripgrep \
        curl \
        ca-certificates \
        gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
        | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
        > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI globally (required runtime for the Agent SDK).
RUN npm install -g @anthropic-ai/claude-code

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.11.2 /uv /uvx /usr/local/bin/

WORKDIR /app

# Install Python deps into a cached layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Install the project itself.
COPY src ./src
RUN uv sync --frozen --no-dev

ENV PATH="/opt/venv/bin:$PATH"

# Brain working copy lives here (mount as a volume).
RUN mkdir -p /data/brain

EXPOSE 8000

CMD ["uvicorn", "brain_agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
