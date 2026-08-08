"""Architecture gate for production HF controller routing."""

from __future__ import annotations

from pathlib import Path
import unittest


BACKEND = Path(__file__).resolve().parent


class HFControllerArchitectureTests(unittest.TestCase):
    def test_no_direct_hf_api_transport_outside_oauth_browser_redirect(self):
        violations: list[str] = []
        for path in BACKEND.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if path == Path(__file__).resolve():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for line_no, line in enumerate(text.splitlines(), 1):
                if "hackforums.net/api/v2" not in line:
                    continue
                if path == BACKEND / "auth.py" and "RedirectResponse" in line:
                    continue
                violations.append(f"{path.relative_to(BACKEND)}:{line_no}")
        self.assertEqual([], violations, "Direct HF API endpoints found: " + ", ".join(violations))

    def test_hf_client_is_controller_adapter(self):
        source = (BACKEND / "HFClient.py").read_text(encoding="utf-8")
        self.assertIn("HF_CONTROL_PLANE_URL", source)
        self.assertIn("/internal/v1/request", source)
        self.assertNotIn("https://hackforums.net/api/v2/read", source)
        self.assertNotIn("https://hackforums.net/api/v2/write", source)


if __name__ == "__main__":
    unittest.main()
