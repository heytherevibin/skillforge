#!/usr/bin/env bash
# Shared continuous-learning-v2 data-directory resolver.
#
# Resolution precedence:
#   1. SKILLFORGE_HOMUNCULUS_DIR, when absolute
#   2. XDG_DATA_HOME/skillforge-homunculus, when XDG_DATA_HOME is absolute
#   3. HOME/.local/share/skillforge-homunculus

_sf_resolve_homunculus_dir() {
  if [ -n "${SKILLFORGE_HOMUNCULUS_DIR:-}" ]; then
    case "$SKILLFORGE_HOMUNCULUS_DIR" in
      /*) printf '%s\n' "$SKILLFORGE_HOMUNCULUS_DIR"; return 0 ;;
      *) printf '[skillforge] SKILLFORGE_HOMUNCULUS_DIR=%s is not absolute; ignoring\n' "$SKILLFORGE_HOMUNCULUS_DIR" >&2 ;;
    esac
  fi

  if [ -n "${XDG_DATA_HOME:-}" ]; then
    case "$XDG_DATA_HOME" in
      /*) printf '%s/skillforge-homunculus\n' "$XDG_DATA_HOME"; return 0 ;;
      *) printf '[skillforge] XDG_DATA_HOME=%s is not absolute; ignoring\n' "$XDG_DATA_HOME" >&2 ;;
    esac
  fi

  case "${HOME:-}" in
    /*) printf '%s/.local/share/skillforge-homunculus\n' "$HOME" ;;
    *)
      printf '[skillforge] HOME=%s is not absolute; cannot resolve homunculus dir\n' "${HOME:-}" >&2
      return 1
      ;;
  esac
}
