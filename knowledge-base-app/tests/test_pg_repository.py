"""PostgresRepository 接口契约测试

沙箱无 PostgreSQL，用 mock cursor 验证：
- SQL 语句与参数正确生成
- 行映射到数据模型正确
- 方法签名与业务层调用一致

真实 PG 集成测试需在 CI 环境用 testcontainers/postgres 运行。
"""
import json
import pytest
from unittest.mock import MagicMock, patch

from repositories.postgres_repository import PostgresRepository
from models.chunk import Chunk
from models.document import Document
from models.category import Category, ChunkCategory
from models.compensation import CompensationTask


@pytest.fixture
def repo():
    """创建仓库实例，mock 内部连接"""
    r = PostgresRepository(host="localhost", database="test")
    r._conn = MagicMock()
    r._conn.closed = False
    return r


@pytest.fixture
def mock_cursor(repo):
    """mock cursor，返回预设结果"""
    cur = MagicMock()
    repo._conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    repo._conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return cur


# ========== document_index 测试 ==========

class TestDocumentOperations:
    def test_insert_document_generates_correct_sql(self, repo, mock_cursor):
        repo.insert_document(
            doc_id=1001, file_name="test.pdf", file_path="/data/test.pdf",
            file_type="pdf", content_hash="abc123", parse_status="parsing"
        )
        sql, params = mock_cursor.execute.call_args[0]
        assert "INSERT INTO document_index" in sql
        assert params == (1001, "test.pdf", "/data/test.pdf", "pdf", "abc123", None, "parsing")
        repo._conn.commit.assert_called_once()

    def test_update_parse_status_with_failure(self, repo, mock_cursor):
        repo.update_parse_status(1001, "failed", fail_stage="parse", fail_reason="OOM")
        sql, params = mock_cursor.execute.call_args[0]
        assert "UPDATE document_index" in sql
        assert "parse_status = %s" in sql
        assert params == ("failed", "parse", "OOM", 1001)

    def test_get_parse_status(self, repo, mock_cursor):
        mock_cursor.fetchone.return_value = ("parsing",)
        status = repo.get_parse_status(1001)
        assert status == "parsing"

    def test_get_parse_status_not_found(self, repo, mock_cursor):
        mock_cursor.fetchone.return_value = None
        assert repo.get_parse_status(9999) is None

    def test_get_document_maps_to_model(self, repo, mock_cursor):
        mock_cursor.fetchone.return_value = (
            1001, "test.pdf", "/data/test.pdf", "pdf", "abc123",
            10, "2025-01-01", "completed", None, None
        )
        doc = repo.get_document(1001)
        assert isinstance(doc, Document)
        assert doc.doc_id == 1001
        assert doc.file_name == "test.pdf"
        assert doc.parse_status == "completed"

    def test_list_by_status(self, repo, mock_cursor):
        mock_cursor.fetchall.return_value = [
            (1001, "a.pdf", "/a", "pdf", "h1", 5, "t1", "parsing", None, None),
            (1002, "b.pdf", "/b", "pdf", "h2", 3, "t2", "failed", "parse", "OOM"),
        ]
        docs = repo.list_by_status(["parsing", "failed"])
        assert len(docs) == 2
        assert docs[0].doc_id == 1001
        assert docs[1].fail_stage == "parse"

    def test_delete_document(self, repo, mock_cursor):
        repo.delete_document(1001)
        sql, params = mock_cursor.execute.call_args[0]
        assert "DELETE FROM document_index" in sql
        assert params == (1001,)


# ========== chunk_index 测试 ==========

