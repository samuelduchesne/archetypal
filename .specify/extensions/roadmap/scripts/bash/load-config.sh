#!/usr/bin/env bash
# load-config.sh — Load and validate the roadmap extension configuration and emit
# a stable JSON contract on stdout.
#
# Deterministic only. Contains no judgment (Constitution Principle II): it resolves
# paths and config scalars, never parses roadmap markdown or makes decisions.
#
# Resolution order for each value: environment override → roadmap-config.yml →
# extension.yml defaults → built-in default.
#
# PRD globs are PATTERNS ONLY — this script never scans the filesystem for matches.
#
# Output (stdout, single line JSON):
#   {"roadmap_path":"...","roadmap_exists":bool,"adr_dir":"...","adr_present":bool,
#    "prd_globs":["...",...],"max_findings":N}
#
# Exit codes:
#   0 — configuration loaded and emitted
#   1 — invalid configuration value
#
# Portability: targets bash 3.2+ (macOS default). No heredocs, no temp files, no
# `mapfile`/`readarray`, no process substitution required for core paths.
set -euo pipefail

# --- Locate repo root (CWD-independent: walk up from the script's own location) --
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Walk up from a starting dir, return the first ancestor that contains a `.specify`
# directory. Echoes empty if none found.
_find_specify_root() {
    local d="$1"
    while [ -n "$d" ] && [ "$d" != "/" ]; do
        if [ -d "$d/.specify" ]; then printf '%s' "$d"; return 0; fi
        d="$(dirname -- "$d")"
    done
    # Check root itself.
    [ -d "/.specify" ] && { printf '/'; return 0; }
    return 1
}

REPO_ROOT="$(_find_specify_root "$SCRIPT_DIR" || true)"
# Fall back to walking up from CWD (covers unusual install layouts).
[ -n "$REPO_ROOT" ] || REPO_ROOT="$(_find_specify_root "$PWD" || true)"
# Last resort: CWD (no spec-kit repo located — built-in defaults still apply below).
[ -n "$REPO_ROOT" ] || REPO_ROOT="$PWD"

# --- Optionally source core common.sh for the canonical json_escape --------------
_common=""
for up in "$REPO_ROOT/.specify/scripts/bash/common.sh" \
          "$SCRIPT_DIR/../../../../.specify/scripts/bash/common.sh" \
          "$SCRIPT_DIR/../../../.specify/scripts/bash/common.sh"; do
    if [ -f "$up" ]; then _common="$up"; break; fi
done
if [ -n "$_common" ]; then
    # shellcheck source=/dev/null
    . "$_common" 2>/dev/null || true
fi

# Fallback json_escape if the core helper was not sourced (no hard dependency).
if ! declare -F json_escape >/dev/null 2>&1; then
    json_escape() {
        local s="$1"
        s="${s//\\/\\\\}"; s="${s//\"/\\\"}"
        s="${s//$'\n'/\\n}"; s="${s//$'\t'/\\t}"; s="${s//$'\r'/\\r}"
        printf '%s' "$s"
    }
fi

CONFIG_FILE="$REPO_ROOT/.specify/extensions/roadmap/roadmap-config.yml"
EXTENSION_FILE="$REPO_ROOT/.specify/extensions/roadmap/extension.yml"

# --- Built-in defaults ----------------------------------------------------------
DEF_ROADMAP_PATH=".specify/memory/roadmap.md"
DEF_ADR_DIR="docs/adr/"
DEF_MAX_FINDINGS="50"
# Newline-delimited; consumed via IFS word-splitting (no heredoc).
DEF_PRD_GLOBS='**/prd*.md
**/PRD*.md
**/prd-intake.yaml
**/product-spec.md
docs/product/**/*.md'

# --- Minimal YAML scalar reader (built-in tools only) ---------------------------
# Reads the last "key:" occurrence, trims whitespace and surrounding quotes.
yaml_scalar() {
    local key="$1" file="$2" raw
    [ -f "$file" ] || { printf ''; return; }
    raw="$(grep -E "^[[:space:]]*${key}:" "$file" | tail -n 1 | sed "s/^[^:]*://")"
    raw="$(printf '%s' "$raw" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    raw="$(printf '%s' "$raw" | sed 's/^"\(.*\)"$/\1/')"
    raw="$(printf '%s' "$raw" | sed "s/^'\(.*\)'\$/\1/")"
    if [ "$raw" = "null" ] || [ "$raw" = "~" ]; then raw=""; fi
    printf '%s' "$raw"
}

