from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Iterable

from fastapi import Depends, FastAPI, Header, HTTPException, Response


app = FastAPI(title="DocShare")


@dataclass(frozen=True)
class User:
    id: str
    name: str
    role: str


USERS = {
    "alice-key": User(id="u_alice", name="Alice", role="user"),
    "bob-key": User(id="u_bob", name="Bob", role="user"),
    "admin-key": User(id="u_admin", name="Admin", role="admin"),
}


DOCUMENTS = {
    "doc_public_handbook": {
        "id": "doc_public_handbook",
        "owner_id": "u_alice",
        "title": "Team Handbook",
        "visibility": "public",
        "tags": ["handbook", "team"],
        "archived": False,
        "body": "Welcome to the shared team handbook.",
    },
    "doc_alice_private": {
        "id": "doc_alice_private",
        "owner_id": "u_alice",
        "title": "Alice Client Notes",
        "visibility": "private",
        "tags": ["client", "acme"],
        "archived": False,
        "body": "ACME-PRIVATE-ALPHA: Alice private renewal notes.",
    },
    "doc_alice_archive": {
        "id": "doc_alice_archive",
        "owner_id": "u_alice",
        "title": "Alice Archived Contract",
        "visibility": "private",
        "tags": ["client", "archive"],
        "archived": True,
        "body": "ACME-PRIVATE-ARCHIVE: archived confidential contract.",
    },
    "doc_bob_private": {
        "id": "doc_bob_private",
        "owner_id": "u_bob",
        "title": "Bob Launch Plan",
        "visibility": "private",
        "tags": ["launch"],
        "archived": False,
        "body": "Bob private launch plan.",
    },
}


def current_user(x_api_key: Annotated[str | None, Header()] = None) -> User:
    if x_api_key not in USERS:
        raise HTTPException(status_code=401, detail="missing or invalid API key")
    return USERS[x_api_key]


def serialize_document(document: dict[str, object], include_body: bool = False) -> dict[str, object]:
    payload = {
        "id": document["id"],
        "owner_id": document["owner_id"],
        "title": document["title"],
        "visibility": document["visibility"],
        "tags": document["tags"],
        "archived": document["archived"],
    }
    if include_body:
        payload["body"] = document["body"]
    return payload


def can_read_document(user: User, document: dict[str, object]) -> bool:
    if user.role == "admin":
        return True
    if document["visibility"] == "public":
        return True
    if document["owner_id"] == user.id:
        return True
    return False


def require_document(document_id: str) -> dict[str, object]:
    try:
        return DOCUMENTS[document_id]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="document not found") from exc


def visible_documents_for(user: User, documents: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    return [document for document in documents if can_read_document(user, document)]


@app.get("/documents")
def list_documents(
    user: Annotated[User, Depends(current_user)],
    tag: str | None = None,
    include_archived: bool = False,
) -> dict[str, list[dict[str, object]]]:
    documents: Iterable[dict[str, object]] = DOCUMENTS.values()
    if tag:
        documents = [document for document in documents if tag in document["tags"]]
    if not include_archived:
        documents = [document for document in documents if not document["archived"]]

    # BUG: searches scoped by tag return every matching document before applying
    # ownership checks, leaking private metadata for guessed client tags.
    visible = list(documents) if tag else visible_documents_for(user, documents)
    return {"documents": [serialize_document(document) for document in visible]}


@app.get("/documents/export")
def export_documents(
    ids: str,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, list[dict[str, object]]]:
    requested = [require_document(document_id.strip()) for document_id in ids.split(",") if document_id.strip()]

    # BUG: export trusts the caller-provided ids and serializes private body text.
    return {"documents": [serialize_document(document, include_body=True) for document in requested]}


@app.get("/documents/{document_id}")
def get_document(
    document_id: str,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, object]:
    document = require_document(document_id)

    # BUG: private documents are returned by id to any authenticated user.
    if document["visibility"] != "private" and not can_read_document(user, document):
        raise HTTPException(status_code=403, detail="not allowed")
    return serialize_document(document, include_body=True)


@app.get("/documents/{document_id}/download")
def download_document(
    document_id: str,
    user: Annotated[User, Depends(current_user)],
) -> Response:
    document = require_document(document_id)

    # BUG: mirrors the detail endpoint and leaks private body bytes to non-owners.
    if document["visibility"] != "private" and not can_read_document(user, document):
        raise HTTPException(status_code=403, detail="not allowed")
    return Response(content=str(document["body"]), media_type="text/plain")


@app.post("/documents/{document_id}/share")
def create_share_link(
    document_id: str,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, object]:
    document = require_document(document_id)

    # BUG: any authenticated user can mint a share link for a guessed private doc.
    if document["visibility"] == "public" or document["owner_id"] == user.id or user.role == "admin":
        return {"document_id": document_id, "share_url": f"https://docshare.local/s/{document_id}"}
    return {"document_id": document_id, "share_url": f"https://docshare.local/s/{document_id}"}
