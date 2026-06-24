#!/usr/bin/env bash
set -euo pipefail

agent="${1:-codex}"
expected_login="${2:-}"

case "$agent" in
  claude|codex) ;;
  *)
    echo "usage: $0 <claude|codex> [expected-github-login]" >&2
    exit 64
    ;;
esac

if [[ -z "$expected_login" ]]; then
  case "$agent" in
    claude) expected_login="hallovorld" ;;
    codex) expected_login="haorensjtu-dev" ;;
  esac
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
agent_env="${RENQUANT_AGENT_GH_ENV:-$repo_root/../RenQuant/scripts/agent_gh_env.sh}"

if [[ -f "$agent_env" ]]; then
  # Loads GH_TOKEN / RENQUANT_<AGENT>_GH_TOKEN from Keychain without printing it.
  # The loader may print a non-secret status line; token values must stay hidden.
  # shellcheck source=/dev/null
  source "$agent_env" "$agent" >/dev/null
fi

login="$(gh api user --jq .login)"
if [[ "$login" != "$expected_login" ]]; then
  echo "wrong GitHub actor for $agent: got '$login', expected '$expected_login'" >&2
  echo "run: source ../RenQuant/scripts/agent_gh_env.sh $agent" >&2
  exit 1
fi

echo "$agent GitHub actor OK: $login"
