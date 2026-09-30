# Scope browser dependency installation to Ubuntu package sources

At head `1879f0d155d7594aba5d71206af08803a9db528a`, CI runs
[34384593645](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34384593645)
and [34384586390](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34384586390)
both fail at `Install Playwright browser`, before numerical evidence
materialization. Their original logs report an APT hash mismatch for
`https://dl.google.com/linux/chrome-stable/deb/dists/stable/main/binary-amd64/Packages.gz`.
The expected SHA-256 is
`233e56de019b57db89238fa7bcc3647718dbbea3a40c2dc1c633a8c8952aa9e9`;
the received SHA-256 is
`bc1428ab27c6d76ee9bb76de07f1ded0ddb4aaabd958fc72855634ef5894a4b3`.
These are observed repository-index inconsistencies, not evidence of a product
regression or a completed downstream test run.

The original run/job metadata and both logs are retained at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-stop-ci-n85xujjk`:
five files / 566,918 bytes, inventory SHA-256
`fcb7809d7b994627f7c88a0e678099aac2ec7beba31558863d1aa902ac620a24`.

## Change

[The shared wrapper](../../scripts/with-ubuntu-apt-sources.sh) runs each existing
Playwright `install --with-deps chromium` command with a temporary APT
configuration selecting `/etc/apt/sources.list.d/ubuntu.sources` and disabling
additional source-part discovery for that command. It uses the runner's original
Ubuntu source file, including its suites, components and signing-key settings.
No package source, key, browser version, lockfile, TLS setting, signature check
or package hash is replaced. Playwright still resolves and installs its own
system dependencies and browser binaries.

The configuration filename is allocated exclusively with `mktemp` under
`apt.conf.d`; it cannot overwrite an existing configuration. An exit trap removes
only that file. The command's ordinary failure status remains a failure; setup
failure and handled termination also clean the override. Original source and
configuration files are left intact. The CLI is limited to GitHub-hosted Linux;
the required Ubuntu deb822 file must exist. It is not run against the local
workstation's system configuration. Uncatchable termination cannot run traps;
the intended hosts are disposable CI runners, not persistent self-hosted machines.

Six workflows use the wrapper: CI, Frontend Web CI, Runtime Input and Viewer CI,
Viewer Browser CI, Native Frame Alpha Clean Install, and Nightly Full Quality.
Path-filtered workflows also watch the wrapper. Frontend Web CI retains its
verified Node executable and isolated environment, and all existing install
arguments and downstream checks remain unchanged.

The [Playwright documentation](https://playwright.dev/docs/browsers#install-system-dependencies)
distinguishes browser downloads from system dependency installation. Ubuntu
[documents the deb822 source file](https://ubuntu.com/project/docs/how-ubuntu-is-made/concepts/package-archive/)
and [APT source configuration](https://manpages.ubuntu.com/manpages/noble/man5/sources.list.5.html).
The repository's installed Playwright implementation performs `apt-get update`
before installing its Linux package list; this explains the unrelated Chrome
repository being contacted by the original command.

## Local verification and limits

The final selection passes **37 tests in 2.00 seconds**, covering the wrapper,
product CI contracts, native clean-install contracts, and strict workflow YAML.
The preceding selection passes 35 tests before two additional failure-cleanup
cases are added. Bash syntax, Ruff and diff checks pass. ShellCheck is unavailable
locally and is not claimed as executed.

The wrapper tests execute actual shell commands and APT configuration parsing in
an unprivileged temporary directory, substituting only privilege elevation.
`apt-get --print-uris update` initially lists both unrelated sources; inside the
wrapper it lists only the original Ubuntu suites; afterward the original URI list
is restored exactly. This mode performs no repository downloads or installation.
Other cases verify exact argument forwarding, status 37 propagation, setup failure,
SIGTERM cleanup, missing-source rejection, local-host rejection and integration
across all six workflows. These tests do not exercise real sudo or hosted package
installation. Hosted installation results must be observed at the published head
before claiming this CI failure resolved.

The external reaction discrepancies, independent verification, public experiment
reconstruction, learned net performance, signed-artifact acceptance and full
M1-M5/P1-P3/R1-R2 roadmap remain open. The wrapper changes package-source scope for
browser setup; it does not bypass any numerical or release gate.
