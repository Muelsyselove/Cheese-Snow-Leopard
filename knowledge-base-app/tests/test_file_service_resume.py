"""FileService 幂等恢复单元测试

验证 _resume_from_stage / resume_interrupted 的恢复逻辑：
- completed/deleting 阶段跳过
- storing/failed 阶段先清理 PG chunk_index + Qdrant 半成品
- 从 MinIO 拉回原始文件后重跑 parse→embed→classify→store
- resume_interrupted 单文档失败不影响其他文档

mock 策略：所有外部依赖（parser/embedder/llm/pg/minio/qdrant/classify/compensation）
均用 MagicMock，验证调用次数与状态机流转。
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from services.file_service import FileService
from models.chunk import Chunk
from models.document import Document
from interfaces.embedder import EmbeddingResult
from interfaces.parser import ParsedDocument


# ========== 公共 fixture ==========

@pytest.fixture
def mocks():
    """构造所有依赖均为 MagicMock 的 FileService"""
    parser = MagicMock()
    embedder = MagicMock()
    embedder.encode = MagicMock(
        side_effect=lambda texts: [EmbeddingResult(dense=[0.1] * 8) for _ in texts]
    )
    llm = MagicMock()
    snowflake = MagicMock()
    snowflake.next_id = MagicMock(side_effect=iter(range(1000, 10000)))
    chunker = MagicMock()
    pg = MagicMock()
    minio = MagicMock()
    qdrant = MagicMock()
    classify = MagicMock()
    classify.classify = MagicMock(return_value=[])  # 无分类
    compensation = MagicMock()

    svc = FileService(
        parser=parser, embedder=embedder, llm=llm, snowflake=snowflake,
        chunker=chunker, pg_repo=pg, minio_repo=minio, qdrant_store=qdrant,
        classify_service=classify, compensation=compensation
    )
    return {
        "svc": svc, "parser": parser, "embedder": embedder, "llm": llm,
        "snowflake": snowflake, "chunker": chunker, "pg": pg, "minio": minio,
        "qdrant": qdrant, "classify": classify, "compensation": compensation,
    }


def _make_doc(doc_id=100, stage="storing", file_name="t.pdf",
              file_path="obj/100/t.pdf") -> Document:
    return Document(
        doc_id=doc_id, file_name=file_name, file_path=file_path,
        file_type="pdf", content_hash="abc", parse_status="failed",
        fail_stage=stage, fail_reason="prev error"
    )


def _make_parsed() -> ParsedDocument:
    """构造解析产物：1 个文本块"""
    chunk = Chunk(
        chunk_id=0, content_hash="", doc_id=0, doc_name="",
        content="测试内容", chunk_type="text",
        page_number=1, char_start=0, char_end=4
    )
    return ParsedDocument(chunks=[chunk], images=[])


def _setup_rerun_pipeline(mocks):
    """配置 mock 使重跑全流程成功：parser 返回 parsed，chunker 直通"""
    mocks["parser"].parse_document.return_value = _make_parsed()
    mocks["chunker"].split.side_effect = lambda parsed: list(parsed.chunks)
    # minio.download 写入本地文件
    def fake_download(obj_key, local_path):
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "w", encoding="utf-8") as f:
            f.write("fake file content")
        return local_path
    mocks["minio"].download.side_effect = fake_download


# ========== ① completed/deleting 跳过 ==========

class TestResumeSkipCompleted:
    def test_completed_stage_skipped(self, mocks):
        doc = _make_doc(stage="completed")
        mocks["svc"]._resume_from_stage(doc, "completed")
        # 不应清理、不应拉文件、不应重跑
        mocks["pg"].list_chunk_ids.assert_not_called()
        mocks["minio"].download.assert_not_called()
        mocks["parser"].parse_document.assert_not_called()

    def test_deleting_stage_skipped(self, mocks):
        doc = _make_doc(stage="deleting")
        mocks["svc"]._resume_from_stage(doc, "deleting")
        mocks["pg"].list_chunk_ids.assert_not_called()
        mocks["minio"].download.assert_not_called()


# ========== ② storing/failed 清理半成品 ==========

class TestResumeCleanup:
    def test_storing_cleans_pg_and_qdrant(self, mocks, tmp_path):
        _setup_rerun_pipeline(mocks)
        # PG 中有半成品 chunk
        mocks["pg"].list_chunk_ids.return_value = [1001, 1002]
        doc = _make_doc(stage="storing")

        mocks["svc"]._resume_from_stage(doc, "storing")

        # 清理调用：qdrant.delete + pg.delete_chunks_by_doc
        mocks["qdrant"].delete.assert_called_once()
        deleted_ids = mocks["qdrant"].delete.call_args.args[0]
        assert set(deleted_ids) == {"chunk_1001", "chunk_1002"}
        mocks["pg"].delete_chunks_by_doc.assert_called_once_with(100)

    def test_failed_stage_cleans_half_products(self, mocks):
        _setup_rerun_pipeline(mocks)
        mocks["pg"].list_chunk_ids.return_value = [1001]
        doc = _make_doc(stage="failed")

        mocks["svc"]._resume_from_stage(doc, "failed")

        mocks["qdrant"].delete.assert_called_once()
        mocks["pg"].delete_chunks_by_doc.assert_called_once_with(100)

    def test_qdrant_cleanup_failure_non_blocking(self, mocks):
        """Qdrant 清理失败不阻塞 PG 清理与重跑"""
        _setup_rerun_pipeline(mocks)
        mocks["pg"].list_chunk_ids.return_value = [1001]
        mocks["qdrant"].delete.side_effect = RuntimeError("qdrant down")
        doc = _make_doc(stage="storing")

        # 不应抛异常
        mocks["svc"]._resume_from_stage(doc, "storing")
        # PG 清理仍执行
        mocks["pg"].delete_chunks_by_doc.assert_called_once()
        # 重跑仍执行
        mocks["parser"].parse_document.assert_called_once()

    def test_no_chunks_no_cleanup(self, mocks):
        """PG 中无 chunk 时不调用清理"""
        _setup_rerun_pipeline(mocks)
        mocks["pg"].list_chunk_ids.return_value = []
        doc = _make_doc(stage="storing")

        mocks["svc"]._resume_from_stage(doc, "storing")
        mocks["qdrant"].delete.assert_not_called()
        mocks["pg"].delete_chunks_by_doc.assert_not_called()


# ========== ③ parsing/embedding/classifying 不清理直接重跑 ==========

class TestResumeNoCleanupStages:
    @pytest.mark.parametrize("stage", ["pending", "parsing", "embedding", "classifying"])
    def test_non_storing_stages_skip_cleanup(self, mocks, stage):
        _setup_rerun_pipeline(mocks)
        doc = _make_doc(stage=stage)

        mocks["svc"]._resume_from_stage(doc, stage)

        # 不清理
        mocks["pg"].list_chunk_ids.assert_not_called()
        mocks["qdrant"].delete.assert_not_called()
        # 但仍拉文件 + 重跑
        mocks["minio"].download.assert_called_once()
        mocks["parser"].parse_document.assert_called_once()


# ========== ④ 重跑全流程 ==========

class TestResumeRerunPipeline:
    def test_rerun_resets_status_to_parsing_first(self, mocks):
        _setup_rerun_pipeline(mocks)
        mocks["pg"].list_chunk_ids.return_value = []
        doc = _make_doc(stage="storing")

        mocks["svc"]._resume_from_stage(doc, "storing")

        # 第一次 update_parse_status 应为 parsing（重置）
        first_call = mocks["pg"].update_parse_status.call_args_list[0]
        assert first_call.args[0] == 100
        assert first_call.args[1] == "parsing"

    def test_rerun_success_marks_completed(self, mocks):
        _setup_rerun_pipeline(mocks)
        mocks["pg"].list_chunk_ids.return_value = []
        doc = _make_doc(stage="parsing")

        mocks["svc"]._resume_from_stage(doc, "parsing")

        # 最后一次状态应为 completed
        last_call = mocks["pg"].update_parse_status.call_args_list[-1]
        assert last_call.args == (100, "completed")

    def test_rerun_calls_full_pipeline(self, mocks):
        _setup_rerun_pipeline(mocks)
        mocks["pg"].list_chunk_ids.return_value = []
        doc = _make_doc(stage="parsing")

        mocks["svc"]._resume_from_stage(doc, "parsing")

        mocks["parser"].parse_document.assert_called_once()
        mocks["chunker"].split.assert_called_once()
        mocks["embedder"].encode.assert_called_once()
        mocks["classify"].classify.assert_called_once()
        mocks["pg"].insert_chunks.assert_called_once()
        mocks["qdrant"].upsert.assert_called_once()

    def test_rerun_reuses_original_doc_id(self, mocks):
        """重跑复用原 doc_id，不生成新 doc_id"""
        _setup_rerun_pipeline(mocks)
        mocks["pg"].list_chunk_ids.return_value = []
        doc = _make_doc(doc_id=999, stage="parsing")

        mocks["svc"]._resume_from_stage(doc, "parsing")

        # snowflake.next_id 用于 chunk_id，但不应有 insert_document
        mocks["pg"].insert_document.assert_not_called()
        # chunk 的 doc_id 应为 999
        insert_call = mocks["pg"].insert_chunks.call_args
        chunks_arg = insert_call.args[0]
        assert all(c.doc_id == 999 for c in chunks_arg)

    def test_rerun_failure_marks_failed_with_stage(self, mocks):
        """重跑失败应标记 failed + fail_stage"""
        _setup_rerun_pipeline(mocks)
        mocks["pg"].list_chunk_ids.return_value = []
        # 模拟 embedder 失败
        mocks["embedder"].encode.side_effect = RuntimeError("GPU OOM")
        # get_parse_status 返回当前阶段（embedding）
        mocks["pg"].get_parse_status.return_value = "embedding"
        doc = _make_doc(stage="parsing")

        with pytest.raises(RuntimeError, match="GPU OOM"):
            mocks["svc"]._resume_from_stage(doc, "parsing")

        # 最后一次 update 应为 failed + fail_stage（kwarg）
        last_call = mocks["pg"].update_parse_status.call_args_list[-1]
        assert last_call.args[0] == 100
        assert last_call.args[1] == "failed"
        assert last_call.kwargs.get("fail_stage") == "embedding"


# ========== ⑤ 临时文件清理 ==========

class TestResumeTempFileCleanup:
    def test_temp_file_removed_after_success(self, mocks, tmp_path):
        _setup_rerun_pipeline(mocks)
        mocks["pg"].list_chunk_ids.return_value = []
        doc = _make_doc(stage="parsing")

        captured_paths = []
        original_download = mocks["minio"].download.side_effect

        def tracking_download(obj_key, local_path):
            original_download(obj_key, local_path)
            captured_paths.append(local_path)
            return local_path
        mocks["minio"].download.side_effect = tracking_download

        mocks["svc"]._resume_from_stage(doc, "parsing")

        assert len(captured_paths) == 1
        assert not os.path.exists(captured_paths[0])

    def test_temp_file_removed_after_failure(self, mocks):
        _setup_rerun_pipeline(mocks)
        mocks["pg"].list_chunk_ids.return_value = []
        mocks["embedder"].encode.side_effect = RuntimeError("fail")
        mocks["pg"].get_parse_status.return_value = "embedding"
        doc = _make_doc(stage="parsing")

        captured_paths = []
        original_download = mocks["minio"].download.side_effect

        def tracking_download(obj_key, local_path):
            original_download(obj_key, local_path)
            captured_paths.append(local_path)
            return local_path
        mocks["minio"].download.side_effect = tracking_download

        with pytest.raises(RuntimeError):
            mocks["svc"]._resume_from_stage(doc, "parsing")

        # 即使失败也清理临时文件
        assert len(captured_paths) == 1
        assert not os.path.exists(captured_paths[0])


# ========== ⑥ resume_interrupted 异常隔离 ==========

class TestResumeInterruptedIsolation:
    def test_single_doc_failure_doesnt_block_others(self, mocks):
        _setup_rerun_pipeline(mocks)
        doc1 = _make_doc(doc_id=101, stage="parsing")
        doc2 = _make_doc(doc_id=102, stage="parsing")
        doc3 = _make_doc(doc_id=103, stage="parsing")

        # doc2 重跑失败
        def parse_side_effect(path):
            if "102" in str(path) or doc2.file_name in str(path):
                raise RuntimeError("doc2 parse fail")
            return _make_parsed()
        mocks["parser"].parse_document.side_effect = parse_side_effect
        mocks["pg"].list_by_status.return_value = [doc1, doc2, doc3]
        mocks["pg"].list_chunk_ids.return_value = []
        mocks["pg"].get_parse_status.return_value = "parsing"

        # 不应抛异常（单文档失败被隔离）
        mocks["svc"].resume_interrupted()

        # 三个文档都尝试了
        assert mocks["parser"].parse_document.call_count == 3
        # doc2 标记 failed
        failed_updates = [
            c for c in mocks["pg"].update_parse_status.call_args_list
            if len(c.args) >= 2 and c.args[1] == "failed"
        ]
        assert len(failed_updates) >= 1

    def test_resume_interrupted_iterates_all_pending(self, mocks):
        _setup_rerun_pipeline(mocks)
        docs = [_make_doc(doc_id=i, stage="parsing") for i in range(200, 203)]
        mocks["pg"].list_by_status.return_value = docs
        mocks["pg"].list_chunk_ids.return_value = []

        mocks["svc"].resume_interrupted()

        assert mocks["parser"].parse_document.call_count == 3

    def test_resume_interrupted_completed_doc_skipped(self, mocks):
        """completed 文档即使被列出也跳过"""
        _setup_rerun_pipeline(mocks)
        doc = _make_doc(stage="completed")
        mocks["pg"].list_by_status.return_value = [doc]

        mocks["svc"].resume_interrupted()

        mocks["parser"].parse_document.assert_not_called()
        mocks["minio"].download.assert_not_called()
