"""
日志工具 - Logger Utility
"""

import os
import logging
from datetime import datetime
from typing import Optional


class Logger:
    """日志工具类"""

    _instance: Optional['Logger'] = None

    def __init__(self, name: str = "Simulation", log_dir: str = "logs"):
        self.name = name
        self.log_dir = log_dir
        self._setup_logger()

    @classmethod
    def get_instance(cls, name: str = "Simulation", log_dir: str = "logs") -> 'Logger':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls(name, log_dir)
        return cls._instance

    def _setup_logger(self):
        """设置日志记录器"""
        # 创建日志目录
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

        # 创建logger
        self.logger = logging.getLogger(self.name)
        self.logger.setLevel(logging.DEBUG)

        # 清除现有处理器
        self.logger.handlers.clear()

        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_format)
        self.logger.addHandler(console_handler)

        # 文件处理器
        log_file = os.path.join(
            self.log_dir,
            f"simulation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_format)
        self.logger.addHandler(file_handler)

    def debug(self, message: str):
        """调试日志"""
        self.logger.debug(message)

    def info(self, message: str):
        """信息日志"""
        self.logger.info(message)

    def warning(self, message: str):
        """警告日志"""
        self.logger.warning(message)

    def error(self, message: str):
        """错误日志"""
        self.logger.error(message)

    def critical(self, message: str):
        """严重错误日志"""
        self.logger.critical(message)

    def log_event(self, event_type: str, message: str):
        """记录事件"""
        self.logger.info(f"[{event_type}] {message}")


# 全局日志实例
_app_logger: Optional[Logger] = None


def get_logger() -> Logger:
    """获取全局日志实例"""
    global _app_logger
    if _app_logger is None:
        _app_logger = Logger.get_instance()
    return _app_logger
