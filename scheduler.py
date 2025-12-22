from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger
from models import NotifyTask, NotifyStatus, ExternalCalendar, UserChannel, get_db
from notifier import NotificationSender, parse_config
import logging
import queue
import requests
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EventManager:
    def __init__(self):
        # listeners: list of (queue, user_id)
        self.listeners = []

    def listen(self, user_id):
        q = queue.Queue(maxsize=10)
        self.listeners.append((q, user_id))
        return q

    def announce(self, user_id, msg):
        for i in range(len(self.listeners) - 1, -1, -1):
            q, uid = self.listeners[i]
            if uid == user_id:
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    del self.listeners[i]

event_manager = EventManager()


def get_cron_trigger(expression):
    """根据 cron 表达式获取触发器，支持 5 位 (分时日月周) 和 6 位 (秒分时日月周)"""
    values = expression.strip().split()
    if len(values) == 6:
        return CronTrigger(
            second=values[0],
            minute=values[1],
            hour=values[2],
            day=values[3],
            month=values[4],
            day_of_week=values[5]
        )
    return CronTrigger.from_crontab(expression)


class NotifyScheduler:
    """通知调度器"""
    
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        logger.info("通知调度器已启动")
    
    def add_task(self, task: NotifyTask):
        """
        添加通知任务到调度器
        
        Args:
            task: 通知任务对象
        """
        if task.is_recurring and task.cron_expression:
            # 重复任务，使用 cron 表达式
            try:
                trigger = get_cron_trigger(task.cron_expression)
                job_id = f"recurring_task_{task.id}"
                
                self.scheduler.add_job(
                    func=self._execute_task,
                    trigger=trigger,
                    args=[task.id],
                    id=job_id,
                    replace_existing=True,
                    misfire_grace_time=60  # 错过时间窗口60秒内仍执行
                )
                logger.info(f"任务 {task.id} 已添加到调度器，计划执行时间: {task.scheduled_time}")
            except Exception as e:
                logger.error(f"添加任务 {task.id} 失败，Cron 表达式无效: {e}")
        else:
            # 一次性任务，使用指定时间
            trigger = DateTrigger(run_date=task.scheduled_time)
            job_id = f"task_{task.id}"
        
            self.scheduler.add_job(
                func=self._execute_task,
                trigger=trigger,
                args=[task.id],
                id=job_id,
                replace_existing=True,
                misfire_grace_time=60  # 错过时间窗口60秒内仍执行
            )
            
            logger.info(f"任务 {task.id} 已添加到调度器，计划执行时间: {task.scheduled_time}")
    
    def remove_task(self, task_id: int, is_recurring: bool = False):
        """
        从调度器中移除任务
        
        Args:
            task_id: 任务ID
            is_recurring: 是否为重复任务
        """
        try:
            job_id = f"recurring_task_{task_id}" if is_recurring else f"task_{task_id}"
            self.scheduler.remove_job(job_id)
            logger.info(f"任务 {task_id} 已从调度器移除")
        except Exception as e:
            logger.warning(f"移除任务 {task_id} 失败: {str(e)}")
    
    def _execute_task(self, task_id: int):
        """
        执行通知任务

        Args:
            task_id: 任务ID
        """
        with get_db() as db:
            try:
                # 获取任务
                task = db.query(NotifyTask).filter(NotifyTask.id == task_id).first()
                if not task:
                    logger.error(f"任务 {task_id} 不存在")
                    return

                # 如果任务已取消，跳过执行
                if task.status == NotifyStatus.CANCELLED:
                    logger.info(f"任务 {task_id} 已取消，跳过执行")
                    return

                # 检查暂停状态
                if task.status == NotifyStatus.PAUSED:
                    logger.info(f"任务 {task_id} 已暂停，跳过执行")
                    return

                logger.info(f"开始执行任务 {task_id}: {task.title}")

                # 解析配置
                config = parse_config(task.channel_config)

                # 发送通知
                try:
                    NotificationSender.send(
                        channel=task.channel,
                        config=config,
                        title=task.title,
                        content=task.content
                    )

                    # 更新任务状态
                    if not task.is_recurring:
                        task.status = NotifyStatus.SENT
                    task.sent_time = datetime.now()
                    task.error_msg = None

                    # 关键：重复任务执行成功后，滚动更新下一次执行时间（用于列表展示）
                    if task.is_recurring and task.cron_expression:
                        try:
                            trigger = get_cron_trigger(task.cron_expression)
                            # 以"本次实际执行时间"为基准，计算下一次
                            base_time = datetime.now()
                            next_run = trigger.get_next_fire_time(None, base_time)
                            if next_run:
                                task.scheduled_time = next_run
                        except Exception as e:
                            # 不影响本次发送结果，但记录日志
                            logger.warning(f"任务 {task_id} 更新下一次执行时间失败: {str(e)}")

                    logger.info(f"任务 {task_id} 执行成功")
                    
                    # 通知前端
                    event_manager.announce(task.user_id, {
                        'type': 'task_executed',
                        'task_id': task.id,
                        'title': task.title,
                        'status': 'sent',
                        'message': '发送成功'
                    })

                except Exception as e:
                    # 更新任务状态为失败
                    task.status = NotifyStatus.FAILED
                    task.error_msg = str(e)
                    logger.error(f"任务 {task_id} 执行失败: {str(e)}")
                    
                    # 通知前端
                    event_manager.announce(task.user_id, {
                        'type': 'task_executed',
                        'task_id': task.id,
                        'title': task.title,
                        'status': 'failed',
                        'message': str(e)
                    })

                db.commit()

            except Exception as e:
                logger.error(f"执行任务 {task_id} 时发生错误: {str(e)}")
                db.rollback()
    
    def load_pending_tasks(self):
        """
        加载所有待发送的任务到调度器
        """
        with get_db() as db:
            try:
                # 查询所有待发送的任务
                pending_tasks = db.query(NotifyTask).filter(
                    NotifyTask.status == NotifyStatus.PENDING
                ).all()

                logger.info(f"找到 {len(pending_tasks)} 个待发送任务")

                for task in pending_tasks:
                    # 如果是一次性任务且计划时间已过，跳过
                    if not task.is_recurring and task.scheduled_time < datetime.now():
                        logger.warning(f"任务 {task.id} 计划时间已过，跳过加载")
                        continue

                    # 如果是重复任务且计划时间已过，重新计算下一次执行时间
                    if task.is_recurring and task.cron_expression and task.scheduled_time < datetime.now():
                        try:
                            trigger = get_cron_trigger(task.cron_expression)
                            next_run = trigger.get_next_fire_time(None, datetime.now())
                            if next_run:
                                task.scheduled_time = next_run
                                db.commit()
                                logger.info(f"重复任务 {task.id} 的执行时间已过期，已更新为下一次执行时间: {next_run}")
                        except Exception as e:
                            logger.warning(f"重复任务 {task.id} 更新下一次执行时间失败: {str(e)}")

                    self.add_task(task)

                logger.info("待发送任务加载完成")

            except Exception as e:
                logger.error(f"加载待发送任务失败: {str(e)}")
    
    def get_scheduled_jobs(self):
        """获取所有已调度的任务"""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger)
            })
        return jobs
    
    def shutdown(self):
        """关闭调度器"""
        self.scheduler.shutdown()
        logger.info("通知调度器已关闭")

    def add_external_calendar_sync_job(self):
        """添加外部日历同步定时任务"""
        if not self.scheduler.get_job('sync_external_calendars'):
            self.scheduler.add_job(
                sync_all_external_calendars,
                'interval',
                minutes=15,
                id='sync_external_calendars',
                replace_existing=True
            )
            logger.info("外部日历同步任务已启动 (每15分钟)")


