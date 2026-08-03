"""RebuildWorker 单元测试

验证四步重建流程（技术文档 11.3）：
① 统计总量  ② ensure_collection(新维度)  ③ 分批编码 + upsert  ④ 删除旧 collection

不依赖真实 PG / Qdrant / Embedder，全部用 mock。
需 QApplication 实例以支持 Signal 通信（worker 直接调用 _rebuild，同线程直连）。
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from workers.rebuild_worker import RebuildWorker
from models.chunk import Chunk
from interfaces.embedder import EmbeddingResult


# ========== 公共 fixture ==========

def _make_chunk(cid: int, content: str = "hello") -> Chunk:
    return Chunk(
        chunk_id=cid, content_hash=f"h{cid}", doc_id=100, doc_name="t.pdf",
        page_number=1, char_start=0, char_end=10, chunk_type="text",
        content=content, vector_id=f"v{cid}"
    )


@pytest.fixture
def mock_pg():
    return MagicMock()


@pytest.fixture
def mock_qdrant():
    q = MagicMock()
    q.collection = "text_chunks_new"  # 新 collection 名，与 old 不同
    q._get_client.return_value = MagicMock()
    return q


@pytest.fixture
def captured():
    """收集 progress / finished / error 信号参数"""
    return {"progress": [], "finished": [], "error": []}


def _make_worker(pg, embedder, qdrant, old_collection, batch_size, captured):
    """构造 worker 并连接信号到采集器"""
    w = RebuildWorker(
        pg_repo=pg, embedder=embedder, qdrant_store=qdrant,
        old_collection=old_collection, batch_size=batch_size
    )
    w.progress.connect(lambda p, m: captured["progress"].append((p, m)))
    w.finished.connect(lambda ok: captured["finished"].append(ok))
    w.error.connect(lambda m: captured["error"].append(m))
    return w


# ========== ① 缺失依赖校验 ==========

class TestRebuildValidation:
    def test_missing_deps_raises_value_error(self, qapp, captured):
        """pg/embedder/qdrant 任一为空应抛 ValueError"""
        w = RebuildWorker(pg_repo=None, embedder=None, qdrant_store=None)
        with pytest.raises(ValueError, match="不可为空"):
            w._rebuild()


# ========== ② 空库跳过 ==========

class TestRebuildEmpty:
    def test_skip_when_no_chunks(self, qapp, mock_pg, mock_qdrant, captured):
        """count_chunks=0 时跳过重建，进度直接 100"""
        mock_pg.count_chunks.return_value = 0
        embedder = MagicMock()
        embedder.dim = 1024
        w = _make_worker(mock_pg, embedder, mock_qdrant,
                         "old", 100, captured)
        w._rebuild()

        # 不应调用 ensure_collection / encode / upsert
        mock_qdrant.ensure_collection.assert_not_called()
        embedder.encode.assert_not_called()
        # 进度应包含跳过提示
        assert any("跳过" in m for _, m in captured["progress"])


# ========== ③ Happy Path（dim 属性提供）==========

class TestRebuildHappyPath:
    def test_full_rebuild_with_dim_attribute(self, qapp, mock_pg, mock_qdrant, captured):
        """完整流程：count → ensure_collection(1024) → 分批编码 → upsert → 删旧"""
        chunks = [_make_chunk(i, f"content_{i}") for i in range(1, 6)]  # 5 个块
        mock_pg.count_chunks.return_value = 5
        mock_pg.list_all_chunks.return_value = chunks

        embedder = MagicMock()
        embedder.dim = 1024
        # encode 按输入文本数返回等长结果
        embedder.encode = MagicMock(
            side_effect=lambda texts: [EmbeddingResult(dense=[0.1] * 1024) for _ in texts]
        )

        w = _make_worker(mock_pg, embedder, mock_qdrant,
                         old_collection="old_col", batch_size=2, captured=captured)
        w._rebuild()

        # ① ensure_collection 用 1024 维
        mock_qdrant.ensure_collection.assert_called_once_with(1024)
        # ② 5 块分 3 批（2,2,1），encode 调用 3 次
        assert embedder.encode.call_count == 3
        # ③ upsert 3 次
        assert mock_qdrant.upsert.call_count == 3
        # ④ 旧 collection 删除
        mock_qdrant._get_client.return_value.delete_collection.assert_called_once_with("old_col")
        # 进度最终 >= 95
        assert captured["progress"][-1][0] >= 95

    def test_batch_boundaries(self, qapp, mock_pg, mock_qdrant, captured):
        """batch_size=2 处理 5 块 → 3 批，每批大小 2/2/1"""
        chunks = [_make_chunk(i) for i in range(5)]
        mock_pg.count_chunks.return_value = 5
        mock_pg.list_all_chunks.return_value = chunks

        embedder = MagicMock()
        embedder.dim = 8
        embedder.encode = MagicMock(
            side_effect=lambda texts: [EmbeddingResult(dense=[0.1] * 8) for _ in texts]
        )

        w = _make_worker(mock_pg, embedder, mock_qdrant,
                         old_collection="", batch_size=2, captured=captured)
        w._rebuild()

        # 验证每批传入的块数
        batch_sizes = [len(call.args[0]) for call in mock_qdrant.upsert.call_args_list]
        assert batch_sizes == [2, 2, 1]


# ========== ④ 维度探测（无 dim 属性）==========

class TestRebuildDimProbe:
    def test_detect_dim_via_probe_encode(self, qapp, mock_pg, mock_qdrant, captured):
        """embedder 无 dim 属性时，通过探测编码获取维度"""
        chunks = [_make_chunk(1)]
        mock_pg.count_chunks.return_value = 1
        mock_pg.list_all_chunks.return_value = chunks

        embedder = MagicMock()
        embedder.dim = None  # 触发探测分支
        # 探测调用返回 512 维；正式批量调用返回 512 维
        embedder.encode = MagicMock(
            side_effect=lambda texts: [EmbeddingResult(dense=[0.1] * 512) for _ in texts]
        )

        w = _make_worker(mock_pg, embedder, mock_qdrant,
                         old_collection="old", batch_size=10, captured=captured)
        w._rebuild()

        # 第 1 次 encode 是探测（["维度探测"]），第 2 次是正式批量
        assert embedder.encode.call_count == 2
        assert embedder.encode.call_args_list[0].args[0] == ["维度探测"]
        # ensure_collection 用探测到的 512 维
        mock_qdrant.ensure_collection.assert_called_once_with(512)

    def test_probe_returns_empty_raises(self, qapp, mock_pg, mock_qdrant, captured):
        """探测编码返回空结果应抛 RuntimeError"""
        mock_pg.count_chunks.return_value = 1
        mock_pg.list_all_chunks.return_value = [_make_chunk(1)]

        embedder = MagicMock()
        embedder.dim = None
        embedder.encode = MagicMock(return_value=[])  # 探测返回空

        w = _make_worker(mock_pg, embedder, mock_qdrant,
                         old_collection="old", batch_size=10, captured=captured)
        with pytest.raises(RuntimeError, match="探测维度失败"):
            w._rebuild()


# ========== ⑤ 编码数量不匹配 ==========

class TestRebuildEncodingMismatch:
    def test_encoding_count_mismatch_raises(self, qapp, mock_pg, mock_qdrant, captured):
        """encode 返回数量与输入不匹配应抛 RuntimeError"""
        chunks = [_make_chunk(i) for i in range(3)]
        mock_pg.count_chunks.return_value = 3
        mock_pg.list_all_chunks.return_value = chunks

        embedder = MagicMock()
        embedder.dim = 4
        # 输入 3 条，仅返回 2 条
        embedder.encode = MagicMock(
            return_value=[EmbeddingResult(dense=[0.1] * 4) for _ in range(2)]
        )

        w = _make_worker(mock_pg, embedder, mock_qdrant,
                         old_collection="", batch_size=10, captured=captured)
        with pytest.raises(RuntimeError, match="编码数量不匹配"):
            w._rebuild()


# ========== ⑥ 旧 collection 删除策略 ==========

class TestRebuildOldCollectionDeletion:
    def test_same_collection_not_deleted(self, qapp, mock_pg, mock_qdrant, captured):
        """old_collection == 新 collection 时不删除"""
        chunks = [_make_chunk(1)]
        mock_pg.count_chunks.return_value = 1
        mock_pg.list_all_chunks.return_value = chunks

        embedder = MagicMock()
        embedder.dim = 4
        embedder.encode = MagicMock(
            side_effect=lambda texts: [EmbeddingResult(dense=[0.1] * 4) for _ in texts]
        )
        # old_collection 与 qdrant.collection 相同
        w = _make_worker(mock_pg, embedder, mock_qdrant,
                         old_collection=mock_qdrant.collection, batch_size=10,
                         captured=captured)
        w._rebuild()

        mock_qdrant._get_client.return_value.delete_collection.assert_not_called()

    def test_empty_old_collection_not_deleted(self, qapp, mock_pg, mock_qdrant, captured):
        """old_collection 为空字符串时不删除"""
        chunks = [_make_chunk(1)]
        mock_pg.count_chunks.return_value = 1
        mock_pg.list_all_chunks.return_value = chunks

        embedder = MagicMock()
        embedder.dim = 4
        embedder.encode = MagicMock(
            side_effect=lambda texts: [EmbeddingResult(dense=[0.1] * 4) for _ in texts]
        )
        w = _make_worker(mock_pg, embedder, mock_qdrant,
                         old_collection="", batch_size=10, captured=captured)
        w._rebuild()

        mock_qdrant._get_client.return_value.delete_collection.assert_not_called()

    def test_old_collection_delete_failure_non_blocking(self, qapp, mock_pg, mock_qdrant, captured):
        """旧 collection 删除失败不应阻塞重建成功"""
        chunks = [_make_chunk(1)]
        mock_pg.count_chunks.return_value = 1
        mock_pg.list_all_chunks.return_value = chunks

        embedder = MagicMock()
        embedder.dim = 4
        embedder.encode = MagicMock(
            side_effect=lambda texts: [EmbeddingResult(dense=[0.1] * 4) for _ in texts]
        )
        # 删除旧 collection 抛异常
        mock_qdrant._get_client.return_value.delete_collection.side_effect = RuntimeError("network")

        w = _make_worker(mock_pg, embedder, mock_qdrant,
                         old_collection="old_col", batch_size=10, captured=captured)
        # 不应抛异常（删除失败仅记日志）
        w._rebuild()
        # upsert 仍执行成功
        mock_qdrant.upsert.assert_called_once()


# ========== ⑦ run() 入口信号 ==========

class TestRebuildRunEntry:
    def test_run_success_emits_finished_true(self, qapp, mock_pg, mock_qdrant, captured):
        """run() 成功完成应 emit finished(True)"""
        chunks = [_make_chunk(1)]
        mock_pg.count_chunks.return_value = 1
        mock_pg.list_all_chunks.return_value = chunks

        embedder = MagicMock()
        embedder.dim = 4
        embedder.encode = MagicMock(
            side_effect=lambda texts: [EmbeddingResult(dense=[0.1] * 4) for _ in texts]
        )
        w = _make_worker(mock_pg, embedder, mock_qdrant,
                         old_collection="", batch_size=10, captured=captured)
        w.run()  # 同步执行（不调用 start，避免线程时序问题）

        assert captured["finished"] == [True]
        assert captured["error"] == []

    def test_run_failure_emits_error_and_finished_false(self, qapp, mock_pg, mock_qdrant, captured):
        """run() 异常应 emit error + finished(False)"""
        mock_pg.count_chunks.side_effect = RuntimeError("DB down")

        embedder = MagicMock()
        embedder.dim = 4
        w = _make_worker(mock_pg, embedder, mock_qdrant,
                         old_collection="", batch_size=10, captured=captured)
        w.run()

        assert captured["finished"] == [False]
        assert len(captured["error"]) == 1
        assert "DB down" in captured["error"][0]