# Resolve one scalar: env override → config file → extension.yml → built-in default.
resolve() {
    local env_val="$1" key="$2" default="$3" v
    if [ -n "$env_val" ]; then printf '%s' "$env_val"; return; fi
    v="$(yaml_scalar "$key" "$CONFIG_FILE")"
    [ -n "$v" ] || v="$(yaml_scalar "$key" "$EXTENSION_FILE")"
    [ -n "$v" ] || v="$default"
    printf '%s' "$v"
}

ROADMAP_PATH="$(resolve "${SPECKIT_ROADMAP_PATH:-}" "path" "$DEF_ROADMAP_PATH")"
ADR_DIR="$(resolve "${SPECKIT_ROADMAP_ADR_DIR:-}" "dir" "$DEF_ADR_DIR")"
MAX_FINDINGS="$(resolve "${SPECKIT_ROADMAP_MAX_FINDINGS:-}" "max_findings" "$DEF_MAX_FINDINGS")"

# --- Validate -------------------------------------------------------------------
case "$MAX_FINDINGS" in
    ''|*[!0-9]*)
        echo "Error: report.max_findings must be a non-negative integer, got '$MAX_FINDINGS'" >&2
        exit 1
        ;;
esac

# --- Derived booleans -----------------------------------------------------------
case "$ROADMAP_PATH" in
    /*) roadmap_abs="$ROADMAP_PATH" ;;
    *)  roadmap_abs="$REPO_ROOT/$ROADMAP_PATH" ;;
esac
[ -f "$roadmap_abs" ] && ROADMAP_EXISTS=true || ROADMAP_EXISTS=false

case "$ADR_DIR" in
    /*) adr_abs="$ADR_DIR" ;;
    *)  adr_abs="$REPO_ROOT/$ADR_DIR" ;;
esac
[ -d "$adr_abs" ] && ADR_PRESENT=true || ADR_PRESENT=false

# --- PRD globs: PATTERNS ONLY (env CSV → config list → built-in defaults) --------
prd_globs=""
if [ -n "${SPECKIT_ROADMAP_PRD_GLOBS:-}" ]; then
    # Comma-separated env override → newline-delimited.
    prd_globs="$(printf '%s' "$SPECKIT_ROADMAP_PRD_GLOBS" | tr ',' '\n')"
else
    for f in "$CONFIG_FILE" "$EXTENSION_FILE"; do
        if [ -f "$f" ] && grep -Eq '^[[:space:]]*globs:' "$f"; then
            prd_globs="$(awk '
                /^[[:space:]]*globs:/ {ing=1; next}
                ing && /^[[:space:]]*-[[:space:]]*/ {sub(/^[[:space:]]*-[[:space:]]*/,""); gsub(/^"|"$|^'\''|'\''$/,""); print; next}
                ing && /^[[:space:]]*[^[:space:]-]/ {ing=0}
            ' "$f")"
            [ -n "$prd_globs" ] && break
        fi
    done
fi
# Never emit an empty array unless explicitly configured empty: fall back to defaults.
[ -n "$prd_globs" ] || prd_globs="$DEF_PRD_GLOBS"

# Build the prd_globs JSON array via IFS word-splitting (bash 3.2-safe, no heredoc).
globs_json=""
_old_ifs="$IFS"
IFS='
'
for g in $prd_globs; do
    [ -n "$g" ] || continue
    if [ -z "$globs_json" ]; then
        globs_json="\"$(json_escape "$g")\""
    else
        globs_json="$globs_json,\"$(json_escape "$g")\""
    fi
done
IFS="$_old_ifs"

# --- Emit JSON contract ---------------------------------------------------------
printf '{"roadmap_path":"%s","roadmap_exists":%s,"adr_dir":"%s","adr_present":%s,"prd_globs":[%s],"max_findings":%s}\n' \
    "$(json_escape "$ROADMAP_PATH")" "$ROADMAP_EXISTS" \
    "$(json_escape "$ADR_DIR")" "$ADR_PRESENT" \
    "$globs_json" "$MAX_FINDINGS"
