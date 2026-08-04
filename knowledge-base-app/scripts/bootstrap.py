#!/usr/bin/env python
"""一键部署引导脚本 — 从零开始自动部署全部依赖服务

职责（按顺序）：
1. 自动发现 PostgreSQL / Qdrant / MinIO 安装路径（向上查找父目录）
2. 启动 PostgreSQL（未运行则 pg_ctl start，未初始化则 initdb）
3. 创建 admin 用户 + knowledge_base 数据库（不存在则创建）
4. 凭据写入 keyring（PG/MinIO 密码）
5. 初始化数据库表结构（init_db.SCHEMA_SQL）
6. 启动 Qdrant（未运行则后台启动 qdrant.exe）
7. 下载并启动 MinIO（未部署则自动下载 minio.exe）
8. 检测 LLM API Key（未配置则提示用户去设置页面）
9. 路径回写 config.yaml（services 段）

用法：
    python -m scripts.bootstrap           # 完整引导
    python -m scripts.bootstrap --check   # 仅检测状态不启动
"""
from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import time
import secrets
import string

# 添加项目根到 path（与 init_db.py 同样的手法）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] bootstrap: %(message)s"
)
logger = logging.getLogger(__name__)

# ============================================================
# 常量
# ============================================================
APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 默认服务目录名（在 APP_ROOT 的父目录下查找）
PG_DIR_NAME = "PostgreSQL16"
QDRANT_DIR_NAME = "Qdrant"
MINIO_DIR_NAME = "MinIO"

# MinIO 下载地址（官方 dl.min.io 会 302 重定向到 GitHub Releases，国内访问不稳定）
MINIO_DOWNLOAD_URL = "https://dl.min.io/server/minio/release/windows-amd64/minio.exe"
# GitHub 加速镜像前缀（直接拼接 GitHub URL 前；空字符串表示直连 GitHub）
# 顺序即优先级，第一个能下载成功的就停止
GITHUB_MIRROR_PREFIXES = [
    "https://ghfast.top/",
    "https://gh-proxy.com/",
    "https://mirror.ghproxy.com/",
    "",  # 直连 GitHub（国内通常失败，作为兜底）
]
MINIO_CLIENT_URL = "https://dl.min.io/client/mc/release/windows-amd64/mc.exe"

# 默认端口
PG_PORT = 5432
QDRANT_PORT = 6333
MINIO_PORT = 9000

# 数据库配置
PG_DB = "knowledge_base"
PG_USER = "admin"
PG_SUPER_USER = "postgres"  # initdb 创建的超级用户


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """检测端口是否可连"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ConnectionRefusedError):
        return False


def _wait_for_port(host: str, port: int, timeout: int = 30, interval: float = 1.0) -> bool:
    """等待端口可连，超时返回 False"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_open(host, port):
            return True
        time.sleep(interval)
    return False


def _gen_password(length: int) -> str:
    """生成随机密码（字母+数字）"""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _find_parent_dir(dir_name: str) -> str | None:
    """在 APP_ROOT 的父目录中查找指定名称的目录

    查找范围：APP_ROOT 向上 3 层父目录及其直接子目录
    """
    current = APP_ROOT
    for _ in range(4):
        parent = os.path.dirname(current)
        if not parent or parent == current:
            break
        # 检查父目录下是否有目标目录
        candidate = os.path.join(parent, dir_name)
        if os.path.isdir(candidate):
            return candidate
        current = parent
    return None