class TestChunkOperations:
    def test_insert_chunks_with_dedup(self, repo, mock_cursor):
        chunks = [
            Chunk(chunk_id=1, content_hash="h1", doc_id=100, doc_name="t.pdf",
                  page_number=1, char_start=0, char_end=100, chunk_type="text",
                  content="hello", vector_id="v1"),
            Chunk(chunk_id=2, content_hash="h2", doc_id=100, doc_name="t.pdf",
                  page_number=1, char_start=100, char_end=200, chunk_type="table",
                  content="data", vector_id="v2"),
        ]
        classifications = [
            [ChunkCategory(chunk_id=1, category_id=10, confidence=0.9)],
            [],
        ]
        repo.insert_chunks(chunks, classifications)
        # 应执行 2 次插入 chunk + 1 次插入 category = 3 次 execute
        assert mock_cursor.execute.call_count == 3
        # 验证 chunk 插入用 ON CONFLICT 去重
        first_sql = mock_cursor.execute.call_args_list[0][0][0]
        assert "ON CONFLICT (content_hash, doc_id) DO NOTHING" in first_sql

    def test_insert_chunks_with_bbox_json(self, repo, mock_cursor):
        chunk = Chunk(chunk_id=1, content_hash="h1", doc_id=100, doc_name="t.pdf",
                      page_number=1, bbox=[10, 20, 100, 50], chunk_type="image",
                      content="img desc", vector_id="v1")
        repo.insert_chunks([chunk], [[]])
        params = mock_cursor.execute.call_args_list[0][0][1]
        # bbox 应序列化为 JSON 字符串
        assert json.loads(params[7]) == [10, 20, 100, 50]

    def test_get_chunk_maps_to_model(self, repo, mock_cursor):
        mock_cursor.fetchone.return_value = (
            1, "h1", 100, "t.pdf", 1, 0, 100,
            json.dumps([10, 20, 100, 50]), "text", "hello", "v1"
        )
        chunk = repo.get_chunk(1)
        assert isinstance(chunk, Chunk)
        assert chunk.chunk_id == 1
        assert chunk.bbox == [10, 20, 100, 50]

    def test_list_chunk_ids(self, repo, mock_cursor):
        mock_cursor.fetchall.return_value = [(1,), (2,), (3,)]
        ids = repo.list_chunk_ids(100)
        assert ids == [1, 2, 3]

    def test_delete_chunks_cascades_category(self, repo, mock_cursor):
        repo.delete_chunks_by_doc(100)
        # 应执行 2 次：先删 chunk_category，再删 chunk_index
        assert mock_cursor.execute.call_count == 2
        first_sql = mock_cursor.execute.call_args_list[0][0][0]
        assert "DELETE FROM chunk_category" in first_sql
        second_sql = mock_cursor.execute.call_args_list[1][0][0]
        assert "DELETE FROM chunk_index WHERE doc_id" in second_sql


# ========== category 测试 ==========

class TestCategoryOperations:
    def test_list_all_categories(self, repo, mock_cursor):
        mock_cursor.fetchall.return_value = [
            (10, "技术", None, "技术类", 5),
            (20, "法律", None, "法律类", 3),
        ]
        cats = repo.list_all_categories()
        assert len(cats) == 2
        assert isinstance(cats[0], Category)
        assert cats[0].name == "技术"
        assert cats[0].chunk_count == 5

    def test_upsert_chunk_categories(self, repo, mock_cursor):
        repo.upsert_chunk_categories(chunk_id=1, category_ids=[10, 20])
        # 先删后插：1 次删除 + 2 次插入 = 3 次
        assert mock_cursor.execute.call_count == 3
        first_sql = mock_cursor.execute.call_args_list[0][0][0]
        assert "DELETE FROM chunk_category WHERE chunk_id" in first_sql

    def test_get_category_names(self, repo, mock_cursor):
        mock_cursor.fetchall.return_value = [("技术",), ("法律",)]
        names = repo.get_category_names(1)
        assert names == ["技术", "法律"]


# ========== compensation_queue 测试 ==========

class TestCompensationOperations:
    def test_enqueue_returns_id(self, repo, mock_cursor):
        mock_cursor.fetchone.return_value = (42,)
        task_id = repo.enqueue_compensation("delete_pg_chunks", "100")
        assert task_id == 42
        sql, params = mock_cursor.execute.call_args[0]
        assert "INSERT INTO compensation_queue" in sql
        assert "RETURNING id" in sql
        # status/retries 用字面量 DEFAULT，params 仅含 op_type + target_id
        assert params == ("delete_pg_chunks", "100")

    def test_list_pending_compensations(self, repo, mock_cursor):
        mock_cursor.fetchall.return_value = [
            (1, "delete_pg_chunks", "100", "pending", 0, "t1", "t2"),
            (2, "delete_pg_doc", "200", "pending", 1, "t3", "t4"),
        ]
        tasks = repo.list_pending_compensations()
        assert len(tasks) == 2
        assert isinstance(tasks[0], CompensationTask)
        assert tasks[0].op_type == "delete_pg_chunks"
        assert tasks[1].retries == 1

    def test_mark_compensation_done(self, repo, mock_cursor):
        repo.mark_compensation_done(42)
        sql, params = mock_cursor.execute.call_args[0]
        assert "status = 'done'" in sql
        assert params == (42,)

    def test_mark_compensation_failed(self, repo, mock_cursor):
        repo.mark_compensation_failed(42, "connection lost")
        sql, params = mock_cursor.execute.call_args[0]
        assert "status = 'failed'" in sql
        assert params == ("connection lost", 42)

    def test_update_compensation_retries(self, repo, mock_cursor):
        repo.update_compensation_retries(42, 3)
        sql, params = mock_cursor.execute.call_args[0]
        assert "retries = %s" in sql
        assert params == (3, 42)


# ========== 事务与错误处理 ==========

class TestTransactionHandling:
    def test_rollback_on_error(self, repo, mock_cursor):
        mock_cursor.execute.side_effect = Exception("DB error")
        with pytest.raises(Exception, match="DB error"):
            repo.insert_document(1, "f", "p", "pdf", "h")
        repo._conn.rollback.assert_called_once()
        repo._conn.commit.assert_not_called()

    def test_execute_commit_on_success(self, repo, mock_cursor):
        repo.get_parse_status(1)
        repo._conn.commit.assert_called_once()
