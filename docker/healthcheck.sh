#!/usr/bin/env bash
set -euo pipefail
ragwarrant inspect-environment >/tmp/ragwarrant_environment.json
ragwarrant validate-bundle
