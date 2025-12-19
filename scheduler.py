from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger
from models import NotifyTask, NotifyStatus, get_db
from notifier import NotificationSender, parse_config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
            trigger = CronTrigger.from_crontab(task.cron_expression)
            job_id = f"recurring_task_{task.id}"
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
                            from apscheduler.triggers.cron import CronTrigger
                            trigger = CronTrigger.from_crontab(task.cron_expression)
                            # 以"本次实际执行时间"为基准，计算下一次
                            base_time = datetime.now()
                            next_run = trigger.get_next_fire_time(None, base_time)
                            if next_run:
                                task.scheduled_time = next_run
                        except Exception as e:
                            # 不影响本次发送结果，但记录日志
                            logger.warning(f"任务 {task_id} 更新下一次执行时间失败: {str(e)}")

                    logger.info(f"任务 {task_id} 执行成功")

                except Exception as e:
                    # 更新任务状态为失败
                    task.status = NotifyStatus.FAILED
                    task.error_msg = str(e)
                    logger.error(f"任务 {task_id} 执行失败: {str(e)}")

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
                            trigger = CronTrigger.from_crontab(task.cron_expression)
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


# 全局调度器实例
scheduler = NotifyScheduler()
