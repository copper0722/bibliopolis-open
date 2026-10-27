"""What a refusal and an error of a world file share: the message (English text) and, for a page that translates it, an id and the values the message is made of.

A leaf of the package (it imports nothing), so that the code that draws a city can raise an error with an id too (`bibliopolis.coast.CityTooLarge`), as the world does for an event
(`bibliopolis.events.Refusal`). The ids are `bibliopolis.events.CODES`."""

from __future__ import annotations


class Coded:
    """What a refusal and an error of a world file share: the message (English text) and, for a page that translates it, an id and the values the message is made of.

    `code` is the id (one of `CODES`) and `params` its values, in the names `CODES` gives, all of them plain JSON values. `event` is `{seq, kind}` when the reason is about an event
    of a log that was replayed or folded, and `where` the file, or the place in a file, when it is about one. `as_dict()` is all of it as a JSON object."""

    def __init__(self, message: str, code: str, **params):
        super().__init__(message)
        self.code = code
        self.params = params
        self.event: dict | None = None
        self.where: str | None = None

    def as_dict(self) -> dict:
        return {"code": self.code, "params": self.params, "event": self.event, "where": self.where, "message": str(self)}
