"""A fake ``vercel.blob.sync.put_blob``. Never touches the network."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

HOST = "https://fake-store.public.blob.vercel-storage.com"


@dataclass
class FakeBlob:
    """Records every upload and answers like the real client's result object."""

    calls: list[dict[str, Any]] = field(default_factory=list)
    results: list[Any] = field(default_factory=list)
    error: Exception | None = None

    def __call__(
        self,
        pathname: str,
        body: bytes,
        *,
        access: str,
        content_type: str | None = None,
        add_random_suffix: bool = False,
        **kwargs: Any,
    ) -> Any:
        self.calls.append(
            {
                "pathname": pathname,
                "body": body,
                "access": access,
                "content_type": content_type,
                "add_random_suffix": add_random_suffix,
                "kwargs": kwargs,
            }
        )
        if self.error is not None:
            raise self.error
        stem, dot, ext = pathname.rpartition(".")
        stored = f"{stem}-Xk29aQ{dot}{ext}" if add_random_suffix else pathname
        result = SimpleNamespace(url=f"{HOST}/{stored}", pathname=stored)
        self.results.append(result)
        return result
