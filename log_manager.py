"""
结构化日志管理器 — 分级/文件轮转/远程采集

用法:
    from log_manager import get_logger
    log = get_logger(__name__)
    log.debug("调试信息")
    log.info("正常运行")
    log.warning("需要注意")
    log.error("故障发生")

配置: config.json → logging 节
"""

import logging
import logging.handlers
import os
import sys
from datetime import datetime
from typing import Dict, Optional


class LogManager:
    """统一日志管理器（单例）"""

    _instance: Optional['LogManager'] = None

    def __init__(self):
        self._loggers: Dict[str, logging.Logger] = {}
        self._initialized = False
        self._log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        self._level = logging.INFO
        self._console = True
        self._file_enabled = True
        self._max_bytes = 10 * 1024 * 1024  # 10MB per file
        self._backup_count = 7               # Keep 7 rotated files

    @classmethod
    def instance(cls) -> 'LogManager':
        if cls._instance is None:
            cls._instance = LogManager()
        return cls._instance

    # ------------------------------------------------------------------
    # 配置
    # ------------------------------------------------------------------

    def configure(self, level: str = 'INFO', console: bool = True,
                  file_enabled: bool = True, log_dir: str = None,
                  max_mb: int = 10, backup_count: int = 7):
        """配置日志参数"""
        level_map = {'DEBUG': logging.DEBUG, 'INFO': logging.INFO,
                     'WARNING': logging.WARNING, 'ERROR': logging.ERROR}
        self._level = level_map.get(level.upper(), logging.INFO)
        self._console = console
        self._file_enabled = file_enabled
        if log_dir:
            self._log_dir = log_dir
        self._max_bytes = max_mb * 1024 * 1024
        self._backup_count = backup_count

        # 重新配置已有的 logger
        if self._initialized:
            self._setup_root()

    def load_from_file(self, filepath: str = None):
        """从 config.json 加载日志配置"""
        if filepath is None:
            filepath = os.path.join(os.path.dirname(__file__), 'config.json')
        try:
            import json
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    cfg = json.load(f).get('logging', {})
                self.configure(
                    level=cfg.get('level', 'INFO'),
                    console=cfg.get('console', True),
                    file_enabled=cfg.get('file', True),
                    log_dir=cfg.get('dir', None),
                    max_mb=cfg.get('max_mb', 10),
                    backup_count=cfg.get('backup_count', 7),
                )
                return True
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def _setup_root(self):
        """配置根 logger"""
        root = logging.getLogger()
        root.setLevel(self._level)
        root.handlers.clear()

        # 格式: [时间] [级别] [模块] 消息
        fmt = logging.Formatter(
            '%(asctime)s [%(levelname)-5s] [%(name)-20s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        simple_fmt = logging.Formatter(
            '%(asctime)s [%(levelname)-5s] %(message)s',
            datefmt='%H:%M:%S'
        )

        # 控制台输出
        if self._console:
            ch = logging.StreamHandler(sys.stdout)
            ch.setLevel(self._level)
            ch.setFormatter(simple_fmt)
            root.addHandler(ch)

        # 文件输出（按天轮转）
        if self._file_enabled:
            os.makedirs(self._log_dir, exist_ok=True)
            today = datetime.now().strftime('%Y-%m-%d')
            log_file = os.path.join(self._log_dir, f'simulation_{today}.log')

            fh = logging.handlers.RotatingFileHandler(
                log_file, maxBytes=self._max_bytes,
                backupCount=self._backup_count, encoding='utf-8'
            )
            fh.setLevel(self._level)
            fh.setFormatter(fmt)
            root.addHandler(fh)

            # 错误日志单独文件
            err_file = os.path.join(self._log_dir, f'error_{today}.log')
            eh = logging.handlers.RotatingFileHandler(
                err_file, maxBytes=self._max_bytes,
                backupCount=self._backup_count, encoding='utf-8'
            )
            eh.setLevel(logging.ERROR)
            eh.setFormatter(fmt)
            root.addHandler(eh)

        self._initialized = True

    # ------------------------------------------------------------------
    # 获取 logger
    # ------------------------------------------------------------------

    def get_logger(self, name: str) -> logging.Logger:
        """获取模块级 logger"""
        if not self._initialized:
            self._setup_root()

        if name not in self._loggers:
            logger = logging.getLogger(name)
            logger.setLevel(self._level)
            self._loggers[name] = logger

        return self._loggers[name]


# =============================================================================
# 便捷函数
# =============================================================================

def get_logger(name: str = None) -> logging.Logger:
    """获取 logger"""
    if name is None:
        import inspect
        frame = inspect.currentframe().f_back
        name = frame.f_globals.get('__name__', 'root')
    return LogManager.instance().get_logger(name)


def init_logging(level: str = 'INFO', load_config: bool = True):
    """初始化日志系统（程序入口调用一次）"""
    mgr = LogManager.instance()
    if load_config:
        mgr.load_from_file()
    mgr.configure(level=level)
    return mgr
