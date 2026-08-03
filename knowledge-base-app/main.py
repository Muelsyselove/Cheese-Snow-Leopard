"""自主知识库桌面应用 — 应用入口

启动流程：
1. 加载 config.yaml（自动解析 keyring 凭据占位符）
2. 通过 ComponentFactory 创建各组件实例（按配置动态选择 adapter）
3. 组装业务服务（仅依赖 interfaces，不 import adapter）
4. 启动 PySide6 主窗口
5. 启动补偿队列 reconciler 后台线程
6. 扫描 pending/failed 文档恢复执行
"""
from __future__ import annotations

import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    # 1. 加载配置（keyring 占位符自动解析为真实凭据）
    from config import load_config, ComponentFactory
    config = load_config("config.yaml")
    factory = ComponentFactory(config)
    logger.info(f"配置加载完成: VLM={config.vlm['provider']}, "
                f"Embedding={config.embedding['provider']}")

    # 2. 创建组件实例（业务层仅依赖接口，不 import 任何 adapter）
    parser = factory.create_parser()        # → DocumentParser
    embedder = factory.create_embedder()    # → Embedder
    llm = factory.create_llm()              # → LLMClient
    qdrant = factory.create_vector_store(
        sparse_support=embedder.supports_sparse
    )
    snowflake = factory.create_snowflake()
    logger.info("组件实例化完成")

    # 2.5 创建存储仓库（PostgresRepository + 对象存储）
    from repositories import PostgresRepository
    pg_cfg = config.storage.get("postgres", {})
    pg_repo = PostgresRepository(
        host=pg_cfg.get("host", "localhost"),
        port=pg_cfg.get("port", 5432),
        database=pg_cfg.get("database", "knowledge_base"),
        user=pg_cfg.get("user", "admin"),
        password=pg_cfg.get("password", "")
    )
    minio_repo = factory.create_object_storage()
    # 溯源服务注入 chunk 仓库
    from services.trace_service import set_chunk_repository
    set_chunk_repository(pg_repo)
    logger.info("存储仓库已创建并注入溯源服务")

    # 3. 启动 PySide6 应用
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)

    # 4. 组装业务服务
    from services.rag_service import RagService
    from services.classify_service import ClassifyService
    from services.compensation import CompensationReconciler
    import services.lifecycle_service as lifecycle
    import services.file_service as file_svc

    rag_service = RagService(
        embedder=embedder, llm=llm, qdrant_store=qdrant,
        config=config.retrieval
    )
    classify_service = ClassifyService(
        llm=llm, category_repo=pg_repo, snowflake=snowflake
    )
    # 补偿 reconciler（注入 pg_repo / qdrant / minio_repo）
    reconciler = CompensationReconciler(
        pg=pg_repo, qdrant=qdrant, minio_repo=minio_repo
    )

    # 创建 chunker（结构感知分块）
    chunker = factory.create_chunker()

    # 5. 启动主窗口
    from ui.main_window import MainWindow
    window = MainWindow(rag_service=rag_service, config=config.ui)
    window.show()
    logger.info("应用已启动")

    # 6. 启动补偿队列 reconciler（后台线程）
    import threading
    t = threading.Thread(target=reconciler.run_forever, daemon=True)
    t.start()
    logger.info("补偿队列 reconciler 已启动")

    # 7. 扫描 pending/failed 文档恢复执行（后台异步）
    # 注：_resume_from_stage 当前为骨架，FileService 装配已就绪，
    #     待 _resume_from_stage 实现后即可启用完整恢复流程
    def _resume():
        try:
            file_service = file_svc.FileService(
                parser=parser, embedder=embedder, llm=llm,
                snowflake=snowflake, chunker=chunker,
                pg_repo=pg_repo, minio_repo=minio_repo,
                qdrant_store=qdrant, classify_service=classify_service,
                compensation=reconciler
            )
            file_service.resume_interrupted()
        except Exception as e:
            logger.error(f"恢复中断文档失败: {e}")
    threading.Thread(target=_resume, daemon=True).start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
