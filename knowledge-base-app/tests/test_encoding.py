"""编码服务单元测试 — Snowflake ID + SHA-256"""
from __future__ import annotations

from services.encoding import SnowflakeGenerator, content_hash


class TestSnowflakeGenerator:

    def test_unique_ids(self):
        """连续生成 1000 个 ID 应全部唯一"""
        gen = SnowflakeGenerator(worker_id=1)
        ids = [gen.next_id() for _ in range(1000)]
        assert len(set(ids)) == 1000

    def test_monotonic_increasing(self):
        """ID 应单调递增（同毫秒内序列号递增）"""
        gen = SnowflakeGenerator(worker_id=1)
        prev = gen.next_id()
        for _ in range(100):
            curr = gen.next_id()
            assert curr > prev
            prev = curr

    def test_invalid_worker_id(self):
        """worker_id 超范围应报错"""
        import pytest
        with pytest.raises(ValueError):
            SnowflakeGenerator(worker_id=1024)
        with pytest.raises(ValueError):
            SnowflakeGenerator(worker_id=-1)


class TestContentHash:

    def test_deterministic(self):
        """相同内容生成相同哈希"""
        assert content_hash("abc") == content_hash("abc")

    def test_different_content(self):
        """不同内容生成不同哈希"""
        assert content_hash("abc") != content_hash("abd")

    def test_length_64(self):
        """SHA-256 应为 64 位十六进制"""
        assert len(content_hash("test")) == 64
