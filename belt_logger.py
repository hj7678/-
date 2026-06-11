"""
皮带日志系统 — 5个独立日志文件 + UI桥接

用法:
    from belt_logger import sys_log, belt_log
    sys_log.info("系统启动")
    belt_log('D7').info("路线①启动")
"""

import logging
import logging.handlers
import os
from datetime import datetime


LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')

# 初始化（只执行一次）
_belts = ['system', 'D6', 'D7', 'D8', 'D9']
_loggers = {}
_ui_callbacks = {}  # belt_id → callback(belt_id, msg)


def _init():
    os.makedirs(LOG_DIR, exist_ok=True)
    today = datetime.now().strftime('%Y-%m-%d')
    for belt in _belts:
        logger = logging.getLogger(f'belt.{belt}')
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()

        # 文件
        fh = logging.handlers.RotatingFileHandler(
            os.path.join(LOG_DIR, f'{belt}_{today}.log'),
            maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter('%(asctime)s %(message)s', datefmt='%H:%M:%S'))
        logger.addHandler(fh)

        # 终端
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(ch)

        _loggers[belt] = logger


def belt_log(belt_id: str) -> logging.Logger:
    """获取指定皮带的 logger"""
    if belt_id not in _loggers:
        _init()
    return _loggers.get(belt_id, logging.getLogger('belt.system'))


def sys_log() -> logging.Logger:
    """系统总日志 logger"""
    return belt_log('system')


def attach_ui(belt_id: str, callback):
    """绑定UI回调：日志同时推送到UI面板"""
    _ui_callbacks[belt_id] = callback


class _UIBridge(logging.Handler):
    """将日志路由到UI面板"""
    def __init__(self, belt_id):
        super().__init__()
        self.belt_id = belt_id
    def emit(self, record):
        cb = _ui_callbacks.get(self.belt_id)
        if cb:
            cb(self.belt_id, self.format(record))


def enable_ui_bridge():
    """开启UI桥接（每个logger输出到UI面板）"""
    for belt in _belts:
        logger = _loggers.get(belt)
        if logger:
            bridge = _UIBridge(belt)
            bridge.setFormatter(logging.Formatter('%(message)s'))
            logger.addHandler(bridge)


# 启动时初始化
_init()
