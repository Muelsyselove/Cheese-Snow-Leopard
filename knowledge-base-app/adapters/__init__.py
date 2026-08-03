"""接口实现层（可替换 adapter）。

每个 adapter 实现对应的 Protocol，通过 ComponentFactory 按配置动态实例化。
第三方库（paddleocr/mineru/FlagEmbedding/qdrant-client/openai）仅在 adapter 内 import。
"""
