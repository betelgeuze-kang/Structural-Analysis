#!/usr/bin/env bash
# Scope a hosted Ubuntu browser-dependency install to the OS package sources.
# Existing source files, keys, authentication and hash checks remain unchanged.
set -euo pipefail

with_ubuntu_apt_sources() (
  set -euo pipefail
  local apt_root="$1"
  shift
  if [[ "$#" -eq 0 || ! -f "$apt_root/sources.list.d/ubuntu.sources" ]]; then
    echo "Expected a command and Ubuntu's deb822 source file" >&2
    return 2
  fi
  # APT string literals cannot contain these characters unescaped. The caller
  # uses /etc/apt; reject them in the testable function as well.
  if [[ "$apt_root" != /* || "$apt_root" == *'"'* || "$apt_root" == *'\'* || "$apt_root" == *$'\n'* ]]; then
    echo "Invalid APT configuration directory" >&2
    return 2
  fi
  local apt_override
  apt_override="$(sudo mktemp "$apt_root/apt.conf.d/zzzz-structural-browser-XXXXXXXX")"
  trap 'sudo rm -- "$apt_override"' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  printf 'Dir::Etc::sourcelist "%s/sources.list.d/ubuntu.sources";\nDir::Etc::sourceparts "-";\n' \
    "$apt_root" | sudo tee "$apt_override" >/dev/null
  sudo chmod 644 "$apt_override"
  "$@"
)

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  if [[ "${GITHUB_ACTIONS:-}" != true || "${RUNNER_ENVIRONMENT:-}" != github-hosted || "${RUNNER_OS:-}" != Linux ]]; then
    echo "This wrapper is restricted to GitHub-hosted Linux CI" >&2
    exit 2
  fi
  with_ubuntu_apt_sources /etc/apt "$@"
fi
