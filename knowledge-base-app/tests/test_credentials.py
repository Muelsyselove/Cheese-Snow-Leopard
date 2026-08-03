"""凭据解析单元测试"""
from __future__ import annotations

from unittest.mock import patch

from utils.credentials import resolve_credential_placeholder


class TestCredentials:

    def test_keyring_placeholder_resolved(self):
        """keyring:xxx 占位符应被解析为真实值"""
        with patch("utils.credentials.get_credential", return_value="sk-real-key"):
            assert resolve_credential_placeholder("keyring:llm_api_key") == "sk-real-key"

    def test_non_placeholder_returned_as_is(self):
        """非占位符值原样返回"""
        assert resolve_credential_placeholder("plain_value") == "plain_value"
        assert resolve_credential_placeholder(123) == 123

    def test_missing_credential_raises(self):
        """未设置的凭据应抛出 ValueError"""
        with patch("utils.credentials.get_credential", return_value=None):
            import pytest
            with pytest.raises(ValueError, match="未在 keyring 中设置"):
                resolve_credential_placeholder("keyring:missing_key")
