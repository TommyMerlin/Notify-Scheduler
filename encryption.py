"""
加密工具模块 - 用于保护敏感数据
Encryption utilities for protecting sensitive data in export/import
"""
import base64
import json
from typing import Any, Dict
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.fernet import Fernet


# 需要加密的敏感字段名称
SENSITIVE_FIELDS = {
    'webhook_url',  # Webhook URLs containing secrets
    'token',        # API tokens
    'app_secret',   # App secrets
    'corp_secret',  # Corp secrets
    'corpid',       # Corp IDs
    'agentid',      # Agent IDs
    'app_id',       # App IDs
    'receiver_id',  # Receiver IDs
    'sendkey',      # Send keys
    'server_url',   # Server URLs (may contain auth)
    'username',     # Usernames for auth
    'password',     # Passwords for auth
}


def derive_encryption_key(secret_key: str) -> bytes:
    """
    从 SECRET_KEY 派生 Fernet 加密密钥
    Derive Fernet encryption key from SECRET_KEY using HKDF
    
    Args:
        secret_key: 应用的 SECRET_KEY
        
    Returns:
        Base64 编码的 Fernet 密钥
    """
    kdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b'notify-scheduler-encryption-v1',  # 固定 salt 确保密钥一致
        info=b'channel-config-encryption'
    )
    key_material = secret_key.encode('utf-8')
    derived_key = kdf.derive(key_material)
    return base64.urlsafe_b64encode(derived_key)


def get_fernet_cipher(secret_key: str) -> Fernet:
    """
    获取 Fernet 加密器实例
    Get Fernet cipher instance
    
    Args:
        secret_key: 应用的 SECRET_KEY
        
    Returns:
        Fernet 加密器
    """
    key = derive_encryption_key(secret_key)
    return Fernet(key)


def encrypt_sensitive_fields(data: Dict[str, Any], secret_key: str) -> Dict[str, Any]:
    """
    加密字典中的敏感字段
    Encrypt sensitive fields in a dictionary
    
    Args:
        data: 包含敏感数据的字典
        secret_key: 应用的 SECRET_KEY
        
    Returns:
        加密后的字典副本（标记为已加密）
    """
    if not data:
        return data
        
    cipher = get_fernet_cipher(secret_key)
    encrypted_data = data.copy()
    
    # 标记数据已加密
    encrypted_data['_encrypted'] = True
    encrypted_data['_version'] = '1.0'
    
    for field in SENSITIVE_FIELDS:
        if field in encrypted_data and encrypted_data[field]:
            # 将值加密为字符串
            value_str = str(encrypted_data[field])
            encrypted_bytes = cipher.encrypt(value_str.encode('utf-8'))
            encrypted_data[field] = base64.b64encode(encrypted_bytes).decode('utf-8')
    
    return encrypted_data


def decrypt_sensitive_fields(data: Dict[str, Any], secret_key: str) -> Dict[str, Any]:
    """
    解密字典中的敏感字段
    Decrypt sensitive fields in a dictionary
    
    Args:
        data: 包含加密数据的字典
        secret_key: 应用的 SECRET_KEY
        
    Returns:
        解密后的字典副本
    """
    if not data:
        return data
    
    # 如果没有加密标记，直接返回（向后兼容）
    if not data.get('_encrypted'):
        return data
    
    cipher = get_fernet_cipher(secret_key)
    decrypted_data = data.copy()
    
    # 移除加密标记
    decrypted_data.pop('_encrypted', None)
    decrypted_data.pop('_version', None)
    
    for field in SENSITIVE_FIELDS:
        if field in decrypted_data and decrypted_data[field]:
            try:
                # 解密字符串
                encrypted_bytes = base64.b64decode(decrypted_data[field])
                decrypted_bytes = cipher.decrypt(encrypted_bytes)
                decrypted_data[field] = decrypted_bytes.decode('utf-8')
            except Exception as e:
                # 解密失败，记录错误但保持原值（可能已是明文）
                print(f"Failed to decrypt field {field}: {e}")
                continue
    
    return decrypted_data


def encrypt_channel_config(channel_config: str, secret_key: str) -> str:
    """
    加密通道配置 JSON 字符串
    Encrypt channel configuration JSON string
    
    Args:
        channel_config: JSON 字符串格式的通道配置
        secret_key: 应用的 SECRET_KEY
        
    Returns:
        加密后的 JSON 字符串
    """
    if not channel_config:
        return channel_config
    
    try:
        config_dict = json.loads(channel_config)
        encrypted_dict = encrypt_sensitive_fields(config_dict, secret_key)
        return json.dumps(encrypted_dict)
    except json.JSONDecodeError:
        # 如果不是有效 JSON，直接返回
        return channel_config


def decrypt_channel_config(channel_config: str, secret_key: str) -> str:
    """
    解密通道配置 JSON 字符串
    Decrypt channel configuration JSON string
    
    Args:
        channel_config: 加密的 JSON 字符串格式的通道配置
        secret_key: 应用的 SECRET_KEY
        
    Returns:
        解密后的 JSON 字符串
    """
    if not channel_config:
        return channel_config
    
    try:
        config_dict = json.loads(channel_config)
        decrypted_dict = decrypt_sensitive_fields(config_dict, secret_key)
        return json.dumps(decrypted_dict)
    except json.JSONDecodeError:
        # 如果不是有效 JSON，直接返回
        return channel_config
