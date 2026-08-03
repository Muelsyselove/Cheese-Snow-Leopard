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

    # 3. 启动 PySide6 应用
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)

    # 4. 组装业务服务（TODO: 接入真实 pg_repo / minio_repo / chunker / classify）
    #    骨架阶段先留空，待存储层实现后注入
    from services.rag_service import RagService
    rag_service = RagService(
        embedder=embedder, llm=llm, qdrant_store=qdrant,
        config=config.retrieval
    )

    # 5. 启动主窗口
    from ui.main_window import MainWindow
    window = MainWindow(rag_service=rag_service, config=config.ui)
    window.show()
    logger.info("应用已启动")

    # 6. 启动补偿队列 reconciler（后台线程）
    # TODO: 接入真实 pg_repo 后启用
    # from services.compensation import CompensationReconciler
    # reconciler = CompensationReconciler(pg_repo, qdrant, minio_repo)
    # import threading
    # t = threading.Thread(target=reconciler.run_forever, daemon=True)
    # t.start()

    # 7. 扫描 pending/failed 文档恢复执行
    # TODO: file_service.resume_interrupted()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
