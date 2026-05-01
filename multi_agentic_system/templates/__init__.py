"""Jinja2 template loader for agent system prompts.

Templates live alongside this file as ``*.j2`` files and are loaded from the
filesystem once at import time via a :class:`~jinja2.Environment` with
``FileSystemLoader``.

Example:
    ::

        from .templates import render

        prompt = render("code_agent.j2", task="sort a list", retries=3)
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

__all__ = ["render"]

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=False,
)


def render(template_name: str, **variables: object) -> str:
    """Render a Jinja2 template by filename with the given variables.

    Args:
        template_name: Filename of the template, e.g. ``"code_agent.j2"``.
        **variables: Template context variables.

    Returns:
        The rendered string with leading/trailing whitespace stripped.

    Raises:
        jinja2.TemplateNotFound: If ``template_name`` does not exist.
        jinja2.UndefinedError: If a required template variable is not provided.
    """
    return _env.get_template(template_name).render(**variables).strip()
