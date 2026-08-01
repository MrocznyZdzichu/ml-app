"""Human-friendly rendering for typed ML App client results."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from html import escape
from typing import Any, Mapping

from .models import CatalogPage


class ObjectPresentation:
    """A notebook- and terminal-friendly view of one client response object."""

    def __init__(self, value: Any, *, title: str | None = None) -> None:
        self.value = value
        self.title = title or type(value).__name__

    def _fields(self) -> list[tuple[str, Any]]:
        if isinstance(self.value, CatalogPage):
            return [
                ("items on this page", len(self.value.items)),
                ("matching items", self.value.total),
                ("page limit", self.value.limit),
                ("page offset", self.value.offset),
                ("has next page", self.value.has_next),
            ]
        if is_dataclass(self.value):
            return [
                (field.name, getattr(self.value, field.name))
                for field in fields(self.value)
                if field.name != "raw"
            ]
        if isinstance(self.value, Mapping):
            return [(str(key), value) for key, value in self.value.items() if key != "raw"]
        return [("value", self.value)]

    @staticmethod
    def _format(value: Any) -> str:
        if value is None or value == "":
            return "—"
        if isinstance(value, bool):
            return "yes" if value else "no"
        if isinstance(value, (list, tuple, set)):
            return ", ".join(ObjectPresentation._format(item) for item in value) or "—"
        if isinstance(value, Mapping):
            return ", ".join(f"{key}: {ObjectPresentation._format(item)}" for key, item in value.items()) or "—"
        return str(value)

    def __str__(self) -> str:
        width = max((len(name) for name, _ in self._fields()), default=0)
        rows = "\n".join(
            f"{name.ljust(width)} : {self._format(value)}"
            for name, value in self._fields()
        )
        return f"{self.title}\n{rows}"

    def _repr_html_(self) -> str:
        rows = "".join(
            "<tr>"
            f"<th>{escape(name.replace('_', ' ').title())}</th>"
            f"<td>{escape(self._format(value))}</td>"
            "</tr>"
            for name, value in self._fields()
        )
        return (
            '<div class="mlapp-object-view" style="max-width:900px;font-family:system-ui,sans-serif;">'
            f'<div style="margin:0 0 8px;font-size:18px;font-weight:700;">{escape(self.title)}</div>'
            '<table class="mlapp-object-table" style="border-collapse:collapse;min-width:580px;background:#121d30;color:#eaf1ff;">'
            f"<tbody>{rows}</tbody></table>"
            "<style>"
            ".mlapp-object-view th,.mlapp-object-view td{padding:9px 12px;border-bottom:1px solid #2d405d;text-align:left;vertical-align:top;}"
            ".mlapp-object-view th{width:190px;color:#a3e635;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;}"
            ".mlapp-object-view td{white-space:pre-wrap;word-break:break-word;}"
            "</style></div>"
        )


class PresentationClientMixin:
    """Convenient display methods composed into :class:`MLAppClient`."""

    def present(self, value: Any, *, title: str | None = None) -> ObjectPresentation:
        """Return a rich view for a typed client object, mapping, or catalog page."""
        return ObjectPresentation(value, title=title)

    def display_object(self, value: Any, *, title: str | None = None) -> ObjectPresentation:
        """Render a client object in IPython, or print its readable terminal form.

        The returned :class:`ObjectPresentation` can also be passed to a custom
        display function.  No IPython dependency is required for normal scripts.
        """
        presentation = self.present(value, title=title)
        try:
            from IPython.display import display
        except ImportError:
            print(presentation)
        else:
            display(presentation)
        return presentation