# ============================================================
# 主引导类
# ============================================================
class Bootstrap:

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = os.path.join(APP_ROOT, config_path)
        self.config: dict = {}
        self.services: dict = {}  # discovered service paths

    # ---------------------- 主流程 ----------------------
    def run(self) -> bool:
        """执行完整引导流程，返回是否全部成功"""
        logger.info("=" * 60)
        logger.info("开始一键部署引导")
        logger.info("=" * 60)

        ok = True
        ok &= self._load_config()
        ok &= self._discover_services()

        # PG 是核心依赖，失败则中止
        if not self.ensure_postgresql():
            logger.error("PostgreSQL 启动失败，中止引导")
            return False
        self.ensure_credentials()
        self.init_database()

        # Qdrant 是核心依赖
        if not self.ensure_qdrant():
            logger.error("Qdrant 启动失败，中止引导")
            return False

        # MinIO 可选，失败回退 LocalFS
        self.ensure_minio()

        # LLM API Key 检测
        self.check_llm_key()

        # 回写 config.yaml
        self._update_config()

        logger.info("=" * 60)
        logger.info("一键部署引导完成")
        logger.info("=" * 60)
        return ok

    # ---------------------- 配置加载 ----------------------
    def _load_config(self) -> bool:
        """加载 config.yaml"""
        try:
            import yaml
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f) or {}
            logger.info(f"配置已加载: {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"配置加载失败: {e}")
            self.config = {}
            return False

    # ---------------------- 服务发现 ----------------------
    def _discover_services(self) -> bool:
        """自动发现 PG/Qdrant/MinIO 安装路径"""
        services = self.config.get("services", {})

        # PostgreSQL
        pg_home = services.get("postgresql", {}).get("home")
        if not pg_home:
            pg_home = _find_parent_dir(PG_DIR_NAME)
        if pg_home and os.path.isfile(os.path.join(pg_home, "bin", "pg_ctl.exe")):
            self.services["postgresql"] = pg_home
            logger.info(f"[发现] PostgreSQL: {pg_home}")
        else:
            logger.warning(f"[未发现] PostgreSQL（在父目录查找 {PG_DIR_NAME}/ 失败）")

        # Qdrant
        qdrant_home = services.get("qdrant", {}).get("home")
        if not qdrant_home:
            qdrant_home = _find_parent_dir(QDRANT_DIR_NAME)
        if qdrant_home and os.path.isfile(os.path.join(qdrant_home, "qdrant.exe")):
            self.services["qdrant"] = qdrant_home
            logger.info(f"[发现] Qdrant: {qdrant_home}")
        else:
            logger.warning(f"[未发现] Qdrant（在父目录查找 {QDRANT_DIR_NAME}/ 失败）")

        # MinIO（可能未部署，后面 ensure_minio 会下载）
        minio_home = services.get("minio", {}).get("home")
        if not minio_home:
            minio_home = _find_parent_dir(MINIO_DIR_NAME)
        # MinIO 可执行文件必须存在且 >1MB（避免不完整下载被误识别）
        minio_exe_found = False
        if minio_home:
            for rel in ("bin/minio.exe", "minio.exe"):
                p = os.path.join(minio_home, *rel.split("/"))
                if os.path.isfile(p) and os.path.getsize(p) > 1024 * 1024:
                    minio_exe_found = True
                    break
        if minio_home and minio_exe_found:
            self.services["minio"] = minio_home
            logger.info(f"[发现] MinIO: {minio_home}")
        else:
            logger.info(f"[未发现] MinIO（将在后续步骤自动下载）")

        return True

    # ---------------------- PostgreSQL ----------------------
    def ensure_postgresql(self) -> bool:
        """确保 PostgreSQL 运行：检测端口 → pg_ctl status → pg_ctl start → 等待就绪"""
        pg_home = self.services.get("postgresql")
        if not pg_home:
            logger.error("PostgreSQL 未找到，请手动安装到项目父目录")
            logger.error(f"下载: https://www.enterprisedb.com/download-postgresql-binaries")
            return False

        pg_bin = os.path.join(pg_home, "bin")
        pg_data = os.path.join(pg_home, "data")
        pg_log = os.path.join(pg_home, "pg.log")
        pg_ctl = os.path.join(pg_bin, "pg_ctl.exe")
        initdb = os.path.join(pg_bin, "initdb.exe")

        # 1. 检测是否已运行（含重试，避免 PG 正在恢复中误判）
        if _wait_for_port("localhost", PG_PORT, timeout=5, interval=1.0):
            logger.info("[PostgreSQL] 已在运行")
            self._ensure_pg_user_and_db()
            return True

        # 2. 检测 data 目录是否已初始化
        if not os.path.isfile(os.path.join(pg_data, "PG_VERSION")):
            logger.info("[PostgreSQL] data 目录未初始化，执行 initdb ...")
            ret = subprocess.run(
                [initdb, "-D", pg_data, "-U", PG_SUPER_USER, "--auth=trust", "--encoding=UTF8"],
                capture_output=True, text=True, cwd=pg_home
            )
            if ret.returncode != 0:
                logger.error(f"[PostgreSQL] initdb 失败:\n{ret.stderr}")
                return False
            # 写入最小 pg_hba.conf（trust 模式，本地免密）
            with open(os.path.join(pg_data, "pg_hba.conf"), "w", encoding="utf-8") as f:
                f.write("host all all 127.0.0.1/32 trust\n")
                f.write("host all all ::1/128 trust\n")
                f.write("local all all trust\n")
            logger.info("[PostgreSQL] initdb 完成")

        # 3. 检查 pg_ctl status（区分"未运行"和"已在运行但端口未就绪"）
        ret = subprocess.run(
            [pg_ctl, "status", "-D", pg_data],
            capture_output=True, text=True, cwd=pg_home
        )
        if ret.returncode == 0:
            # PG 进程存在但端口未就绪，等待恢复完成
            logger.info("[PostgreSQL] 进程存在，等待端口就绪 ...")
            if _wait_for_port("localhost", PG_PORT, timeout=30):
                logger.info("[PostgreSQL] 服务已就绪")
                self._ensure_pg_user_and_db()
                return True
            logger.error("[PostgreSQL] 进程存在但端口 5432 长时间不可连")
            return False

        # 4. PG 未运行，执行启动
        logger.info("[PostgreSQL] 启动服务 ...")
        # 清理可能残留的 postmaster.pid
        pid_file = os.path.join(pg_data, "postmaster.pid")
        if os.path.isfile(pid_file):
            logger.warning("[PostgreSQL] 清理残留 postmaster.pid ...")
            os.remove(pid_file)

        ret = subprocess.run(
            [pg_ctl, "start", "-D", pg_data, "-l", pg_log, "-w", "-t", "30"],
            capture_output=True, text=True, cwd=pg_home
        )
        if ret.returncode != 0:
            logger.error(f"[PostgreSQL] 启动失败:\n{ret.stderr}")
            return False

        # 5. 等待就绪
        if not _wait_for_port("localhost", PG_PORT, timeout=30):
            logger.error("[PostgreSQL] 启动后端口 5432 仍不可连")
            return False

        logger.info("[PostgreSQL] 服务已启动")

        # 6. 创建 admin 用户 + knowledge_base 数据库
        self._ensure_pg_user_and_db()

        return True

    def _ensure_pg_user_and_db(self):
        """创建 admin 用户和 knowledge_base 数据库（如果不存在）"""
        pg_home = self.services["postgresql"]
        psql = os.path.join(pg_home, "bin", "psql.exe")

        # 用 postgres 超级用户连接默认 postgres 库
        env = os.environ.copy()

        # 创建 admin 角色（如果不存在）
        ret = subprocess.run(
            [psql, "-U", PG_SUPER_USER, "-d", "postgres", "-h", "localhost",
             "-tc", f"SELECT 1 FROM pg_roles WHERE rolname='{PG_USER}'"],
            capture_output=True, text=True, env=env
        )
        if "1" not in ret.stdout.strip():
            logger.info(f"[PostgreSQL] 创建角色 {PG_USER} ...")
            ret = subprocess.run(
                [psql, "-U", PG_SUPER_USER, "-d", "postgres", "-h", "localhost",
                 "-c", f"CREATE ROLE {PG_USER} WITH LOGIN SUPERUSER"],
                capture_output=True, text=True, env=env
            )
            if ret.returncode != 0:
                logger.error(f"[PostgreSQL] 创建角色失败: {ret.stderr}")
            else:
                logger.info(f"[PostgreSQL] 角色 {PG_USER} 已创建")
        else:
            logger.info(f"[PostgreSQL] 角色 {PG_USER} 已存在")

        # 创建 knowledge_base 数据库（如果不存在）
        ret = subprocess.run(
            [psql, "-U", PG_SUPER_USER, "-d", "postgres", "-h", "localhost",
             "-tc", f"SELECT 1 FROM pg_database WHERE datname='{PG_DB}'"],
            capture_output=True, text=True, env=env
        )
        if "1" not in ret.stdout.strip():
            logger.info(f"[PostgreSQL] 创建数据库 {PG_DB} ...")
            ret = subprocess.run(
                [psql, "-U", PG_SUPER_USER, "-d", "postgres", "-h", "localhost",
                 "-c", f"CREATE DATABASE {PG_DB} OWNER {PG_USER}"],
                capture_output=True, text=True, env=env
            )
            if ret.returncode != 0:
                logger.error(f"[PostgreSQL] 创建数据库失败: {ret.stderr}")
            else:
                logger.info(f"[PostgreSQL] 数据库 {PG_DB} 已创建")
        else:
            logger.info(f"[PostgreSQL] 数据库 {PG_DB} 已存在")

    # ---------------------- 凭据同步 ----------------------
    def ensure_credentials(self):
        """凭据写入 keyring（PG/MinIO 密码）

        PG 是 trust 模式，密码可以是任意值，但 keyring 需要有占位值供 config.yaml 解析。
        MinIO 密码需要与 minio server 启动参数一致。
        """
        try:
            from utils.credentials import get_credential, set_credential
        except ImportError:
            logger.warning("[凭据] 无法导入 keyring 模块，跳过凭据配置")
            return

        # PG 密码（trust 模式下任意值即可）
        if not get_credential("pg_password"):
            pg_pwd = _gen_password(20)
            set_credential("pg_password", pg_pwd)
            logger.info("[凭据] pg_password 已生成并写入 keyring")
        else:
            logger.info("[凭据] pg_password 已存在")

        # MinIO Secret Key（需要与 minio server 启动参数一致）
        # 使用固定值，确保 bootstrap 启动的 minio 和 config.yaml 一致
        minio_secret = get_credential("minio_secret_key")
        if not minio_secret:
            minio_secret = _gen_password(32)
            set_credential("minio_secret_key", minio_secret)
            logger.info("[凭据] minio_secret_key 已生成并写入 keyring")
        else:
            logger.info("[凭据] minio_secret_key 已存在")

        # 保存 MinIO access_key（固定为 admin，与 config.yaml 一致）
        if not get_credential("minio_access_key"):
            set_credential("minio_access_key", "admin")
            logger.info("[凭据] minio_access_key 已写入 keyring")

    # ---------------------- 数据库初始化 ----------------------
    def init_database(self):
        """初始化数据库表结构"""
        try:
            from scripts.init_db import init_database as _init
            _init(
                host="localhost", port=PG_PORT,
                database=PG_DB, user=PG_USER,
                password=""
            )
            logger.info("[数据库] 表结构初始化完成")
        except Exception as e:
            logger.error(f"[数据库] 初始化失败: {e}")

    # ---------------------- Qdrant ----------------------
    def ensure_qdrant(self) -> bool:
        """确保 Qdrant 运行

        Qdrant 1.11+ 不再支持 --storage-dir 参数，存储目录由 cwd 相对路径决定
        （默认 ./storage）。因此通过设置 cwd=qdrant_home 让其使用 <qdrant_home>/storage。
        """
        qdrant_home = self.services.get("qdrant")
        if not qdrant_home:
            logger.error("Qdrant 未找到，请手动安装到项目父目录")
            logger.error("下载: https://github.com/qdrant/qdrant/releases")
            return False

        qdrant_exe = os.path.join(qdrant_home, "qdrant.exe")
        storage_dir = os.path.join(qdrant_home, "storage")
        os.makedirs(storage_dir, exist_ok=True)

        # 1. 检测是否已运行
        if _port_open("localhost", QDRANT_PORT):
            logger.info("[Qdrant] 已在运行")
            return True

        # 2. 后台启动（stdout/stderr 重定向到日志文件，便于排错）
        logger.info("[Qdrant] 启动服务 ...")
        stdout_log = os.path.join(qdrant_home, "stdout.log")
        stderr_log = os.path.join(qdrant_home, "stderr.log")
        try:
            stdout_fp = open(stdout_log, "w", encoding="utf-8")
            stderr_fp = open(stderr_log, "w", encoding="utf-8")
            proc = subprocess.Popen(
                [qdrant_exe],
                stdout=stdout_fp,
                stderr=stderr_fp,
                cwd=qdrant_home,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            # 记录 PID 以便后续管理
            pid_file = os.path.join(qdrant_home, ".qdrant.pid")
            with open(pid_file, "w") as f:
                f.write(str(proc.pid))
            logger.info(f"[Qdrant] 进程已启动 (PID={proc.pid})")
        except Exception as e:
            logger.error(f"[Qdrant] 启动失败: {e}")
            return False

        # 3. 等待就绪（最多 30 秒，期间检测进程是否意外退出）
        deadline = time.time() + 30
        while time.time() < deadline:
            if _port_open("localhost", QDRANT_PORT):
                logger.info("[Qdrant] 服务已就绪")
                return True
            if proc.poll() is not None:
                logger.error(f"[Qdrant] 进程意外退出 (code={proc.returncode})")
                # 打印 stderr 末尾帮助诊断
                try:
                    stdout_fp.close()
                    stderr_fp.close()
                except Exception:
                    pass
                try:
                    with open(stderr_log, "r", encoding="utf-8", errors="replace") as f:
                        tail = f.read()[-1500:]
                    if tail.strip():
                        logger.error(f"[Qdrant] stderr 末尾:\n{tail}")
                except Exception:
                    pass
                return False
            time.sleep(1.0)

        logger.error("[Qdrant] 启动后端口 6333 仍不可连（超时 30s）")
        try:
            stdout_fp.close()
            stderr_fp.close()
        except Exception:
            pass
        return False

    # ---------------------- MinIO ----------------------
    def ensure_minio(self) -> bool:
        """确保 MinIO 运行：检测 → 下载 → 启动 → 创建 bucket"""
        minio_home = self.services.get("minio")

        # 1. 检测是否已运行
        if _port_open("localhost", MINIO_PORT):
            logger.info("[MinIO] 已在运行")
            self._ensure_minio_bucket()
            return True

        # 2. 定位或下载 minio.exe
        if minio_home:
            minio_exe = os.path.join(minio_home, "bin", "minio.exe")
            if not os.path.isfile(minio_exe):
                minio_exe = os.path.join(minio_home, "minio.exe")
        else:
            # 自动下载到与 PG/Qdrant 同级的父目录（如 d:/doit/MinIO）
            # 优先用已发现的 PG/Qdrant 父目录，确保 MinIO 与它们同级
            base_dir = os.path.dirname(os.path.dirname(APP_ROOT))
            for svc_path in self.services.values():
                if svc_path and os.path.dirname(svc_path) != os.path.dirname(APP_ROOT):
                    base_dir = os.path.dirname(svc_path)
                    break
            minio_home = os.path.join(base_dir, MINIO_DIR_NAME)
            minio_bin_dir = os.path.join(minio_home, "bin")
            minio_exe = os.path.join(minio_bin_dir, "minio.exe")
            if not os.path.isfile(minio_exe):
                if not self._download_minio(minio_exe, minio_bin_dir):
                    return False
            self.services["minio"] = minio_home

        if not os.path.isfile(minio_exe):
            logger.error("[MinIO] minio.exe 不存在且下载失败")
            return False

        # 3. 获取凭据
        try:
            from utils.credentials import get_credential
            access_key = get_credential("minio_access_key") or "admin"
            secret_key = get_credential("minio_secret_key")
            if not secret_key:
                logger.warning("[MinIO] minio_secret_key 未配置，使用默认值")
                secret_key = "minioadmin"
        except ImportError:
            access_key = "admin"
            secret_key = "minioadmin"

        # 4. 启动 minio server
        data_dir = os.path.join(minio_home, "data")
        os.makedirs(data_dir, exist_ok=True)

        logger.info("[MinIO] 启动服务 ...")
        try:
            env = os.environ.copy()
            env["MINIO_ROOT_USER"] = access_key
            env["MINIO_ROOT_PASSWORD"] = secret_key
            proc = subprocess.Popen(
                [minio_exe, "server", data_dir, "--address", f":{MINIO_PORT}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                cwd=minio_home,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            pid_file = os.path.join(minio_home, ".minio.pid")
            with open(pid_file, "w") as f:
                f.write(str(proc.pid))
            logger.info(f"[MinIO] 进程已启动 (PID={proc.pid})")
        except Exception as e:
            logger.error(f"[MinIO] 启动失败: {e}")
            return False

        # 5. 等待就绪
        if not _wait_for_port("localhost", MINIO_PORT, timeout=20):
            logger.error("[MinIO] 启动后端口 9000 仍不可连")
            return False

        logger.info("[MinIO] 服务已就绪")

        # 6. 创建 bucket
        self._ensure_minio_bucket()
        return True

    def _download_minio(self, minio_exe: str, bin_dir: str) -> bool:
        """下载 minio.exe

        策略：
          1. 先 HEAD 请求 dl.min.io，从 Location 头解析出 GitHub Releases 具体版本 URL
             （因为 GitHub 的 /latest/download/ 路径在镜像上常返回 404）
          2. 用 GITHUB_MIRROR_PREFIXES 中的镜像前缀依次拼接该 URL，尝试下载
          3. 每个源依次尝试 curl.exe → PowerShell → urllib（不验证证书）

        任一方式下载到 >1MB 的文件即视为成功。
        """
        import urllib.request
        import ssl
        os.makedirs(bin_dir, exist_ok=True)

        # 步骤 1：解析 GitHub 具体版本 URL
        github_url = self._resolve_minio_github_url()
        if not github_url:
            logger.error("[MinIO] 无法解析 GitHub Releases URL，dl.min.io 不可达")
            logger.error(f"[MinIO] 请手动下载 minio.exe 放置到: {minio_exe}")
            logger.error(f"[MinIO] 下载地址: {MINIO_DOWNLOAD_URL}")
            return False
        logger.info(f"[MinIO] GitHub Releases URL: {github_url}")

        # 步骤 2：依次用镜像前缀尝试下载
        for idx, prefix in enumerate(GITHUB_MIRROR_PREFIXES):
            url = prefix + github_url if prefix else github_url
            mirror_name = prefix.split("/")[2] if prefix else "github.com (直连)"
            logger.info(f"[MinIO] 尝试镜像 {idx+1}/{len(GITHUB_MIRROR_PREFIXES)}: {mirror_name}")

            if self._try_download_file(url, minio_exe):
                logger.info(f"[MinIO] 下载完成: {minio_exe}")
                return True

            # 清理不完整文件后尝试下一个镜像
            self._cleanup_incomplete(minio_exe)

        logger.error("[MinIO] 所有镜像源下载均失败")
        logger.error(f"[MinIO] 请手动下载 minio.exe 放置到: {minio_exe}")
        logger.error(f"[MinIO] GitHub 地址: {github_url}")
        return False

    def _resolve_minio_github_url(self) -> str | None:
        """请求 dl.min.io HEAD，从 Location 头解析 GitHub Releases 具体版本 URL"""
        # 优先用 curl.exe（HEAD 请求，超时短）
        try:
            ret = subprocess.run(
                ["curl.exe", "-s", "-I", "--max-time", "15", MINIO_DOWNLOAD_URL],
                capture_output=True, text=True, timeout=20,
            )
            if ret.returncode == 0:
                for line in ret.stdout.splitlines():
                    line = line.strip()
                    if line.lower().startswith("location:"):
                        loc = line.split(":", 1)[1].strip()
                        if loc.startswith("http"):
                            return loc
        except (FileNotFoundError, Exception) as e:
            logger.warning(f"[MinIO] curl HEAD 失败: {e}")

        # 回退到 urllib（不验证证书）
        try:
            import urllib.request
            import ssl
            ctx = ssl._create_unverified_context()
            req = urllib.request.Request(MINIO_DOWNLOAD_URL, method="HEAD")
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                loc = resp.headers.get("Location")
                if loc and loc.startswith("http"):
                    return loc
        except Exception as e:
            logger.warning(f"[MinIO] urllib HEAD 失败: {e}")

        # 最后兜底：用 latest/download 路径（虽在镜像上常 404，但直连 GitHub 可能成功）
        return "https://github.com/minio/minio/releases/latest/download/minio.windows-amd64.exe"

    def _try_download_file(self, url: str, dest: str) -> bool:
        """尝试用 curl/PowerShell/urllib 下载文件，成功返回 True"""
        # 方式 1：curl.exe
        try:
            ret = subprocess.run(
                ["curl.exe", "-L", "--fail", "--max-time", "180", "-o", dest, url],
                capture_output=True, text=True, timeout=200,
            )
            if ret.returncode == 0 and os.path.isfile(dest) and \
                    os.path.getsize(dest) > 1024 * 1024:
                return True
        except FileNotFoundError:
            pass
        except Exception:
            pass

        self._cleanup_incomplete(dest)

        # 方式 2：PowerShell
        try:
            ret = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"Invoke-WebRequest -Uri '{url}' -OutFile '{dest}' -UseBasicParsing"],
                capture_output=True, text=True, timeout=180,
            )
            if ret.returncode == 0 and os.path.isfile(dest) and \
                    os.path.getsize(dest) > 1024 * 1024:
                return True
        except Exception:
            pass

        self._cleanup_incomplete(dest)

        # 方式 3：urllib + 不验证证书
        try:
            import urllib.request
            import ssl
            ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(url, context=ctx, timeout=180) as resp, \
                 open(dest, "wb") as out:
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
            if os.path.isfile(dest) and os.path.getsize(dest) > 1024 * 1024:
                return True
        except Exception:
            pass

        self._cleanup_incomplete(dest)
        return False

    @staticmethod
    def _cleanup_incomplete(path: str):
        """删除过小的不完整下载文件"""
        if os.path.isfile(path) and os.path.getsize(path) < 1024 * 1024:
            try:
                os.remove(path)
            except Exception:
                pass

    def _ensure_minio_bucket(self):
        """确保 MinIO bucket 存在"""
        try:
            from minio import Minio
            from utils.credentials import get_credential
            access_key = get_credential("minio_access_key") or "admin"
            secret_key = get_credential("minio_secret_key") or "minioadmin"
            bucket = self.config.get("storage", {}).get("minio", {}).get("bucket", "knowledge-base")

            client = Minio(f"localhost:{MINIO_PORT}", access_key=access_key,
                           secret_key=secret_key, secure=False)
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
                logger.info(f"[MinIO] bucket '{bucket}' 已创建")
            else:
                logger.info(f"[MinIO] bucket '{bucket}' 已存在")
        except Exception as e:
            logger.warning(f"[MinIO] bucket 检查失败（非致命）: {e}")

    # ---------------------- LLM API Key 检测 ----------------------
    def check_llm_key(self):
        """检测 LLM API Key 是否已配置"""
        try:
            from utils.credentials import get_credential
            # 检查 DeepSeek API Key（默认 provider）
            key = get_credential("llm_api_key_deepseek")
            if key:
                logger.info("[LLM] DeepSeek API Key 已配置")
                return True
        except ImportError:
            pass

        logger.warning("=" * 60)
        logger.warning("[LLM] DeepSeek API Key 未配置！")
        logger.warning("[LLM] 问答功能将不可用（UI 仍可启动）")
        logger.warning("[LLM] 请启动应用后进入 设置 → 模型配置 填入 API Key")
        logger.warning("[LLM] 获取地址: https://platform.deepseek.com/api_keys")
        logger.warning("=" * 60)
        return False

    # ---------------------- 回写 config.yaml ----------------------
    def _update_config(self):
        """将服务路径和凭据占位符回写到 config.yaml"""
        try:
            import yaml
        except ImportError:
            logger.warning("[配置] PyYAML 未安装，跳过回写")
            return

        changed = False
        services = self.config.setdefault("services", {})

        # 回写服务路径
        if "postgresql" in self.services:
            pg_svc = services.setdefault("postgresql", {})
            if pg_svc.get("home") != self.services["postgresql"]:
                pg_svc["home"] = self.services["postgresql"]
                changed = True
        if "qdrant" in self.services:
            qd_svc = services.setdefault("qdrant", {})
            if qd_svc.get("home") != self.services["qdrant"]:
                qd_svc["home"] = self.services["qdrant"]
                changed = True
        if "minio" in self.services:
            mn_svc = services.setdefault("minio", {})
            if mn_svc.get("home") != self.services["minio"]:
                mn_svc["home"] = self.services["minio"]
                changed = True

        # 确保 PG/MinIO 凭据用 keyring 占位符
        storage = self.config.setdefault("storage", {})
        pg_cfg = storage.setdefault("postgres", {})
        if pg_cfg.get("password") != "keyring:pg_password":
            pg_cfg["password"] = "keyring:pg_password"
            pg_cfg.pop("password_env", None)
            changed = True

        minio_cfg = storage.setdefault("minio", {})
        if minio_cfg.get("secret_key") != "keyring:minio_secret_key":
            minio_cfg["secret_key"] = "keyring:minio_secret_key"
            minio_cfg.pop("secret_key_env", None)
            changed = True
        # 确保 access_key 与 keyring 一致
        if minio_cfg.get("access_key") != "keyring:minio_access_key":
            minio_cfg["access_key"] = "keyring:minio_access_key"
            changed = True

        if changed:
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(self.config, f, allow_unicode=True, sort_keys=False)
            logger.info(f"[配置] 已回写 {self.config_path}")
        else:
            logger.info("[配置] 无需更新")


# ============================================================
# 入口
# ============================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(description="一键部署引导")
    parser.add_argument("--check", action="store_true", help="仅检测状态不启动")
    args = parser.parse_args()

    if args.check:
        # 仅检测模式
        logger.info("检测模式：仅报告状态")
        b = Bootstrap()
        b._load_config()
        b._discover_services()
        logger.info(f"PostgreSQL: {'运行中' if _port_open('localhost', PG_PORT) else '未运行'}")
        logger.info(f"Qdrant: {'运行中' if _port_open('localhost', QDRANT_PORT) else '未运行'}")
        logger.info(f"MinIO: {'运行中' if _port_open('localhost', MINIO_PORT) else '未运行'}")
        return

    b = Bootstrap()
    success = b.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
