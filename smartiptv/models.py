"""Provider-independent catalog records. Playback URLs never enter the library."""
from dataclasses import asdict, dataclass, fields


def integer(value, default=0):
    try:
        return int(float(value or 0))
    except (ValueError, TypeError, OverflowError):
        return default


@dataclass(frozen=True)
class Content:
    kind: str
    id: str
    name: str
    categories: tuple = ()
    artwork: str = ""
    added: int = 0
    year: str = ""
    rating: str = ""
    plot: str = ""
    extension: str = "mp4"
    series_id: str = ""
    series_name: str = ""
    season: int = 0
    episode: int = 0
    duration_ms: int = 0

    @property
    def uid(self):
        return f"{self.kind}:{self.id}"

    @property
    def display_name(self):
        if self.kind == "episode" and self.series_name:
            return f"{self.series_name} · T{self.season:02} E{self.episode:02}"
        return self.name

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        data = {k: v for k, v in data.items() if k in {f.name for f in fields(cls)}}
        data["categories"] = tuple(data.get("categories") or ())
        return cls(**data)


def content_from_api(kind, data):
    item_id = str(data.get("series_id" if kind == "series" else "stream_id") or "")
    if not item_id:
        return None
    categories = data.get("category_ids") or [data.get("category_id")]
    if not isinstance(categories, (list, tuple)):
        categories = [categories]
    return Content(
        kind, item_id, str(data.get("name") or data.get("title") or "Sem título"),
        tuple(str(c) for c in categories if c is not None),
        str(data.get("cover" if kind == "series" else "stream_icon") or ""),
        integer(data.get("last_modified") if kind == "series" else data.get("added")),
        str(data.get("year") or ""), str(data.get("rating") or ""),
        str(data.get("plot") or ""), str(data.get("container_extension") or "mp4"),
    )


def episodes_from_api(series, payload):
    result = []
    groups = payload.get("episodes") or {}
    if isinstance(groups, list):
        groups = {"1": groups}
    if not isinstance(groups, dict):
        return []
    seen = set()
    for season_key, episodes in groups.items():
        if not isinstance(episodes, list):
            continue
        for entry in episodes:
            if not isinstance(entry, dict) or not entry.get("id"):
                continue
            item_id = str(entry["id"])
            if item_id in seen:
                continue
            seen.add(item_id)
            info = entry.get("info") if isinstance(entry.get("info"), dict) else {}
            season = integer(entry.get("season") or info.get("season") or season_key, 1)
            number = integer(entry.get("episode_num") or info.get("episode_num"), len(result) + 1)
            result.append(Content(
                "episode", item_id, str(entry.get("title") or f"Episódio {number}"),
                series.categories, series.artwork, integer(entry.get("added")),
                series.year, series.rating, str(info.get("plot") or ""),
                str(entry.get("container_extension") or "mp4"), series.id,
                series.name, season, number, integer(info.get("duration_secs")) * 1000,
            ))
    return sorted(result, key=lambda ep: (ep.season, ep.episode, ep.name.casefold()))
