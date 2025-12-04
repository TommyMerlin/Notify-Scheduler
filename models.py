from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, Enum, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import enum
import hashlib
import os
import secrets
import json

Base = declarative_base()

# 定义通知渠道枚举
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

    def __str__(self):
        return self.value


class NotifyStatus(enum.Enum):
    """通知状态枚举"""
    PENDING = "pending"  # 待发送
    SENT = "sent"  # 已发送
    FAILED = "failed"  # 发送失败
    CANCELLED = "cancelled"  # 已取消

    def __str__(self):
        return self.value


class User(Base):
    """用户模型"""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, comment="用户名")
    email = Column(String(100), unique=True, nullable=False, comment="邮箱")
    password_hash = Column(String(255), nullable=False, comment="密码哈希")
    salt = Column(String(32), nullable=False, comment="密码盐值")
    is_active = Column(Boolean, default=True, comment="是否激活")
    is_admin = Column(Boolean, default=False, comment="是否管理员")

    # 时间戳
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    last_login = Column(DateTime, nullable=True, comment="最后登录时间")

    # 关联关系
    notify_tasks = relationship("NotifyTask", back_populates="user", cascade="all, delete-orphan")
    notify_channels = relationship("UserChannel", back_populates="user", cascade="all, delete-orphan")

    def set_password(self, password):
        """设置密码"""
        self.salt = secrets.token_hex(16)
        self.password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), self.salt.encode('utf-8'), 100000).hex()

    def check_password(self, password):
        """验证密码"""
        return self.password_hash == hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), self.salt.encode('utf-8'), 100000).hex()

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'is_active': self.is_active,
            'is_admin': self.is_admin,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }


class UserChannel(Base):
    """用户通知渠道配置"""
    __tablename__ = 'user_channels'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, comment="用户ID")
    channel_name = Column(String(100), nullable=False, comment="渠道名称")
    channel_type = Column(Enum(NotifyChannel), nullable=False, comment="渠道类型")
    channel_config = Column(Text, nullable=False, comment="渠道配置（JSON）")
    is_default = Column(Boolean, default=False, comment="是否默认渠道")

    # 时间戳
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    # 关联关系
    user = relationship("User", back_populates="notify_channels")

    def to_dict(self):
        """转换为字典"""
        # 安全解析 channel_config
        try:
            config = json.loads(self.channel_config) if self.channel_config else {}
        except (json.JSONDecodeError, TypeError):
            # 如果解析失败，尝试使用 eval（兼容旧数据）
            try:
                config = eval(self.channel_config) if self.channel_config else {}
            except:
                config = {}

        return {
            'id': self.id,
            'channel_name': self.channel_name,
            'channel_type': self.channel_type.value if hasattr(self.channel_type, 'value') else str(self.channel_type),
            'channel_config': config,
            'is_default': self.is_default,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


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
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, comment="用户ID")
    title = Column(String(200), nullable=False, comment="通知标题")
    content = Column(Text, nullable=False, comment="通知内容")
    channel = Column(Enum(NotifyChannel, values_callable=lambda obj: [e.value for e in NotifyChannel]), nullable=False, comment="通知渠道")
    scheduled_time = Column(DateTime, nullable=False, comment="计划发送时间")

    # 渠道配置（JSON格式字符串）
    channel_config = Column(Text, nullable=False, comment="渠道配置信息")

    # 状态相关
    status = Column(Enum(NotifyStatus, values_callable=lambda obj: [e.value for e in NotifyStatus]), default=NotifyStatus.PENDING, comment="发送状态")
    sent_time = Column(DateTime, nullable=True, comment="实际发送时间")
    error_msg = Column(Text, nullable=True, comment="错误信息")

    # 时间戳
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    # 是否重复任务
    is_recurring = Column(Boolean, default=False, comment="是否重复任务")
    cron_expression = Column(String(100), nullable=True, comment="Cron表达式（用于重复任务）")

    # 关联关系
    user = relationship("User", back_populates="notify_tasks")

    def to_dict(self):
        """转换为字典"""
        # 安全解析 channel_config
        try:
            channel_config = json.loads(self.channel_config) if self.channel_config else {}
        except (json.JSONDecodeError, TypeError):
            # 如果解析失败，尝试使用 eval（兼容旧数据）
            try:
                channel_config = eval(self.channel_config) if self.channel_config else {}
            except:
                channel_config = {}

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
            'cron_expression': self.cron_expression,
            'channel_config': channel_config
        }


# 数据库配置
default_db_path = os.path.join(os.getenv('DATA_DIR', 'data'), 'notify_scheduler.db')
os.makedirs(os.path.dirname(default_db_path), exist_ok=True)
DATABASE_URL = os.getenv('DATABASE_URL', f"sqlite:///{default_db_path}")
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