# 全局调度器实例
scheduler = NotifyScheduler()

# --- 外部日历同步逻辑 ---

def parse_ics_content(content):
    """简易 ICS 解析器 (避免引入 heavy 依赖)"""
    events = []
    lines = content.replace('\r\n', '\n').split('\n')
    
    # 处理折行 (line unfolding)
    unfolded_lines = []
    for line in lines:
        if line.startswith(' ') or line.startswith('\t'):
            if unfolded_lines:
                unfolded_lines[-1] += line[1:]
        else:
            unfolded_lines.append(line)
            
    current_event = {}
    in_event = False
    
    for line in unfolded_lines:
        if line == 'BEGIN:VEVENT':
            in_event = True
            current_event = {}
        elif line == 'END:VEVENT':
            in_event = False
            if 'DTSTART' in current_event and 'SUMMARY' in current_event:
                events.append(current_event)
        elif in_event:
            if ':' in line:
                key, val = line.split(':', 1)
                # 处理参数 (如 DTSTART;TZID=...)
                prop_name = key.split(';')[0]
                current_event[prop_name] = val
                
    return events

def parse_ics_date(date_str):
    """解析 ICS 日期字符串"""
    try:
        # 格式: 20230101T120000Z 或 20230101T120000
        clean_str = date_str.replace('Z', '')
        if len(clean_str) == 8: # 仅日期
            return datetime.strptime(clean_str, '%Y%m%d')
        return datetime.strptime(clean_str, '%Y%m%dT%H%M%S')
    except Exception:
        return None

