from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, Enum, ForeignKey, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from contextlib import contextmanager
import enum
import hashlib
import os
import secrets
import json
import ast

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
    GOTIFY = "gotify"  # Gotify
    NTFY = "ntfy"  # ntfy.sh
    IYUU = "iyuu"  # IYUU 推送
    BAFAYUN = "bafayun"  # 巴法云
    EMAIL = "email"  # 邮件

    def __str__(self):
        return self.value


class NotifyStatus(str, enum.Enum):
    """通知状态枚举"""
    PENDING = "pending"  # 待发送
    SENT = "sent"  # 已发送
    FAILED = "failed"  # 发送失败
    CANCELLED = "cancelled"  # 已取消
    PAUSED = "paused"  # 暂停

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
    calendar_token = Column(String(64), unique=True, nullable=True, comment="日历订阅Token")

    # 关联关系
    notify_tasks = relationship("NotifyTask", back_populates="user", cascade="all, delete-orphan")
    notify_channels = relationship("UserChannel", back_populates="user", cascade="all, delete-orphan")
    external_calendars = relationship("ExternalCalendar", back_populates="user", cascade="all, delete-orphan")

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
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'calendar_token': self.calendar_token
        }


class ExternalCalendar(Base):
    """外部日历订阅"""
    __tablename__ = 'external_calendars'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, comment="用户ID")
    name = Column(String(100), nullable=False, comment="日历名称")
    url = Column(String(500), nullable=False, comment="ICS链接")
    channel_id = Column(Integer, ForeignKey('user_channels.id'), nullable=True, comment="默认通知渠道")
    last_sync = Column(DateTime, nullable=True, comment="最后同步时间")
    is_active = Column(Boolean, default=True, comment="是否启用")
    
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    
    user = relationship("User", back_populates="external_calendars")
    channel = relationship("UserChannel")

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'url': self.url,
            'channel_id': self.channel_id,
            'last_sync': self.last_sync.isoformat() if self.last_sync else None,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
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
            # 如果解析失败，尝试使用 ast.literal_eval（兼容旧数据，但只能解析字面量）
            try:
                config = ast.literal_eval(self.channel_config) if self.channel_config else {}
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


class NotifyTask(Base):
    """通知任务模型"""
    __tablename__ = 'notify_tasks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, comment="用户ID")
    title = Column(String(200), nullable=False, comment="通知标题")
    content = Column(Text, nullable=False, comment="通知内容")
    channel = Column(Enum(NotifyChannel, values_callable=lambda obj: [e.value for e in NotifyChannel]), nullable=True, comment="通知渠道（单渠道模式）")
    scheduled_time = Column(DateTime, nullable=False, comment="计划发送时间")

    # 渠道配置（JSON格式字符串）
    channel_config = Column(Text, nullable=True, comment="渠道配置信息（单渠道模式）")
    
    # 多渠道支持
    channels_json = Column(Text, nullable=True, comment="通知渠道数组（JSON格式，多渠道模式）")
    channels_config_json = Column(Text, nullable=True, comment="渠道配置映射（JSON格式，多渠道模式）")
    send_results = Column(Text, nullable=True, comment="各渠道发送结果（JSON格式）")

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
    external_uid = Column(String(255), nullable=True, comment="外部日历事件UID")

    # 关联关系
    user = relationship("User", back_populates="notify_tasks")

    def to_dict(self):
        """转换为字典"""
        # 安全解析 channel_config
        try:
            channel_config = json.loads(self.channel_config) if self.channel_config else {}
        except (json.JSONDecodeError, TypeError):
            # 如果解析失败，尝试使用 ast.literal_eval（兼容旧数据，但只能解析字面量）
            try:
                channel_config = ast.literal_eval(self.channel_config) if self.channel_config else {}
            except:
                channel_config = {}
        
        # 安全解析多渠道字段
        try:
            channels = json.loads(self.channels_json) if self.channels_json else None
        except (json.JSONDecodeError, TypeError):
            channels = None
        
        try:
            channels_config = json.loads(self.channels_config_json) if self.channels_config_json else None
        except (json.JSONDecodeError, TypeError):
            channels_config = None
        
        try:
            send_results = json.loads(self.send_results) if self.send_results else None
        except (json.JSONDecodeError, TypeError):
            send_results = None

        result = {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'channel': self.channel.value if self.channel else None,
            'scheduled_time': self.scheduled_time.isoformat() if self.scheduled_time else None,
            'status': self.status.value,
            'sent_time': self.sent_time.isoformat() if self.sent_time else None,
            'error_msg': self.error_msg,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'is_recurring': self.is_recurring,
            'cron_expression': self.cron_expression,
            'channel_config': channel_config,
            'external_uid': self.external_uid
        }
        
        # 添加多渠道字段（如果存在）
        if channels:
            result['channels'] = channels
            result['channels_config'] = channels_config
            result['send_results'] = send_results
        
        return result


