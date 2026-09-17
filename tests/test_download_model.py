import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).parents[1] / "scripts/download-model.py"
SPEC = importlib.util.spec_from_file_location("download_model", SCRIPT)
assert SPEC and SPEC.loader
DOWNLOAD_MODEL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DOWNLOAD_MODEL)


class DownloadModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.output_dir = self.root / "models"
        self.output_dir.mkdir()
        self.file_spec = {
            "file": "shard.bin",
            "bytes": 5,
            "sha256": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_downloads_verifies_and_skips_existing_file(self) -> None:
        def fake_curl(command: list[str], **_: object) -> object:
            output = Path(command[command.index("--output") + 1])
            output.write_bytes(b"hello")
            return type("Result", (), {"returncode": 0})()

        with patch.object(DOWNLOAD_MODEL.subprocess, "run", side_effect=fake_curl) as run:
            DOWNLOAD_MODEL.download_file("https://example.test/resolve/rev", self.output_dir, self.file_spec)
            DOWNLOAD_MODEL.download_file("https://example.test/resolve/rev", self.output_dir, self.file_spec)

        final_path = self.output_dir / "shard.bin"
        self.assertEqual(final_path.read_bytes(), b"hello")
        self.assertFalse((self.output_dir / "shard.bin.part").exists())
        run.assert_called_once()
        command = run.call_args.args[0]
        self.assertIn("--continue-at", command)
        self.assertNotIn("--shell", command)

    def test_complete_partial_file_is_promoted_without_curl(self) -> None:
        (self.output_dir / "shard.bin.part").write_bytes(b"hello")
        with patch.object(DOWNLOAD_MODEL.subprocess, "run") as run:
            DOWNLOAD_MODEL.download_file("https://example.test/resolve/rev", self.output_dir, self.file_spec)
        run.assert_not_called()
        self.assertEqual((self.output_dir / "shard.bin").read_bytes(), b"hello")

    def test_existing_mismatch_is_not_overwritten(self) -> None:
        final_path = self.output_dir / "shard.bin"
        final_path.write_bytes(b"bad")
        with patch.object(DOWNLOAD_MODEL.subprocess, "run") as run, self.assertRaises(
            DOWNLOAD_MODEL.DownloadError
        ):
            DOWNLOAD_MODEL.download_file("https://example.test/resolve/rev", self.output_dir, self.file_spec)
        run.assert_not_called()
        self.assertEqual(final_path.read_bytes(), b"bad")

    def test_symlinked_parent_cannot_escape_output_directory(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        (self.output_dir / "nested").symlink_to(outside, target_is_directory=True)
        spec = {**self.file_spec, "file": "nested/shard.bin"}
        with patch.object(DOWNLOAD_MODEL.subprocess, "run") as run, self.assertRaises(
            DOWNLOAD_MODEL.DownloadError
        ):
            DOWNLOAD_MODEL.download_file("https://example.test/resolve/rev", self.output_dir, spec)
        run.assert_not_called()
        self.assertFalse((outside / "shard.bin").exists())

    def test_model_dir_precedence(self) -> None:
        with patch.dict(os.environ, {"MODEL_DIR": "/first", "NINFER_MODEL_DIR": "/second"}):
            self.assertEqual(DOWNLOAD_MODEL.output_directory(self.root), Path("/first"))
        with patch.dict(os.environ, {"MODEL_DIR": "", "NINFER_MODEL_DIR": "/second"}):
            self.assertEqual(DOWNLOAD_MODEL.output_directory(self.root), Path("/second"))

    def test_manifest_rejects_parent_component(self) -> None:
        manifest = self.root / "manifest.json"
        manifest.write_text(json.dumps({
            "name": "test",
            "format": "test",
            "repo": "owner/model",
            "revision": "rev",
            "files": [{**self.file_spec, "file": "../escape.bin"}],
        }), encoding="utf-8")
        with self.assertRaises(DOWNLOAD_MODEL.ManifestError):
            DOWNLOAD_MODEL.load_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
