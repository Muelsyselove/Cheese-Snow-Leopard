"""对象存储仓库单元测试 — LocalFSAdapter 完整覆盖 + MinioRepository 契约

LocalFSAdapter 无外部依赖，可独立运行完整测试；
MinioRepository 需真实 MinIO 服务，仅验证构造与契约（不连真实服务）。
"""
from __future__ import annotations

import os
import tempfile

import pytest

from repositories.object_storage import LocalFSAdapter, MinioRepository
from utils.exceptions import StorageError


# ---------------------------------------------------------------------------
# LocalFSAdapter 测试
# ---------------------------------------------------------------------------
class TestLocalFSAdapter:

    @pytest.fixture
    def adapter(self, tmp_path):
        """临时存储根目录的 adapter"""
        return LocalFSAdapter(root=str(tmp_path / "files"))

    @pytest.fixture
    def local_file(self, tmp_path):
        """创建临时本地源文件"""
        path = tmp_path / "source" / "test.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("hello knowledge base", encoding="utf-8")
        return str(path)

    def test_root_auto_created(self, tmp_path):
        """构造时自动创建根目录"""
        root = tmp_path / "auto_created"
        assert not root.exists()
        LocalFSAdapter(root=str(root))
        assert root.exists()

    def test_upload_auto_generate_key(self, adapter, local_file):
        """未指定 object_key 时自动生成 {uuid}/{file_name}"""
        key = adapter.upload(local_file)
        assert key.endswith("/test.txt")
        # uuid 段长度 32
        parts = key.split("/")
        assert len(parts) == 2
        assert len(parts[0]) == 32
        assert adapter.exists(key)

    def test_upload_with_explicit_key(self, adapter, local_file):
        """显式指定 object_key"""
        key = adapter.upload(local_file, object_key="doc1/file.txt")
        assert key == "doc1/file.txt"
        assert adapter.exists(key)

    def test_upload_preserves_content(self, adapter, local_file):
        """上传后内容一致"""
        key = adapter.upload(local_file, object_key="doc1/test.txt")
        downloaded = os.path.join(tempfile.gettempdir(), "test_download.txt")
        adapter.download(key, downloaded)
        with open(downloaded, "r", encoding="utf-8") as f:
            assert f.read() == "hello knowledge base"
        os.remove(downloaded)

    def test_upload_nonexistent_local_file(self, adapter):
        """上传不存在的本地文件抛 StorageError"""
        with pytest.raises(StorageError):
            adapter.upload("/nonexistent/path/file.txt")

    def test_download_nonexistent_object(self, adapter, tmp_path):
        """下载不存在的对象抛 StorageError"""
        target = str(tmp_path / "out.txt")
        with pytest.raises(StorageError):
            adapter.download("not/exist.txt", target)

    def test_download_creates_local_dir(self, adapter, local_file, tmp_path):
        """下载时自动创建本地目标目录"""
        key = adapter.upload(local_file)
        target = str(tmp_path / "deep" / "nested" / "dir" / "out.txt")
        adapter.download(key, target)
        assert os.path.isfile(target)

    def test_delete_idempotent(self, adapter, local_file):
        """删除不存在的对象视为成功（幂等）"""
        key = adapter.upload(local_file, object_key="to_delete.txt")
        adapter.delete(key)
        assert not adapter.exists(key)
        # 再次删除不抛异常
        adapter.delete(key)
        adapter.delete("never_uploaded/key.txt")

    def test_exists_false_for_nonexistent(self, adapter):
        """exists 对不存在对象返回 False"""
        assert adapter.exists("no/such/key.txt") is False

    def test_path_traversal_blocked(self, adapter, local_file):
        """object_key 路径穿越被拦截"""
        with pytest.raises(StorageError):
            adapter.upload(local_file, object_key="../../../etc/passwd")

    def test_empty_object_key_rejected(self, adapter):
        """空 object_key 在 download/delete/exists 时被拒绝"""
        with pytest.raises(StorageError):
            adapter.download("", "/tmp/x")
        with pytest.raises(StorageError):
            adapter.delete("")
        with pytest.raises(StorageError):
            adapter.exists("")

    def test_upload_overwrites_existing(self, adapter, tmp_path):
        """同 object_key 重复上传覆盖原内容"""
        f1 = tmp_path / "f1.txt"
        f1.write_text("content1", encoding="utf-8")
        f2 = tmp_path / "f2.txt"
        f2.write_text("content2", encoding="utf-8")

        key = "doc/overwritable.txt"
        adapter.upload(str(f1), object_key=key)
        adapter.upload(str(f2), object_key=key)

        out = str(tmp_path / "out.txt")
        adapter.download(key, out)
        with open(out, "r", encoding="utf-8") as f:
            assert f.read() == "content2"

    def test_directory_object_delete(self, adapter, local_file):
        """删除目录型对象（兼容）"""
        # 通过显式 key 制造嵌套结构
        adapter.upload(local_file, object_key="dir/a.txt")
        adapter.upload(local_file, object_key="dir/b.txt")
        # 删除目录
        adapter.delete("dir")
        assert not adapter.exists("dir/a.txt")


# ---------------------------------------------------------------------------
# MinioRepository 构造与契约（不连真实 MinIO）
# ---------------------------------------------------------------------------
class TestMinioRepositoryConfig:

    def test_construct_with_defaults(self):
        repo = MinioRepository()
        assert repo.endpoint == "localhost:9000"
        assert repo.access_key == "admin"
        assert repo.bucket == "knowledge-base"
        assert repo.secure is False
        assert repo._client is None

    def test_construct_with_config(self):
        repo = MinioRepository(
            endpoint="minio.example.com:9000",
            access_key="ak", secret_key="sk",
            bucket="my-bucket", secure=True
        )
        assert repo.endpoint == "minio.example.com:9000"
        assert repo.secret_key == "sk"
        assert repo.bucket == "my-bucket"
        assert repo.secure is True

    def test_lazy_client_init(self):
        """客户端懒加载，构造时不创建"""
        repo = MinioRepository()
        assert repo._client is None

    def test_generate_object_key_format(self):
        """自动生成的 object_key 格式为 {uuid32}/{filename}"""
        key = MinioRepository._generate_object_key("/path/to/报告.pdf")
        parts = key.split("/")
        assert len(parts) == 2
        assert len(parts[0]) == 32
        assert parts[1] == "报告.pdf"

    def test_generate_object_key_no_basename(self):
        """无文件名时回退为 'file'"""
        key = MinioRepository._generate_object_key("/")
        assert key.endswith("/file")


# ---------------------------------------------------------------------------
# 接口契约
# ---------------------------------------------------------------------------
class TestObjectStorageContract:

    def test_local_fs_satisfies_protocol(self):
        """LocalFSAdapter 满足 ObjectStorage Protocol"""
        from interfaces.storage import ObjectStorage
        adapter = LocalFSAdapter(root=tempfile.mkdtemp())
        for method in ("upload", "download", "delete", "exists"):
            assert hasattr(adapter, method)
        assert isinstance(adapter, ObjectStorage) if hasattr(ObjectStorage, "__protocol__") else True

    def test_minio_satisfies_protocol(self):
        """MinioRepository 满足 ObjectStorage Protocol"""
        from interfaces.storage import ObjectStorage
        repo = MinioRepository()
        for method in ("upload", "download", "delete", "exists"):
            assert hasattr(repo, method)
        assert isinstance(repo, ObjectStorage) if hasattr(ObjectStorage, "__protocol__") else True