# 数据库配置
default_db_path = os.path.join(os.getenv('DATA_DIR', 'data'), 'notify_scheduler.db')
os.makedirs(os.path.dirname(default_db_path), exist_ok=True)
DATABASE_URL = os.getenv('DATABASE_URL', f"sqlite:///{default_db_path}")
engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """初始化数据库"""
    Base.metadata.create_all(bind=engine)
    
    # 简单的自动迁移逻辑：检查并添加新字段
    try:
        with engine.connect() as conn:
            # 1. 检查 users.calendar_token
            try:
                conn.execute(text("SELECT calendar_token FROM users LIMIT 1"))
            except Exception:
                print("Migrating: Adding calendar_token to users table...")
                conn.execute(text("ALTER TABLE users ADD COLUMN calendar_token VARCHAR(64)"))
                conn.commit()
                
            # 2. 检查 notify_tasks.external_uid
            try:
                conn.execute(text("SELECT external_uid FROM notify_tasks LIMIT 1"))
            except Exception:
                print("Migrating: Adding external_uid to notify_tasks table...")
                conn.execute(text("ALTER TABLE notify_tasks ADD COLUMN external_uid VARCHAR(255)"))
                conn.commit()
            
            # 3. 检查 notify_tasks.channels_json（多渠道支持）
            try:
                conn.execute(text("SELECT channels_json FROM notify_tasks LIMIT 1"))
            except Exception:
                print("Migrating: Adding multi-channel support fields to notify_tasks table...")
                conn.execute(text("ALTER TABLE notify_tasks ADD COLUMN channels_json TEXT"))
                conn.execute(text("ALTER TABLE notify_tasks ADD COLUMN channels_config_json TEXT"))
                conn.execute(text("ALTER TABLE notify_tasks ADD COLUMN send_results TEXT"))
                conn.commit()
            
            # 4. 移除 channel 和 channel_config 的 NOT NULL 约束（多渠道模式需要）
            # SQLite 不支持直接修改列约束，需要重建表
            try:
                # 检查是否已经迁移（通过尝试插入 channel=NULL 的记录）
                result = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='notify_tasks'"))
                table_schema = result.fetchone()[0]
                
                # 如果表结构中 channel 字段仍有 NOT NULL 约束
                if 'channel' in table_schema and 'channel TEXT NOT NULL' in table_schema:
                    print("Migrating: Removing NOT NULL constraint from channel and channel_config...")
                    
                    # 创建临时表
                    conn.execute(text("""
                        CREATE TABLE notify_tasks_new (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            title VARCHAR(200) NOT NULL,
                            content TEXT NOT NULL,
                            channel TEXT,
                            scheduled_time DATETIME NOT NULL,
                            channel_config TEXT,
                            channels_json TEXT,
                            channels_config_json TEXT,
                            send_results TEXT,
                            status TEXT DEFAULT 'pending',
                            sent_time DATETIME,
                            error_msg TEXT,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            is_recurring BOOLEAN DEFAULT 0,
                            cron_expression VARCHAR(100),
                            external_uid VARCHAR(255),
                            FOREIGN KEY (user_id) REFERENCES users(id)
                        )
                    """))
                    
                    # 复制数据
                    conn.execute(text("""
                        INSERT INTO notify_tasks_new 
                        SELECT id, user_id, title, content, channel, scheduled_time, 
                               channel_config, channels_json, channels_config_json, send_results,
                               status, sent_time, error_msg, created_at, updated_at, 
                               is_recurring, cron_expression, external_uid
                        FROM notify_tasks
                    """))
                    
                    # 删除旧表
                    conn.execute(text("DROP TABLE notify_tasks"))
                    
                    # 重命名新表
                    conn.execute(text("ALTER TABLE notify_tasks_new RENAME TO notify_tasks"))
                    
                    conn.commit()
                    print("Migration completed: channel and channel_config are now nullable")
            except Exception as e:
                print(f"Channel nullable migration info: {e}")
    except Exception as e:
        print(f"Migration warning: {e}")


@contextmanager
def get_db():
    """获取数据库会话（上下文管理器）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
