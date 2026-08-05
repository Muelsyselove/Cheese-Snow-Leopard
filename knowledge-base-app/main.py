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
    # 收集启动过程中的错误（非致命错误不阻塞 UI，由新 UI 玻璃对话框展示）
    startup_errors: list[str] = []

    # 1. 加载配置（keyring 占位符自动解析为真实凭据）
    config = None
    factory = None
    try:
        from config import load_config, ComponentFactory
        config = load_config("config.yaml")
        factory = ComponentFactory(config)
        logger.info(f"配置加载完成: VLM={config.vlm['provider']}, "
                    f"Embedding={config.embedding['provider']}")
    except Exception as e:
        startup_errors.append(f"配置加载失败: {e}")
        logger.error(f"配置加载失败: {e}", exc_info=True)

    # 1.5 计算设备选择（必须在任何 CUDA 上下文初始化之前执行：
    #     torch 的 import 本身安全，CUDA 上下文在首次调用时才创建）
    compute_device_desc = "cpu"
    if config is not None:
        try:
            from services.gpu_service import apply_compute_device
            compute_device_desc = apply_compute_device(
                (config.compute or {}).get("device", "auto"))
        except Exception as e:
            logger.warning(f"计算设备选择失败（按默认继续）: {e}")

    # 2. 创建组件实例（容错：任一失败不阻塞 UI）
    parser = embedder = llm = qdrant = snowflake = None
    if factory is not None:
        try:
            parser = factory.create_parser()
        except Exception as e:
            startup_errors.append(f"解析器创建失败: {e}")
            logger.error(f"解析器创建失败: {e}", exc_info=True)
        try:
            embedder = factory.create_embedder()
        except Exception as e:
            startup_errors.append(f"向量化器创建失败: {e}")
            logger.error(f"向量化器创建失败: {e}", exc_info=True)
        try:
            llm = factory.create_llm()
        except Exception as e:
            startup_errors.append(f"LLM 客户端创建失败: {e}")
            logger.error(f"LLM 客户端创建失败: {e}", exc_info=True)
        try:
            qdrant = factory.create_vector_store(
                sparse_support=embedder.supports_sparse if embedder else False
            )
        except Exception as e:
            startup_errors.append(f"向量存储创建失败: {e}")
            logger.error(f"向量存储创建失败: {e}", exc_info=True)
        try:
            snowflake = factory.create_snowflake()
        except Exception as e:
            startup_errors.append(f"ID 生成器创建失败: {e}")
            logger.error(f"ID 生成器创建失败: {e}", exc_info=True)
    if parser and embedder and llm and qdrant:
        logger.info("组件实例化完成")
    else:
        logger.warning(f"部分组件未就绪: parser={bool(parser)} embedder={bool(embedder)} "
                       f"llm={bool(llm)} qdrant={bool(qdrant)}")

    # 2.5 创建存储仓库（容错）
    pg_repo = minio_repo = None
    if config is not None:
        try:
            from repositories import PostgresRepository
            pg_cfg = config.storage.get("postgres", {})
            pg_repo = PostgresRepository(
                host=pg_cfg.get("host", "localhost"),
                port=pg_cfg.get("port", 5432),
                database=pg_cfg.get("database", "knowledge_base"),
                user=pg_cfg.get("user", "admin"),
                password=pg_cfg.get("password", "")
            )
        except Exception as e:
            startup_errors.append(f"PG 仓库创建失败: {e}")
            logger.error(f"PG 仓库创建失败: {e}", exc_info=True)
        try:
            minio_repo = factory.create_object_storage()
        except Exception as e:
            startup_errors.append(f"对象存储创建失败: {e}")
            logger.error(f"对象存储创建失败: {e}", exc_info=True)
        # 溯源服务注入 chunk 仓库（可选）
        if pg_repo is not None:
            try:
                from services.trace_service import set_chunk_repository
                set_chunk_repository(pg_repo)
            except Exception as e:
                logger.warning(f"溯源服务注入失败（非致命）: {e}")
        logger.info("存储仓库已创建")

    # 3. 组装业务服务（容错：依赖缺失时跳过）
    rag_service = classify_service = reconciler = lifecycle_service = None
    chunker = None
    if config is not None:
        try:
            from services.rag_service import RagService
            if embedder and llm and qdrant:
                rag_service = RagService(
                    embedder=embedder, llm=llm, qdrant_store=qdrant,
                    config=config.retrieval, category_repo=pg_repo
                )
        except Exception as e:
            startup_errors.append(f"RAG 服务创建失败: {e}")
            logger.error(f"RAG 服务创建失败: {e}", exc_info=True)
        try:
            from services.classify_service import ClassifyService
            if llm and pg_repo and snowflake:
                classify_service = ClassifyService(
                    llm=llm, category_repo=pg_repo, snowflake=snowflake
                )
            if classify_service is not None:
                try:
                    classify_service.ensure_preset_taxonomy()
                except Exception as e:
                    logger.warning(f"预置分类种子写入失败（非致命）: {e}")
        except Exception as e:
            startup_errors.append(f"分类服务创建失败: {e}")
            logger.error(f"分类服务创建失败: {e}", exc_info=True)
        try:
            from services.compensation import CompensationReconciler
            if pg_repo and qdrant and minio_repo:
                reconciler = CompensationReconciler(
                    pg_repo=pg_repo, qdrant_store=qdrant, minio_repo=minio_repo
                )
        except Exception as e:
            startup_errors.append(f"补偿服务创建失败: {e}")
            logger.error(f"补偿服务创建失败: {e}", exc_info=True)
        try:
            from services.lifecycle_service import LifecycleService
            if pg_repo and qdrant and minio_repo and reconciler and embedder:
                lifecycle_service = LifecycleService(
                    pg_repo=pg_repo, qdrant_store=qdrant, minio_repo=minio_repo,
                    compensation=reconciler, factory=factory, embedder=embedder
                )
        except Exception as e:
            startup_errors.append(f"生命周期服务创建失败: {e}")
            logger.error(f"生命周期服务创建失败: {e}", exc_info=True)
        try:
            if factory is not None:
                chunker = factory.create_chunker()
        except Exception as e:
            startup_errors.append(f"分块器创建失败: {e}")
            logger.error(f"分块器创建失败: {e}", exc_info=True)

    # 4. 创建文件服务（用于文件导入，需全依赖就绪）
    file_service = None
    if all([parser, embedder, llm, snowflake, chunker,
            pg_repo, minio_repo, qdrant, classify_service, reconciler]):
        try:
            from services.file_service import FileService
            file_service = FileService(
                parser=parser, embedder=embedder, llm=llm,
                snowflake=snowflake, chunker=chunker,
                pg_repo=pg_repo, minio_repo=minio_repo,
                qdrant_store=qdrant, classify_service=classify_service,
                compensation=reconciler
            )
            logger.info("文件服务已创建")
        except Exception as e:
            startup_errors.append(f"文件服务创建失败: {e}")
            logger.error(f"文件服务创建失败: {e}", exc_info=True)
    else:
        missing = []
        if parser is None: missing.append("parser")
        if embedder is None: missing.append("embedder")
        if llm is None: missing.append("llm")
        if snowflake is None: missing.append("snowflake")
        if chunker is None: missing.append("chunker")
        if pg_repo is None: missing.append("pg_repo")
        if minio_repo is None: missing.append("minio_repo")
        if qdrant is None: missing.append("qdrant")
        if classify_service is None: missing.append("classify_service")
        if reconciler is None: missing.append("reconciler")
        logger.warning(f"文件服务未就绪，缺失依赖: {', '.join(missing)}")

    # 5. 启动液态玻璃 UI（即使部分服务为 None 也能显示）
    from services.model_config_service import ModelConfigService
    from services.chat_store import ChatStore
    model_config_service = ModelConfigService()
    chat_store = ChatStore()

    # 6. 启动补偿队列 reconciler（后台线程，仅当就绪时）
    import threading
    if reconciler is not None:
        threading.Thread(target=reconciler.run_forever, daemon=True).start()
        logger.info("补偿队列 reconciler 已启动")

    # 7. 扫描 pending/failed 文档恢复执行（后台异步，仅当 file_service 就绪时）
    if file_service is not None:
        def _resume():
            try:
                file_service.resume_interrupted()
            except Exception as e:
                logger.error(f"恢复中断文档失败: {e}")
        threading.Thread(target=_resume, daemon=True).start()

    # 8. 后台预加载向量模型（避免首次导入时才下载/加载模型导致卡顿）
    if embedder is not None and hasattr(embedder, "preload"):
        def _preload_embedder():
            try:
                embedder.preload()
            except Exception as e:
                logger.error(f"向量模型预加载失败: {e}", exc_info=True)
        threading.Thread(target=_preload_embedder, daemon=True).start()

    # 9. 装配并运行 UI
    #    默认：Web 路线（ui_web/，pywebview + WebView2 内核，内置窗口非外部浏览器）
    #    回退：--ui=qml 启动 old_v2 QML UI（已弃用，不再受系统支持和更新）
    ui_mode = "web"
    for arg in sys.argv[1:]:
        if arg.startswith("--ui="):
            ui_mode = arg.split("=", 1)[1].strip().lower()

    if ui_mode == "qml":
        logger.info("UI 模式: old_v2 QML（已弃用）")
        from ui_old_v2.app import run_ui
        exit_code = run_ui(
            file_service=file_service, rag_service=rag_service,
            lifecycle_service=lifecycle_service,
            model_config_service=model_config_service, chat_store=chat_store,
            pg_repo=pg_repo,
            ui_config=config.ui if config else {},
            startup_errors=startup_errors,
        )
    else:
        logger.info("UI 模式: web（WebView2 内置内核）")
        from ui_web.app import run_web_ui
        exit_code = run_web_ui(
            file_service=file_service, rag_service=rag_service,
            lifecycle_service=lifecycle_service,
            model_config_service=model_config_service, chat_store=chat_store,
            pg_repo=pg_repo,
            startup_errors=startup_errors,
        )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
