################################################################################
# Codespaces dev image for the wize73 class chatbot.
#
# Base: Microsoft's official devcontainer Python 3.12 image. It comes
# with the vscode user, ssh, git, common build tools, and a sane shell
# pre-configured. We add the tooling that students and the agents need.
#
# Students click "Code → Codespaces → Create" and get this environment
# in <30 seconds in the browser. No local setup, no Python install
# debugging, no "works on my machine" — every student starts identical.
################################################################################

FROM mcr.microsoft.com/devcontainers/python:3.12

# Tools we want available in every dev session:
#   ripgrep — fast text search (replaces grep for symbol navigation)
#   universal-ctags — jump-to-definition for VS Code's "go to symbol"
#   jq — structured JSON manipulation in scripts
#   tree — quick directory inspection
#   nftables — let students poke at the firewall rules locally
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ripgrep \
        universal-ctags \
        jq \
        tree \
        nftables \
    && rm -rf /var/lib/apt/lists/*

# Pre-install pip-tools for dep updates and uv as a faster pip alternative.
# These are dev-time conveniences; the actual locked manifest is in
# requirements.txt at the repo root.
RUN pip install --no-cache-dir \
    pip-tools==7.4.1 \
    uv==0.5.5

# Make ~/.local/bin (where post-create installs symlinks) writable.
USER vscode
RUN mkdir -p ~/.local/bin

# The repo gets mounted into /workspaces by the devcontainer runtime.
WORKDIR /workspaces/slim
