import os
import sys

# Insert src directory into path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
import io
import types

import pytest

# Stub boto3 and colorlog before importing aws/config
fake_boto3 = types.ModuleType("boto3")
fake_boto3.client = lambda *args, **kwargs: None  # type: ignore[attr-defined]
sys.modules["boto3"] = fake_boto3

fake_colorlog = types.ModuleType("colorlog")
fake_colorlog.ColoredFormatter = lambda *args, **kwargs: None  # type: ignore[attr-defined]
sys.modules["colorlog"] = fake_colorlog

from index_core import aws

# Use the same config module imported by aws
config = aws.config


class FakeCursor:
    def __init__(self):
        self.operations = []

    def execute(self, query, params=None):
        self.operations.append(("execute", query, params))

    def fetchall(self):
        return []

    def executemany(self, query, values):
        self.operations.append(("executemany", query, values))

    def close(self):
        self.operations.append(("close",))


class FakeDB:
    """Fake database connection that returns a single FakeCursor."""

    def __init__(self):
        self.cursor_obj = FakeCursor()

    def cursor(self):
        return self.cursor_obj


class FakePaginator:
    def __init__(self, pages):
        self.pages = pages

    def paginate(self, **kwargs):
        return self.pages


class FakeS3Client:
    def __init__(self, pages):
        self.pages = pages

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return FakePaginator(self.pages)


def test_get_s3_objects_empty_db(monkeypatch):
    """Test get_s3_objects retrieves pages when DB has no records."""
    fake_db = FakeDB()
    # Prepare fake S3 pages
    pages = [
        {
            "Contents": [
                {"Key": "test_dir/file1.png", "ETag": '"md5-1"'},
                {"Key": "test_dir/file2.jpg", "ETag": '"md5-2"'},
            ]
        }
    ]
    fake_s3 = FakeS3Client(pages)

    # Set a known AWS_S3_IMAGE_DIR
    monkeypatch.setattr(config, "AWS_S3_IMAGE_DIR", "test_dir/")

    result = aws.get_s3_objects(fake_db, "mybucket", fake_s3)
    # Expect mapping of keys to metadata
    expected = {
        "test_dir/file1.png": {"key": "test_dir/file1.png", "md5": "md5-1"},
        "test_dir/file2.jpg": {"key": "test_dir/file2.jpg", "md5": "md5-2"},
    }
    assert result == expected

    # Check that DB cursor executed SELECT and executemany for insertion
    ops = fake_db.cursor_obj.operations
    assert any(op[0] == "execute" and "SELECT path_key, md5 FROM s3objects" in op[1] for op in ops)
    insert_ops = [op for op in ops if op[0] == "executemany"]
    assert insert_ops, "Expected executemany insert operations"
    # Verify insert values match expected tuples
    _, _, values = insert_ops[0]
    expected_values = [
        ("test_dir/file1.pngmd5-1", "test_dir/file1.png", "md5-1"),
        ("test_dir/file2.jpgmd5-2", "test_dir/file2.jpg", "md5-2"),
    ]
    assert values == expected_values


class DummyS3Client:
    """Dummy S3 client to capture upload calls."""

    def __init__(self):
        self.calls = []

    def upload_fileobj(self, file_obj, bucket, key, ExtraArgs):
        self.calls.append(("upload_fileobj", file_obj, bucket, key, ExtraArgs))

    def upload_file(self, file_path, bucket, key, ExtraArgs):
        self.calls.append(("upload_file", file_path, bucket, key, ExtraArgs))


class ErrorS3Client:
    """S3 client that always raises on upload."""

    def upload_fileobj(self, *args, **kwargs):
        raise RuntimeError("upload_obj_fail")

    def upload_file(self, *args, **kwargs):
        raise RuntimeError("upload_fail")


def test_upload_file_to_s3_fileobj():
    """Test that upload_file_to_s3 uses upload_fileobj for file-like objects."""
    client = DummyS3Client()
    data = io.BytesIO(b"hello")
    aws.upload_file_to_s3(data, "bucket", "path/key.txt", client, content_type="text/plain")
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call[0] == "upload_fileobj"
    assert call[1] is data
    assert call[2:] == ("bucket", "path/key.txt", {"ContentType": "text/plain"})


def test_upload_file_to_s3_path():
    """Test that upload_file_to_s3 uses upload_file for file paths."""
    client = DummyS3Client()
    path = "/tmp/fake.txt"
    aws.upload_file_to_s3(path, "bucket", "remote/key", client)
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call[0] == "upload_file"
    assert call[1] == path
    assert call[2:] == ("bucket", "remote/key", {"ContentType": "binary/octet-stream"})


def test_upload_file_to_s3_error(monkeypatch):
    """Test that upload_file_to_s3 catches exceptions and does not raise."""
    client = ErrorS3Client()
    # Should not raise
    aws.upload_file_to_s3(io.BytesIO(b"x"), "b", "k", client)


def test_invalidate_with_retries_success(monkeypatch):
    """Test invalidation retries until success."""
    calls = {"count": 0}

    def fake_invalidate(files, dist_id):
        calls["count"] += 1
        if calls["count"] < 3:
            raise RuntimeError("fail")
        return {"Invalidation": "ok"}

    monkeypatch.setattr(aws, "invalidate_s3_files", fake_invalidate)
    # Speed up retries
    monkeypatch.setattr(aws.time, "sleep", lambda x: None)

    # Should succeed without exception
    aws.invalidate_with_retries("path", "dist")
    assert calls["count"] == 3


def test_invalidate_with_retries_max(monkeypatch):
    """Test invalidation stops after max retries."""
    calls = {"count": 0}

    def always_fail(files, dist_id):
        calls["count"] += 1
        raise RuntimeError("always_fail")

    monkeypatch.setattr(aws, "invalidate_s3_files", always_fail)
    monkeypatch.setattr(aws.time, "sleep", lambda x: None)

    # Should not raise even after max retries
    aws.invalidate_with_retries("path", "dist")
    # initial call + 5 retries = 6
    assert calls["count"] == 6
