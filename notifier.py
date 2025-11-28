import json
from models import NotifyChannel


class NotificationSender:
    """通知发送器基类"""
    
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


def parse_config(config_json: str) -> dict:
    """解析配置 JSON 字符串"""
    try:
        return json.loads(config_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"配置 JSON 格式错误: {str(e)}")
