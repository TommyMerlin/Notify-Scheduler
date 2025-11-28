from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import enum

Base = declarative_base()


class NotifyChannel(enum.Enum):
    """通知渠道枚举"""
    WECOM = "wecom"  # 企业微信
    WECOM_WEBHOOK = "wecom_webhook"  # 企业微信Webhook
    FEISHU = "feishu"  # 飞书
    FEISHU_WEBHOOK = "feishu_webhook"  # 飞书Webhook
    DINGTALK_WEBHOOK = "dingtalk_webhook"  # 钉钉Webhook
    PUSHPLUS = "pushplus"  # PushPlus
    SERVERCHAN = "serverchan"  # Server酱
    EMAIL = "email"  # 邮件


class NotifyStatus(enum.Enum):
    """通知状态枚举"""
    PENDING = "pending"  # 待发送
    SENT = "sent"  # 已发送
    FAILED = "failed"  # 发送失败
    CANCELLED = "cancelled"  # 已取消


class NotifyTask(Base):
    """通知任务模型"""
    __tablename__ = 'notify_tasks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False, comment="通知标题")
    content = Column(Text, nullable=False, comment="通知内容")
    channel = Column(Enum(NotifyChannel), nullable=False, comment="通知渠道")
    scheduled_time = Column(DateTime, nullable=False, comment="计划发送时间")
    
    # 渠道配置（JSON格式字符串）
    channel_config = Column(Text, nullable=False, comment="渠道配置信息")
    
    # 状态相关
    status = Column(Enum(NotifyStatus), default=NotifyStatus.PENDING, comment="发送状态")
    sent_time = Column(DateTime, nullable=True, comment="实际发送时间")
    error_msg = Column(Text, nullable=True, comment="错误信息")
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    
    # 是否重复任务
    is_recurring = Column(Boolean, default=False, comment="是否重复任务")
    cron_expression = Column(String(100), nullable=True, comment="Cron表达式（用于重复任务）")

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'channel': self.channel.value,
            'scheduled_time': self.scheduled_time.isoformat() if self.scheduled_time else None,
            'status': self.status.value,
            'sent_time': self.sent_time.isoformat() if self.sent_time else None,
            'error_msg': self.error_msg,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'is_recurring': self.is_recurring,
            'cron_expression': self.cron_expression
        }


# 数据库配置
DATABASE_URL = 'sqlite:///notify_scheduler.db'
engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """初始化数据库"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        return db
    finally:
        pass
