"""Normalize ``SKILLFORGE_ROUTER_MODE`` (default **host**, explicit ``auto`` for legacy routing)."""


def normalise_skillforge_router_mode(env_value: str) -> str:
    """Return router mode token for ``app.main``

    Expect ``env_value`` from ``os.getenv("SKILLFORGE_ROUTER_MODE", "host")``.

    Returns
    -------
    ""
        **auto** — use Haiku when ``ANTHROPIC_API_KEY`` is set, else embedding-first.
    "host" | "embedding" | "full"
        As selected.

    **Unset** env → pass default ``"host"`` from ``getenv``. **Explicit auto:** ``auto`` or empty string.
    """
    s = (env_value or "").strip().lower()
    if s in ("", "auto"):
        return ""
    return s
