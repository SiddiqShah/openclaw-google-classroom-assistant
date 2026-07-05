from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from .config import RAG_DB_PATH


class RagStore:
    def __init__(self, path: Path = RAG_DB_PATH) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with closing(self.connect()) as connection:
            connection.executescript(
                """
                create table if not exists rag_documents (
                    id integer primary key autoincrement,
                    owner_phone text not null,
                    title text not null,
                    category text not null default '',
                    original_name text not null,
                    stored_path text not null,
                    status text not null default 'uploaded',
                    created_at text not null default current_timestamp,
                    updated_at text not null default current_timestamp
                );

                create table if not exists rag_chunks (
                    id integer primary key autoincrement,
                    document_id integer not null references rag_documents(id) on delete cascade,
                    chunk_index integer not null,
                    page_number integer,
                    text text not null,
                    created_at text not null default current_timestamp
                );

                create table if not exists rag_queries (
                    id integer primary key autoincrement,
                    owner_phone text not null,
                    question text not null,
                    answer text not null,
                    created_at text not null default current_timestamp
                );
                """
            )
            connection.commit()

    def record_document(
        self,
        owner_phone: str,
        title: str,
        category: str,
        original_name: str,
        stored_path: str,
        status: str = "uploaded",
    ) -> int:
        with closing(self.connect()) as connection:
            cursor = connection.execute(
                """
                insert into rag_documents (owner_phone, title, category, original_name, stored_path, status)
                values (?, ?, ?, ?, ?, ?)
                """,
                (owner_phone, title, category, original_name, stored_path, status),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def list_documents(self, owner_phone: str) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                select d.id, d.title, d.category, d.original_name, d.stored_path, d.status,
                       d.created_at, count(c.id) as chunk_count
                from rag_documents d
                left join rag_chunks c on c.document_id = d.id
                where d.owner_phone = ?
                group by d.id
                order by d.id desc
                """,
                (owner_phone,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_document(self, document_id: int, owner_phone: str = "") -> dict[str, Any] | None:
        with closing(self.connect()) as connection:
            if owner_phone:
                row = connection.execute(
                    """
                    select id, owner_phone, title, category, original_name, stored_path, status, created_at
                    from rag_documents
                    where id = ? and owner_phone = ?
                    """,
                    (document_id, owner_phone),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    select id, owner_phone, title, category, original_name, stored_path, status, created_at
                    from rag_documents
                    where id = ?
                    """,
                    (document_id,),
                ).fetchone()
        return dict(row) if row else None

    def latest_document(self, owner_phone: str, status: str = "") -> dict[str, Any] | None:
        with closing(self.connect()) as connection:
            query = """
                select id, owner_phone, title, category, original_name, stored_path, status, created_at
                from rag_documents
                where owner_phone = ?
            """
            params: list[Any] = [owner_phone]
            if status:
                query += " and status = ?"
                params.append(status)
            query += " order by id desc limit 1"
            row = connection.execute(query, tuple(params)).fetchone()
        return dict(row) if row else None

    def find_documents(self, owner_phone: str, query: str = "", status: str = "") -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            sql = """
                select id, owner_phone, title, category, original_name, stored_path, status, created_at
                from rag_documents
                where owner_phone = ?
            """
            params: list[Any] = [owner_phone]
            if status:
                sql += " and status = ?"
                params.append(status)
            rows = connection.execute(sql, tuple(params)).fetchall()

        documents = [dict(row) for row in rows]
        terms = normalized_terms(query)
        if not terms:
            return sorted(documents, key=lambda item: int(item["id"]), reverse=True)

        scored: list[tuple[int, dict[str, Any]]] = []
        for document in documents:
            haystack = " ".join(
                normalized_terms(
                    " ".join(
                        [
                            str(document.get("title", "")),
                            str(document.get("original_name", "")),
                            str(document.get("category", "")),
                        ]
                    )
                )
            )
            score = sum(1 for term in terms if term in haystack)
            if " ".join(terms) in haystack:
                score += 10
            if score > 0:
                scored.append((score, document))
        scored.sort(key=lambda pair: (-pair[0], -int(pair[1]["id"])))
        return [document for _, document in scored]

    def find_duplicate_document(self, owner_phone: str, original_name: str, category: str = "") -> dict[str, Any] | None:
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                select id, owner_phone, title, category, original_name, stored_path, status, created_at
                from rag_documents
                where owner_phone = ? and original_name = ? and category = ?
                order by id desc
                limit 1
                """,
                (owner_phone, original_name, category),
            ).fetchone()
        return dict(row) if row else None

    def update_document_status(self, document_id: int, status: str) -> None:
        with closing(self.connect()) as connection:
            connection.execute(
                """
                update rag_documents
                set status = ?, updated_at = current_timestamp
                where id = ?
                """,
                (status, document_id),
            )
            connection.commit()

    def delete_document(self, document_id: int, owner_phone: str) -> bool:
        document = self.get_document(document_id=document_id, owner_phone=owner_phone)
        if document is None:
            return False
        with closing(self.connect()) as connection:
            connection.execute("delete from rag_chunks where document_id = ?", (document_id,))
            cursor = connection.execute(
                "delete from rag_documents where id = ? and owner_phone = ?",
                (document_id, owner_phone),
            )
            connection.commit()
            return cursor.rowcount > 0

    def replace_chunks(self, document_id: int, chunks: list[dict[str, Any]]) -> None:
        with closing(self.connect()) as connection:
            connection.execute("delete from rag_chunks where document_id = ?", (document_id,))
            connection.executemany(
                """
                insert into rag_chunks (document_id, chunk_index, page_number, text)
                values (?, ?, ?, ?)
                """,
                [
                    (
                        document_id,
                        int(chunk["chunk_index"]),
                        chunk.get("page_number"),
                        str(chunk["text"]),
                    )
                    for chunk in chunks
                ],
            )
            connection.commit()

    def list_chunks(self, document_id: int) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                select id, document_id, chunk_index, page_number, text
                from rag_chunks
                where document_id = ?
                order by chunk_index
                """,
                (document_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_chunks_by_ids(self, chunk_ids: list[int]) -> list[dict[str, Any]]:
        if not chunk_ids:
            return []
        placeholders = ",".join("?" for _ in chunk_ids)
        with closing(self.connect()) as connection:
            rows = connection.execute(
                f"""
                select c.id, c.document_id, c.chunk_index, c.page_number, c.text,
                       d.title, d.original_name, d.category
                from rag_chunks c
                join rag_documents d on d.id = c.document_id
                where c.id in ({placeholders})
                """,
                tuple(chunk_ids),
            ).fetchall()
        by_id = {int(row["id"]): dict(row) for row in rows}
        return [by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in by_id]

    def search_chunks(self, owner_phone: str, question: str, limit: int = 5) -> list[dict[str, Any]]:
        terms = normalized_terms(question)
        if not terms:
            return []

        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                select c.id, c.document_id, c.chunk_index, c.page_number, c.text,
                       d.title, d.original_name, d.category
                from rag_chunks c
                join rag_documents d on d.id = c.document_id
                where d.owner_phone = ? and d.status = 'indexed'
                """,
                (owner_phone,),
            ).fetchall()

        scored: list[tuple[int, dict[str, Any]]] = []
        for row in rows:
            item = dict(row)
            haystack = " ".join(normalized_terms(str(item["text"])))
            score = sum(1 for term in terms if term in haystack)
            if score > 0:
                scored.append((score, item))

        scored.sort(key=lambda pair: (-pair[0], pair[1]["document_id"], pair[1]["chunk_index"]))
        return [item for _, item in scored[:limit]]

    def record_query(self, owner_phone: str, question: str, answer: str) -> int:
        with closing(self.connect()) as connection:
            cursor = connection.execute(
                """
                insert into rag_queries (owner_phone, question, answer)
                values (?, ?, ?)
                """,
                (owner_phone, question, answer),
            )
            connection.commit()
            return int(cursor.lastrowid)


def normalized_terms(value: str) -> list[str]:
    return [
        term.strip(".,:;!?()[]{}\"'").lower()
        for term in value.split()
        if len(term.strip(".,:;!?()[]{}\"'")) >= 3
    ]
