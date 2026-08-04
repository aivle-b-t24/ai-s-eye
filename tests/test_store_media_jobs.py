from io import BytesIO

from fastapi.testclient import TestClient

from app.main import repository


def test_upload_media_and_create_analysis_job(client: TestClient) -> None:
    store = repository.create_store("업로드온보딩점")
    store_id = store.id
    try:
        upload = client.post(
            f"/api/stores/{store_id}/media",
            files={
                "file": ("clip.mp4", BytesIO(b"fake-mp4-bytes"), "video/mp4"),
            },
        )
        assert upload.status_code == 201
        media = upload.json()
        assert media["store_id"] == store_id
        assert media["media_type"] == "video"
        assert media["filename"] == "clip.mp4"

        listed = client.get(f"/api/stores/{store_id}/media")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        job_response = client.post(
            f"/api/stores/{store_id}/analysis-jobs",
            json={"media_id": media["id"]},
        )
        assert job_response.status_code == 201
        job = job_response.json()
        assert job["status"] == "queued"
        assert job["media_id"] == media["id"]

        claim = client.get(
            "/internal/analysis-jobs/next",
            params={"worker_id": "test-gpu"},
        )
        assert claim.status_code == 200
        body = claim.json()
        assert body["job"]["id"] == job["id"]
        assert body["job"]["status"] == "running"
        assert body["download_path"].endswith("/media")

        download = client.get(body["download_path"])
        assert download.status_code == 200
        assert download.content == b"fake-mp4-bytes"

        done = client.patch(
            f"/internal/analysis-jobs/{job['id']}",
            json={"status": "completed", "worker_id": "test-gpu"},
        )
        assert done.status_code == 200
        assert done.json()["status"] == "completed"
    finally:
        repository.delete_store(store_id)


def test_analysis_job_requires_media(client: TestClient) -> None:
    store = repository.create_store("미디어없는점")
    try:
        response = client.post(f"/api/stores/{store.id}/analysis-jobs", json={})
        assert response.status_code == 422
    finally:
        repository.delete_store(store.id)
