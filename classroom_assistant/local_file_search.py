from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .file_receiver import SUPPORTED_EXTENSIONS


DEFAULT_SEARCH_ROOT = Path(r"C:\Users\SiddiqShah\Documents\University_6th_Sem")


class LocalFileSearchError(RuntimeError):
    pass


@dataclass(frozen=True)
class LocalFileMatch:
    path: Path
    score: int


class LocalFileSearch:
    def __init__(self, root: Path = DEFAULT_SEARCH_ROOT) -> None:
        self.root = root

    def find_one(self, query: str) -> LocalFileMatch:
        matches = self.search(query)
        if not matches:
            raise LocalFileSearchError(f"I could not find a file matching: {query}")
        if len(matches) > 1 and matches[0].score == matches[1].score:
            options = "\n".join(f"{index}. {match.path.name}" for index, match in enumerate(matches[:5], start=1))
            raise LocalFileSearchError(f"I found multiple matching files:\n{options}\nPlease use a more specific file name.")
        return matches[0]

    def search(self, query: str) -> list[LocalFileMatch]:
        if not self.root.exists():
            raise LocalFileSearchError(f"Search folder does not exist: {self.root}")

        terms = normalize(query).split()
        if not terms:
            raise LocalFileSearchError("File search query is empty.")

        matches = []
        for path in self.root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            haystack = normalize(path.stem)
            if all(term in haystack for term in terms):
                matches.append(LocalFileMatch(path=path, score=score_match(terms, haystack)))

        return sorted(matches, key=lambda match: (-match.score, len(str(match.path))))


def normalize(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else " " for char in value)
    return " ".join(cleaned.split())


def score_match(terms: list[str], haystack: str) -> int:
    score = sum(len(term) for term in terms if term in haystack)
    if " ".join(terms) == haystack:
        score += 1000
    elif " ".join(terms) in haystack:
        score += 100
    return score
