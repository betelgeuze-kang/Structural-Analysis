#!/usr/bin/env bash
# Bound the audited Playwright system-package and browser installation phases.
set -euo pipefail

install_playwright_chromium_ci() (
  set -euo pipefail
  if [[ "$#" -ne 9 ]]; then
    echo "Expected APT root, trusted Node, CLI, isolated home/tmp, log and three limits" >&2
    return 2
  fi
  local apt_root="$1" trusted_node="$2" playwright_cli="$3"
  local repository_home="$4" repository_tmp="$5" diagnostic_log="$6"
  local dependency_limit="$7" browser_limit="$8" kill_grace="$9"
  local input
  for input in "$apt_root" "$trusted_node" "$playwright_cli" "$repository_home" "$repository_tmp" "$diagnostic_log"; do
    if [[ "$input" != /* || "$input" == *$'\n'* || "$input" == *$'\r'* ]]; then
      echo "Expected absolute paths without line breaks" >&2
      return 2
    fi
  done
  if [[ "$apt_root" == *'"'* || "$apt_root" == *'\'* ||
        ! -f "$apt_root/sources.list.d/ubuntu.sources" ||
        ! -x "$trusted_node" || ! -f "$playwright_cli" ||
        ! -d "$repository_home" || ! -d "$repository_tmp" ]]; then
    echo "Missing or invalid isolated installation input" >&2
    return 2
  fi
  for input in "$dependency_limit" "$browser_limit" "$kill_grace"; do
    if [[ ! "$input" =~ ^[1-9][0-9]*(s|m)$ ]]; then
      echo "Expected a positive whole-second or whole-minute limit" >&2
      return 2
    fi
  done
  mkdir -p -- "$(dirname -- "$diagnostic_log")"
  : > "$diagnostic_log"
  local apt_override="" dependency_home="" dependency_tmp="" source_digest=""
  log_install() {
    if printf '%s\n' "$*" | tee -a "$diagnostic_log"; then
      return 0
    fi
    printf '%s\n' "$*" >&2
    return 1
  }
  cleanup_install() {
    local status="$?" cleanup_status=0
    trap - EXIT INT TERM
    if [[ -n "$apt_override" ]]; then
      sudo -n -- rm -f -- "$apt_override" || cleanup_status=1
    fi
    if [[ -n "$dependency_home" ]]; then
      sudo -n -- rm -rf -- "$dependency_home" || cleanup_status=1
    fi
    if [[ -n "$dependency_tmp" ]]; then
      sudo -n -- rm -rf -- "$dependency_tmp" || cleanup_status=1
    fi
    local final_source_digest="" source_status=unavailable
    if final_source_digest="$(sha256sum -- "$apt_root/sources.list.d/ubuntu.sources")"; then
      if [[ "$final_source_digest" == "$source_digest" ]]; then
        source_status=unchanged
      else
        source_status=changed
      fi
    fi
    if ! log_install "finish=$(date -u +%FT%TZ) status=$status cleanup_status=$cleanup_status ubuntu_sources_sha256=${final_source_digest%% *} source_bytes=$source_status"; then
      cleanup_status=1
    fi
    if [[ "$status" -eq 0 && "$cleanup_status" -ne 0 ]]; then
      status=1
    fi
    if [[ "$status" -eq 0 && "$source_status" != unchanged ]]; then
      status=1
    fi
    exit "$status"
  }
  trap cleanup_install EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  source_digest="$(sha256sum -- "$apt_root/sources.list.d/ubuntu.sources")"
  log_install "ubuntu_sources_sha256=${source_digest%% *} http_timeout_seconds=30 https_timeout_seconds=30 retries=0"
  apt_override="$(sudo -n -- mktemp "$apt_root/apt.conf.d/zzzz-structural-browser-XXXXXXXX")"
  printf 'Dir::Etc::sourcelist "%s/sources.list.d/ubuntu.sources";\nDir::Etc::sourceparts "-";\nAcquire::http::Timeout "30";\nAcquire::https::Timeout "30";\nAcquire::Retries "0";\n' \
    "$apt_root" | sudo -n -- tee "$apt_override" >/dev/null
  sudo -n -- chmod 644 "$apt_override"
  dependency_home="$(mktemp -d "$repository_tmp/playwright-dependency-home-XXXXXXXX")"
  dependency_tmp="$(mktemp -d "$repository_tmp/playwright-dependency-tmp-XXXXXXXX")"
  local status
  local -a phase_statuses
  log_install "phase=system_dependencies start=$(date -u +%FT%TZ) deadline=$dependency_limit kill_grace=$kill_grace"
  # The audited CLI runs as root only for install-deps. Playwright 1.56.1 then
  # invokes sh directly, so a privileged timeout supervises its ordinary APT
  # descendants without a second sudo session. This is not a claim about
  # arbitrary processes that escape the supervised process group.
  if sudo -n -- /usr/bin/timeout --signal=TERM --kill-after="$kill_grace" "$dependency_limit" \
    /usr/bin/env -i "PATH=${trusted_node%/node}:/usr/bin:/bin" \
    "HOME=$dependency_home" "TMPDIR=$dependency_tmp" LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    "$trusted_node" "$playwright_cli" install-deps chromium 2>&1 | tee -a "$diagnostic_log"; then
    status=0
  else
    phase_statuses=("${PIPESTATUS[@]}")
    status="${phase_statuses[0]}"
    if [[ "$status" -eq 0 ]]; then
      status="${phase_statuses[1]}"
    fi
  fi
  if ! log_install "phase=system_dependencies finish=$(date -u +%FT%TZ) status=$status"; then
    if [[ "$status" -eq 0 ]]; then
      status=1
    fi
  fi
  if [[ "$status" -ne 0 ]]; then
    return "$status"
  fi
  log_install "phase=browser_download start=$(date -u +%FT%TZ) deadline=$browser_limit kill_grace=$kill_grace"
  if /usr/bin/timeout --signal=TERM --kill-after="$kill_grace" "$browser_limit" \
    /usr/bin/env -i "PATH=${trusted_node%/node}:/usr/bin:/bin" \
    "HOME=$repository_home" "TMPDIR=$repository_tmp" LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    "$trusted_node" "$playwright_cli" install chromium 2>&1 | tee -a "$diagnostic_log"; then
    status=0
  else
    phase_statuses=("${PIPESTATUS[@]}")
    status="${phase_statuses[0]}"
    if [[ "$status" -eq 0 ]]; then
      status="${phase_statuses[1]}"
    fi
  fi
  if ! log_install "phase=browser_download finish=$(date -u +%FT%TZ) status=$status"; then
    if [[ "$status" -eq 0 ]]; then
      status=1
    fi
  fi
  return "$status"
)

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  if [[ "${GITHUB_ACTIONS:-}" != true || "${RUNNER_ENVIRONMENT:-}" != github-hosted || "${RUNNER_OS:-}" != Linux ]]; then
    echo "This installer is restricted to GitHub-hosted Linux CI" >&2
    exit 2
  fi
  if [[ "$#" -ne 5 ]]; then
    echo "Expected trusted Node, audited CLI, isolated home/tmp and diagnostics log" >&2
    exit 2
  fi
  install_playwright_chromium_ci /etc/apt "$1" "$2" "$3" "$4" "$5" 600s 300s 30s
fi
