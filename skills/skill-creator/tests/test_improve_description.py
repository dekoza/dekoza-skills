import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import improve_description


class ExtractDescriptionTests(unittest.TestCase):
    def test_prefers_tagged_description(self) -> None:
        text = "before<new_description>Use this skill for Litestar work.</new_description>after"

        self.assertEqual(
            improve_description.extract_description(text),
            "Use this skill for Litestar work.",
        )

    def test_falls_back_to_plain_text(self) -> None:
        self.assertEqual(
            improve_description.extract_description('"Use this skill for HTMX work."'),
            "Use this skill for HTMX work.",
        )


class CallOpencodeTests(unittest.TestCase):
    @mock.patch("scripts.improve_description.subprocess.run")
    def test_call_opencode_uses_attached_file_and_model(
        self, mock_run: mock.Mock
    ) -> None:
        mock_run.return_value = mock.Mock(
            returncode=0,
            stdout=json.dumps({"type": "text", "part": {"text": "ok"}}),
            stderr="",
        )

        with tempfile.TemporaryDirectory() as tmp:
            prompt_file = Path(tmp) / "prompt.txt"
            result = improve_description._call_opencode(
                prompt="hello",
                model="provider/model",
                timeout=12,
                prompt_file=prompt_file,
            )

            self.assertEqual(result, "ok")
            self.assertEqual(prompt_file.read_text(), "hello")

        cmd = mock_run.call_args.kwargs["args"]
        self.assertEqual(
            cmd,
            [
                "opencode",
                "run",
                "Read the attached prompt file and follow it exactly.",
                "--format",
                "json",
                "--file",
                str(prompt_file),
                "--model",
                "provider/model",
            ],
        )


if __name__ == "__main__":
    unittest.main()
