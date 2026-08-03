"""接口契约测试 — 验证所有 adapter 符合 Protocol 定义"""
from __future__ import annotations

import inspect


class TestEmbedderContract:
    """Embedder 接口契约"""

    def test_bge_m3_contract(self):
        from adapters.bge_embedder import BgeM3Embedder
        cls = BgeM3Embedder
        assert hasattr(cls, "encode")
        assert hasattr(cls, "encode_query")
        assert hasattr(cls, "supports_sparse")
        assert hasattr(cls, "supports_colbert")
        # 验证方法签名
        encode_sig = inspect.signature(cls.encode)
        assert "texts" in encode_sig.parameters

    def test_qwen3_contract(self):
        from adapters.qwen3_embedder import Qwen3Embedder
        cls = Qwen3Embedder
        assert hasattr(cls, "encode")
        assert hasattr(cls, "encode_query")
        assert hasattr(cls, "supports_sparse")
        assert hasattr(cls, "supports_colbert")


class TestParserContract:
    """DocumentParser 接口契约"""

    def test_paddleocr_vl_contract(self):
        from adapters.paddleocr_vl import PaddleOCRVLModel
        cls = PaddleOCRVLModel
        assert hasattr(cls, "parse_document")
        assert hasattr(cls, "understand_image")
        assert hasattr(cls, "requires_gpu")

    def test_mineru_contract(self):
        from adapters.mineru_vlm import MinerUModel
        cls = MinerUModel
        assert hasattr(cls, "parse_document")
        assert hasattr(cls, "understand_image")
        assert hasattr(cls, "requires_gpu")

    def test_minicpm_contract(self):
        from adapters.minicpm_vlm import MiniCPMVModel
        cls = MiniCPMVModel
        assert hasattr(cls, "parse_document")
        assert hasattr(cls, "understand_image")
        assert hasattr(cls, "requires_gpu")
