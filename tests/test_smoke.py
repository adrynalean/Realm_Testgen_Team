from fastapi.testclient import TestClient

from docshare.app import app


client = TestClient(app)


def headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def test_public_document_is_visible_to_regular_users():
    response = client.get("/documents/doc_public_handbook", headers=headers("bob-key"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "doc_public_handbook"
    assert payload["visibility"] == "public"
    assert "shared team handbook" in payload["body"]


def test_owner_can_read_and_download_their_private_document():
    detail = client.get("/documents/doc_alice_private", headers=headers("alice-key"))
    download = client.get("/documents/doc_alice_private/download", headers=headers("alice-key"))

    assert detail.status_code == 200
    assert detail.json()["owner_id"] == "u_alice"
    assert download.status_code == 200
    assert "Alice private renewal notes" in download.text


def test_owner_can_share_their_private_document():
    response = client.post("/documents/doc_alice_private/share", headers=headers("alice-key"))

    assert response.status_code == 200
    assert response.json()["share_url"].endswith("/doc_alice_private")


def test_admin_can_list_and_export_private_documents():
    listing = client.get("/documents", headers=headers("admin-key"))
    export = client.get(
        "/documents/export",
        params={"ids": "doc_alice_private,doc_bob_private"},
        headers=headers("admin-key"),
    )

    assert listing.status_code == 200
    listed_ids = {document["id"] for document in listing.json()["documents"]}
    assert {"doc_alice_private", "doc_bob_private"}.issubset(listed_ids)

    assert export.status_code == 200
    exported_ids = {document["id"] for document in export.json()["documents"]}
    assert exported_ids == {"doc_alice_private", "doc_bob_private"}


def test_unauthenticated_requests_are_rejected():
    response = client.get("/documents")

    assert response.status_code == 401
