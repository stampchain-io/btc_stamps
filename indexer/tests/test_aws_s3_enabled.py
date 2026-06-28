"""Regression tests for issue #813 — keyless AWS auth via AWS_S3_ENABLED gate.

These tests verify that S3 storage is gated on *configured + intended* targets
(STORE_FILES + bucket + dir) rather than on the presence of AWS access keys, so
that instance/task-role (keyless) deployments using the boto3 default credential
chain still take the S3 upload path.

Test-pollution rules: `config` is resolved at call time via the `index_core.files`
module reference and patched with `monkeypatch.setattr`, so no stale module-level
imports are relied upon and no real I/O or network occurs.
"""

import io

from index_core import files


class TestStoreFilesS3EnabledGate:
    """store_files() should follow config.AWS_S3_ENABLED, not key presence."""

    def test_keyless_takes_async_s3_path(self, monkeypatch):
        """Keys absent but bucket/dir/STORE_FILES set -> async S3 upload path."""
        monkeypatch.setattr(files.config, "STORE_FILES", True)
        monkeypatch.setattr(files.config, "AWS_S3_ENABLED", True)
        monkeypatch.setattr(files.config, "USE_ASYNC_UPLOADS", True)
        # Keys intentionally absent — simulates instance/task-role deployment.
        monkeypatch.setattr(files.config, "AWS_ACCESS_KEY_ID", None)
        monkeypatch.setattr(files.config, "AWS_SECRET_ACCESS_KEY", None)

        async_upload = _mock(monkeypatch, "async_check_existing_and_upload_to_s3")
        sync_upload = _mock(monkeypatch, "check_existing_and_upload_to_s3")
        disk = _mock(monkeypatch, "store_files_to_disk")

        md5_hash, returned_filename = files.store_files(None, "test.txt", b"data", "text/plain")

        async_upload.assert_called_once()
        sync_upload.assert_not_called()
        disk.assert_not_called()

        # store_files returns the same (md5, filename) regardless of storage path.
        call_args = async_upload.call_args[0]
        assert call_args[0] == "test.txt"
        assert call_args[1] == "text/plain"
        assert isinstance(call_args[2], io.BytesIO)
        assert call_args[3] == md5_hash
        assert returned_filename == "test.txt"

    def test_keyless_takes_sync_s3_path(self, monkeypatch):
        """Keys absent, async disabled -> synchronous S3 upload path."""
        monkeypatch.setattr(files.config, "STORE_FILES", True)
        monkeypatch.setattr(files.config, "AWS_S3_ENABLED", True)
        monkeypatch.setattr(files.config, "USE_ASYNC_UPLOADS", False)
        monkeypatch.setattr(files.config, "AWS_ACCESS_KEY_ID", None)
        monkeypatch.setattr(files.config, "AWS_SECRET_ACCESS_KEY", None)

        async_upload = _mock(monkeypatch, "async_check_existing_and_upload_to_s3")
        sync_upload = _mock(monkeypatch, "check_existing_and_upload_to_s3")
        disk = _mock(monkeypatch, "store_files_to_disk")

        files.store_files(None, "test.txt", b"data", "text/plain")

        sync_upload.assert_called_once()
        async_upload.assert_not_called()
        disk.assert_not_called()

    def test_disabled_falls_back_to_disk(self, monkeypatch):
        """Bucket/dir not configured -> AWS_S3_ENABLED False -> disk fallback."""
        monkeypatch.setattr(files.config, "STORE_FILES", True)
        monkeypatch.setattr(files.config, "AWS_S3_ENABLED", False)
        monkeypatch.setattr(files.config, "USE_ASYNC_UPLOADS", True)

        async_upload = _mock(monkeypatch, "async_check_existing_and_upload_to_s3")
        sync_upload = _mock(monkeypatch, "check_existing_and_upload_to_s3")
        disk = _mock(monkeypatch, "store_files_to_disk")

        files.store_files(None, "test.txt", b"data", "text/plain")

        disk.assert_called_once_with("test.txt", b"data")
        async_upload.assert_not_called()
        sync_upload.assert_not_called()


class TestAwsS3EnabledFlag:
    """The derived AWS_S3_ENABLED flag = STORE_FILES and bucket and dir."""

    @staticmethod
    def _enabled(store_files, bucket, image_dir):
        return bool(store_files and bucket and image_dir)

    def test_true_regardless_of_keys(self):
        # bucket + dir + STORE_FILES set -> enabled, independent of credentials.
        assert self._enabled(True, "bucket", "images") is True

    def test_false_when_bucket_missing(self):
        assert self._enabled(True, None, "images") is False

    def test_false_when_dir_missing(self):
        assert self._enabled(True, "bucket", None) is False

    def test_false_when_store_files_off(self):
        assert self._enabled(False, "bucket", "images") is False


def _mock(monkeypatch, name):
    """Patch a name on the files module with a MagicMock and return it."""
    from unittest.mock import MagicMock

    m = MagicMock()
    monkeypatch.setattr(files, name, m)
    return m
