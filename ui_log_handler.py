"""
UI 日志处理器 — 将 Python logging 桥接到界面的 OperationLogPanel

用法:
    from ui_log_handler import UILogBridge
    bridge = UILogBridge()
    bridge.attach(operation_log_panel)
    # 之后所有 _log.info("D7|路线① 启动") 自动路由到对应皮带栏
"""

import logging
import re
from typing import Optional


class UILogBridge(logging.Handler):
    """将 logging 消息路由到 UI 操作日志面板

    消息格式: "D7|消息内容" 或 "系统|消息内容" 或纯文本
    皮带前缀: D6/D7/D8/D9 → 对应皮带栏
    系统前缀: 系统/SYS → 系统栏
    无前缀 → 系统栏
    """

    # 皮带 → 标题颜色
    BELT_COLORS = {
        'D6': '#3498DB', 'D7': '#2ECC71',
        'D8': '#F39C12', 'D9': '#E74C3C',
    }
    # 级别 → 颜色
    LEVEL_COLORS = {
        logging.DEBUG: '#6E7681',
        logging.INFO: '#C0C8D0',
        logging.WARNING: '#F39C12',
        logging.ERROR: '#E74C3C',
    }

    def __init__(self, level=logging.INFO):
        super().__init__(level)
        self._panel = None  # OperationLogPanel 引用

    def attach(self, operation_log_panel):
        """绑定到界面面板"""
        self._panel = operation_log_panel

    def emit(self, record: logging.LogRecord):
        if not self._panel:
            return

        msg = self.format(record)
        belt_id, text = self._parse(msg)
        color = self.LEVEL_COLORS.get(record.levelno, '#C0C8D0')

        # 直接写入 QTextEdit 的 section，避开 add_log() 避免递归
        try:
            from datetime import datetime
            now = datetime.now().strftime("%H:%M:%S")
            line = f'<span style="color:#6E7681;">[{now}]</span> <span style="color:{color};">{text or msg}</span>'

            if belt_id and belt_id in self._panel._sections:
                section = self._panel._sections[belt_id]
                section._text.append(line)
            elif hasattr(self._panel, '_sys_log'):
                self._panel._sys_log._text.append(line)
        except:
            pass

    def _parse(self, msg: str) -> tuple:
        """解析消息，提取皮带ID和文本"""
        # 格式: "D7|消息内容"
        m = re.match(r'^(D[6789])\|(.+)$', msg)
        if m:
            return m.group(1), m.group(2).strip()
        # 格式: "系统|消息内容"
        m = re.match(r'^系统\|(.+)$', msg)
        if m:
            return None, m.group(1).strip()
        # 格式: "[D7] 消息内容"
        m = re.match(r'^\[(D[6789])\]\s*(.+)$', msg)
        if m:
            return m.group(1), m.group(2).strip()
        # 纯文本 → 系统栏
        return None, msg.strip()
