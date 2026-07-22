import asyncio
import unittest
from io import BytesIO

from fastapi.testclient import TestClient
from starlette.datastructures import Headers, UploadFile

from app.main import app
from app.services.upload_security import UploadValidationError, read_and_extract_upload, safe_display_filename


class ThirdWeekTests(unittest.TestCase):
    def _create_completed_run(self, client: TestClient) -> int:
        response = client.post(
            "/api/v1/runs",
            data={"question": "供应商收款后没有交货，应当承担什么责任？", "mode": "offline"},
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "queued")
        run_id = response.json()["run_id"]
        status = client.get(f"/api/v1/runs/{run_id}")
        self.assertEqual(status.json()["status"], "completed")
        return run_id

    def test_markdown_export(self) -> None:
        with TestClient(app) as client:
            run_id = self._create_completed_run(client)
            response = client.get(f"/api/v1/runs/{run_id}/export?format=markdown")
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/markdown", response.headers["content-type"])
            self.assertIn(f"legal-report-{run_id}.md", response.headers["content-disposition"])
            self.assertIn("法律分析报告", response.text)

    def test_pdf_export(self) -> None:
        with TestClient(app) as client:
            run_id = self._create_completed_run(client)
            response = client.get(f"/api/v1/runs/{run_id}/export?format=pdf")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-type"], "application/pdf")
            self.assertTrue(response.content.startswith(b"%PDF"))
            self.assertGreater(len(response.content), 1000)

    def test_export_rejects_unknown_format(self) -> None:
        with TestClient(app) as client:
            run_id = self._create_completed_run(client)
            response = client.get(f"/api/v1/runs/{run_id}/export?format=docx")
            self.assertEqual(response.status_code, 422)

    def test_upload_rejects_mime_spoofing(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/runs",
                data={"question": "请分析案件", "mode": "offline"},
                files={"file": ("case.pdf", b"plain text", "text/plain")},
            )
            self.assertEqual(response.status_code, 415)
            self.assertIn("MIME", response.json()["detail"])

    def test_request_id_is_returned(self) -> None:
        with TestClient(app) as client:
            response = client.get("/health", headers={"X-Request-ID": "test-request-123"})
            self.assertEqual(response.headers["X-Request-ID"], "test-request-123")

    def test_filename_is_sanitized(self) -> None:
        self.assertEqual(safe_display_filename("../../合同<>记录.txt"), "合同__记录.txt")
        self.assertEqual(safe_display_filename("C:\\secret\\case.pdf"), "case.pdf")

    def test_upload_size_limit_is_enforced_before_parsing(self) -> None:
        upload = UploadFile(
            file=BytesIO(b"12345"),
            filename="case.txt",
            headers=Headers({"content-type": "text/plain"}),
        )
        with self.assertRaises(UploadValidationError) as raised:
            asyncio.run(read_and_extract_upload(upload, max_bytes=4, timeout_seconds=1))
        self.assertEqual(raised.exception.status_code, 413)


if __name__ == "__main__":
    unittest.main()