def sync_single_calendar(cal_id):
    """同步单个外部日历"""
    with get_db() as db:
        try:
            cal = db.query(ExternalCalendar).filter(ExternalCalendar.id == cal_id).first()
            if not cal or not cal.is_active:
                return

            logger.info(f"开始同步日历: {cal.name} ({cal.url})")
            
            # 获取默认渠道配置
            channel_config = "{}"
            channel_type = "email" # 默认 fallback
            if cal.channel_id:
                channel = db.query(UserChannel).filter(UserChannel.id == cal.channel_id).first()
                if channel:
                    channel_config = channel.channel_config
                    channel_type = channel.channel_type
            
            # 下载 ICS
            resp = requests.get(cal.url, timeout=30)
            resp.raise_for_status()
            
            events = parse_ics_content(resp.text)
            count = 0
            
            for event in events:
                uid = event.get('UID')
                if not uid:
                    continue
                    
                ext_uid = f"ext-{cal.id}-{uid}"
                summary = event.get('SUMMARY', '无标题')
                desc = event.get('DESCRIPTION', '')
                dt_start_str = event.get('DTSTART')
                
                dt_start = parse_ics_date(dt_start_str)
                if not dt_start or dt_start < datetime.now():
                    continue # 跳过过去的任务
                
                # 检查是否存在
                existing = db.query(NotifyTask).filter(NotifyTask.external_uid == ext_uid).first()
                
                if existing:
                    # 更新
                    if existing.scheduled_time != dt_start or existing.title != summary:
                        existing.scheduled_time = dt_start
                        existing.title = summary
                        existing.content = desc or summary
                        # 如果任务之前已发送或取消，重新激活
                        if existing.status in [NotifyStatus.SENT, NotifyStatus.CANCELLED]:
                            existing.status = NotifyStatus.PENDING
                        scheduler.add_task(existing)
                        count += 1
                else:
                    # 创建新任务
                    new_task = NotifyTask(
                        user_id=cal.user_id,
                        title=summary,
                        content=desc or summary,
                        channel=channel_type,
                        channel_config=channel_config,
                        scheduled_time=dt_start,
                        status=NotifyStatus.PENDING,
                        external_uid=ext_uid,
                        is_recurring=False # 外部日历的重复由外部处理，这里只同步具体事件
                    )
                    db.add(new_task)
                    db.commit() # 提交以获取 ID
                    scheduler.add_task(new_task)
                    count += 1
            
            cal.last_sync = datetime.now()
            db.commit()
            logger.info(f"日历 {cal.name} 同步完成，更新/创建 {count} 个任务")
            
            # 通知前端
            event_manager.announce(cal.user_id, {
                'type': 'calendar_synced',
                'message': f'日历 "{cal.name}" 同步完成'
            })
            
        except Exception as e:
            logger.error(f"同步日历 {cal_id} 失败: {str(e)}")

def sync_all_external_calendars():
    """同步所有活跃的外部日历"""
    with get_db() as db:
        cals = db.query(ExternalCalendar).filter(ExternalCalendar.is_active == True).all()
        for cal in cals:
            # 为每个日历创建一个单独的 job 立即执行，避免阻塞
            scheduler.scheduler.add_job(
                sync_single_calendar,
                args=[cal.id],
                id=f"sync_cal_{cal.id}_auto",
                replace_existing=True,
                misfire_grace_time=60
            )
