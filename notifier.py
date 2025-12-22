import json
import requests
from datetime import datetime
from urllib.parse import urljoin
from models import NotifyChannel


class NotificationSender:
    """通知发送器基类"""
    
    @staticmethod
    def _process_template(text: str) -> str:
        """处理文本中的变量模板"""
        if not text:
            return text
            
        now = datetime.now()
        weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        weekdays_cn = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']

        replacements = {
            '{{date}}': now.strftime('%Y-%m-%d'),
            '{{time}}': now.strftime('%H:%M:%S'),
            '{{datetime}}': now.strftime('%Y-%m-%d %H:%M:%S'),
            '{{year}}': now.strftime('%Y'),
            '{{month}}': now.strftime('%m'),
            '{{day}}': now.strftime('%d'),
            '{{hour}}': now.strftime('%H'),
            '{{minute}}': now.strftime('%M'),
            '{{second}}': now.strftime('%S'),
            '{{timestamp}}': str(int(now.timestamp())),
            '{{weekday}}': weekdays[now.weekday()],
            '{{weekday_cn}}': weekdays_cn[now.weekday()]
        }
        
        for key, value in replacements.items():
            text = text.replace(key, value)
            
        return text

    @staticmethod
    def send(channel: NotifyChannel, config: dict, title: str, content: str):
        """
        发送通知
        
        Args:
            channel: 通知渠道
            config: 渠道配置信息
            title: 通知标题
            content: 通知内容
            
        Returns:
            bool: 发送是否成功
        """
        # 处理变量替换
        title = NotificationSender._process_template(title)
        content = NotificationSender._process_template(content)

        try:
            if channel == NotifyChannel.WECOM:
                return NotificationSender._send_wecom(config, title, content)
            elif channel == NotifyChannel.WECOM_WEBHOOK:
                return NotificationSender._send_wecom_webhook(config, title, content)
            elif channel == NotifyChannel.FEISHU:
                return NotificationSender._send_feishu(config, title, content)
            elif channel == NotifyChannel.FEISHU_WEBHOOK:
                return NotificationSender._send_feishu_webhook(config, title, content)
            elif channel == NotifyChannel.DINGTALK_WEBHOOK:
                return NotificationSender._send_dingtalk_webhook(config, title, content)
            elif channel == NotifyChannel.PUSHPLUS:
                return NotificationSender._send_pushplus(config, title, content)
            elif channel == NotifyChannel.SERVERCHAN:
                return NotificationSender._send_serverchan(config, title, content)
            elif channel == NotifyChannel.GOTIFY:
                return NotificationSender._send_gotify(config, title, content)
            elif channel == NotifyChannel.NTFY:
                return NotificationSender._send_ntfy(config, title, content)
            elif channel == NotifyChannel.IYUU:
                return NotificationSender._send_iyuu(config, title, content)
            elif channel == NotifyChannel.BAFAYUN:
                return NotificationSender._send_bafayun(config, title, content)
            else:
                raise ValueError(f"不支持的通知渠道: {channel}")
        except Exception as e:
            print(f"发送通知失败: {str(e)}")
            raise

    @staticmethod
    def _send_wecom(config: dict, title: str, content: str):
        """发送企业微信通知"""
        from ANotify import Nwecom
        
        wn = Nwecom.WxNotify(
            corpid=config['corpid'],
            corpsecret=config['corpsecret'],
            agentid=config['agentid']
        )
        
        message = f"{title}\n{content}"
        result = wn.send_msg(message)
        return True

    @staticmethod
    def _send_wecom_webhook(config: dict, title: str, content: str):
        """发送企业微信 Webhook 通知"""
        from ANotify import Nwecom
        
        wn_webhook = Nwecom.WxWebhookNotify(config['webhook_url'])
        message = f"{title}\n{content}"
        result = wn_webhook.send_msg(message)
        return True

    @staticmethod
    def _send_feishu(config: dict, title: str, content: str):
        """发送飞书通知"""
        from ANotify import Nfeishu
        
        feishu = Nfeishu.FeishuNotify(
            appid=config['appid'],
            appsecret=config['appsecret']
        )
        
        receiver_type = getattr(Nfeishu.ReceiverType, config['receiver_type'])
        message = f"{title}\n\n{content}"
        result = feishu.send_msg(receiver_type, config['receiver_id'], message)
        return True

    @staticmethod
    def _send_feishu_webhook(config: dict, title: str, content: str):
        """发送飞书 Webhook 通知"""
        from ANotify import Nfeishu
        
        feishu_webhook = Nfeishu.FeishuWebhookNotify(config['webhook_url'])
        message = f"{title}\n\n{content}"
        result = feishu_webhook.send_msg(message)
        return True

    @staticmethod
    def _send_dingtalk_webhook(config: dict, title: str, content: str):
        """发送钉钉 Webhook 通知"""
        from ANotify import Ndingtalk
        
        dingtalk_webhook = Ndingtalk.DingtalkWebhookNotify(config['webhook_url'])
        message = f"{title}\n\n{content}"
        result = dingtalk_webhook.send_msg(message)
        return True

    @staticmethod
    def _send_pushplus(config: dict, title: str, content: str):
        """发送 PushPlus 通知"""
        from ANotify import Npushplus
        
        pushplus = Npushplus.PushPlusNotify(config['token'])
        result = pushplus.send_msg(title, content, Npushplus.TemplateType.txt)
        return True

    @staticmethod
    def _send_serverchan(config: dict, title: str, content: str):
        """发送 Server酱 通知"""
        from ANotify import Nserverchan
        
        serverchan = Nserverchan.ServerChanNotify(config['token'])
        result = serverchan.send_msg(title, content)
        return True

    @staticmethod
    def _send_gotify(config: dict, title: str, content: str):
        """发送 Gotify 通知（使用 Gotify API）

        config 字段优先级：
        - `server_url`（必需）: Gotify 服务地址，例如 https://gotify.example.com
        - `token`（可选）: 应用 token，可放到查询参数或 Authorization header
        """
        server = config.get('server_url') or config.get('url')
        token = config.get('token')
        from ANotify import Ngotify
        gotify = Ngotify.GotifyNotify(server, token)
        gotify.send_msg(title, content)
        return True

    @staticmethod
    def _send_ntfy(config: dict, title: str, content: str):
        """发送到 ntfy.sh 服务

        配置字段：`server_url`（可选，默认为 https://ntfy.sh）、`topic`（必需或放到 webhook_url）、`token`（可选）
        """
        server = config.get('server_url') or 'https://ntfy.sh'
        topic = config.get('topic')

        from ANotify import Nntfy
        ntfy = Nntfy.NtfyNotify(topic, server)
        ntfy.send_msg(title, content)
        return True

    @staticmethod
    def _send_iyuu(config: dict, title: str, content: str):
        """发送到 IYUU 服务（使用 token 或可选的 server_url）

        推荐配置字段：
        - `token`（必需）: IYUU 推送 token
        """
        token = config.get('token')
        from ANotify import Niyuu
        iyuu = Niyuu.IyuuNotify(token)
        iyuu.send_msg(title, content)
        return True

    @staticmethod
    def _send_bafayun(config: dict, title: str, content: str):
        """发送到巴法云（使用 token 或可选 server_url）

        推荐配置字段：
        - `token`（必需）: 巴法云的推送 token
        """
        token = config.get('token')
        from ANotify import Nbemfa
        bemfa = Nbemfa.BemfaNotify(token)
        bemfa.send_msg(title, content)
        return True

    @staticmethod
    def _send_generic_webhook(config: dict, title: str, content: str):
        """通用 webhook POST（兼容多数自定义推送服务）

        支持：`webhook_url`，可选 `method`（默认 POST），可选 `headers`（dict）
        """
        webhook = config.get('webhook_url')
        if not webhook:
            raise ValueError('缺少 webhook_url')

        method = (config.get('method') or 'POST').upper()
        headers = config.get('headers') or {}
        # 确保内容为 JSON 可序列化结构
        body = config.get('payload_template') or {'title': title, 'content': content}
        # 如果 payload_template 是字符串模板，用户可在配置中替换
        try:
            resp = requests.request(method, webhook, json=body, headers=headers, timeout=10)
            resp.raise_for_status()
            return True
        except Exception:
            # 最后尝试以 text/plain 直接 POST 内容
            resp = requests.request(method, webhook, data=f"{title}\n\n{content}", headers={'Content-Type': 'text/plain', **headers}, timeout=10)
            resp.raise_for_status()
            return True


def parse_config(config_json) -> dict:
    """解析配置 JSON 字符串或字典"""
    # 如果已经是字典，直接返回
    if isinstance(config_json, dict):
        return config_json

    # 如果是字符串，尝试解析 JSON
    try:
        return json.loads(config_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"配置 JSON 格式错误: {str(e)}")
