"""
钩子执行引擎 - 任务钩子脚本执行
"""
import json
import logging
import subprocess
import tempfile
import os
import traceback
import sys
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def execute_hook(
    hook_type: str, 
    task_id: int, 
    task: Any, 
    context: Dict[str, Any], 
    db_session: Any,
    task_execution_log_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    执行钩子脚本
    
    Args:
        hook_type: 钩子类型 (before_execute/after_success/after_failure)
        task_id: 任务ID
        task: NotifyTask 对象
        context: 上下文数据
        db_session: 数据库会话
        task_execution_log_id: 任务执行日志ID
    
    Returns:
        dict: 执行结果
    """
    from models import HookExecutionLog
    
    execution_start = datetime.now()
    hook_log = None
    
    try:
        # 获取钩子配置
        hooks_config = {}
        if task.hooks_config:
            try:
                hooks_config = json.loads(task.hooks_config)
            except Exception as e:
                logger.error(f"Failed to parse hooks_config: {e}")
                return {'success': False, 'error': 'Invalid hooks_config JSON', 'skipped': False}
        
        hook_config = hooks_config.get(hook_type)
        
        if not hook_config or not hook_config.get('enabled', False):
            return {'success': True, 'skipped': True}
        
        # 准备上下文
        hook_context = {
            'task_id': task_id,
            'task': task.to_dict(),
            'hook_type': hook_type,
            'timestamp': datetime.now().isoformat(),
            **context
        }
        
        # 获取脚本配置
        script_type = hook_config.get('script_type', 'python')
        script = hook_config.get('script', '')
        timeout = hook_config.get('timeout', 30)
        
        if not script:
            return {'success': True, 'skipped': True}
        
        # 创建钩子执行日志
        hook_log = HookExecutionLog(
            task_id=task_id,
            task_execution_log_id=task_execution_log_id,
            hook_type=hook_type,
            script_type=script_type,
            script_content=script[:5000],
            execution_start=execution_start,
            status='started'
        )
        db_session.add(hook_log)
        db_session.commit()
        
        # 执行脚本
        logger.info(f"Executing {script_type} hook '{hook_type}' for task {task_id}")
        
        if script_type == 'python':
            result = _execute_python_hook(script, hook_context, timeout)
        elif script_type == 'shell':
            result = _execute_shell_hook(script, hook_context, timeout)
        else:
            result = {'success': False, 'error': f'Unsupported script type: {script_type}'}
        
        # 更新日志
        execution_end = datetime.now()
        hook_log.execution_end = execution_end
        hook_log.execution_duration = (execution_end - execution_start).total_seconds()
        hook_log.status = 'success' if result.get('success') else ('timeout' if 'timeout' in result.get('error', '').lower() else 'failed')
        hook_log.output = result.get('output', '')[:10000]
        hook_log.error_message = result.get('error')
        
        if result.get('data'):
            try:
                hook_log.return_data = json.dumps(result['data'], ensure_ascii=False)
            except:
                pass
        
        db_session.commit()
        
        return result
        
    except Exception as e:
        logger.error(f"Hook execution failed: {str(e)}\n{traceback.format_exc()}")
        
        if hook_log:
            execution_end = datetime.now()
            hook_log.execution_end = execution_end
            hook_log.execution_duration = (execution_end - execution_start).total_seconds()
            hook_log.status = 'failed'
            hook_log.error_message = str(e)
            hook_log.error_traceback = traceback.format_exc()
            try:
                db_session.commit()
            except:
                pass
        
        return {'success': False, 'error': str(e), 'skipped': False}


def _execute_python_hook(script: str, context: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    """执行 Python 脚本"""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            # 保存上下文
            context_file = os.path.join(tmpdir, 'context.json')
            with open(context_file, 'w', encoding='utf-8') as f:
                json.dump(context, f, ensure_ascii=False, indent=2)
            
            # 创建包装脚本
            wrapper_script = f"""
import json
import sys
import traceback
from datetime import datetime

# 读取上下文
with open(r'{context_file}', 'r', encoding='utf-8') as f:
    context = json.load(f)

# 提供给用户脚本的全局变量
task_id = context.get('task_id')
task = context.get('task')
hook_type = context.get('hook_type')
send_results = context.get('send_results')
error = context.get('error')

# 用于返回数据
result_data = {{}}

try:
    # 执行用户脚本
{chr(10).join('    ' + line for line in script.split(chr(10)))}
    
    # 输出结果
    print('__HOOK_RESULT_START__')
    print(json.dumps({{'success': True, 'data': result_data}}, ensure_ascii=False))
    print('__HOOK_RESULT_END__')
    
except Exception as e:
    print('__HOOK_ERROR_START__', file=sys.stderr)
    print(str(e), file=sys.stderr)
    print(traceback.format_exc(), file=sys.stderr)
    print('__HOOK_ERROR_END__', file=sys.stderr)
    sys.exit(1)
"""
            
            script_file = os.path.join(tmpdir, 'hook_script.py')
            with open(script_file, 'w', encoding='utf-8') as f:
                f.write(wrapper_script)
            
            # 执行脚本
            process = subprocess.run(
                [sys.executable, script_file],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir
            )
            
            stdout = process.stdout
            stderr = process.stderr
            
            # 解析结果
            if '__HOOK_RESULT_START__' in stdout:
                result_start = stdout.find('__HOOK_RESULT_START__') + len('__HOOK_RESULT_START__')
                result_end = stdout.find('__HOOK_RESULT_END__')
                result_json = stdout[result_start:result_end].strip()
                try:
                    result = json.loads(result_json)
                    result['output'] = stdout
                    return result
                except json.JSONDecodeError:
                    pass
            
            # 如果有错误
            if process.returncode != 0:
                error_msg = stderr
                if '__HOOK_ERROR_START__' in stderr:
                    error_start = stderr.find('__HOOK_ERROR_START__') + len('__HOOK_ERROR_START__')
                    error_end = stderr.find('__HOOK_ERROR_END__')
                    error_msg = stderr[error_start:error_end].strip()
                
                return {'success': False, 'error': error_msg, 'output': stdout}
            
            return {'success': True, 'output': stdout, 'data': {}}
            
    except subprocess.TimeoutExpired:
        return {'success': False, 'error': f'Script timeout after {timeout} seconds', 'output': ''}
    except Exception as e:
        return {'success': False, 'error': f'Failed to execute Python script: {str(e)}', 'output': ''}


def _execute_shell_hook(script: str, context: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    """执行 Shell 脚本"""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            # 准备环境变量
            env = os.environ.copy()
            env['HOOK_TASK_ID'] = str(context.get('task_id', ''))
            env['HOOK_TYPE'] = context.get('hook_type', '')
            env['HOOK_TIMESTAMP'] = context.get('timestamp', '')
            
            if context.get('task'):
                env['HOOK_TASK_JSON'] = json.dumps(context['task'], ensure_ascii=False)
            
            if context.get('send_results'):
                env['HOOK_SEND_RESULTS_JSON'] = json.dumps(context['send_results'], ensure_ascii=False)
            
            if context.get('error'):
                env['HOOK_ERROR'] = str(context['error'])
            
            # 保存脚本
            script_file = os.path.join(tmpdir, 'hook_script.sh')
            with open(script_file, 'w', encoding='utf-8') as f:
                f.write(script)
            
            # 执行脚本
            if os.name == 'nt':
                # Windows: PowerShell
                process = subprocess.run(
                    ['powershell', '-ExecutionPolicy', 'Bypass', '-File', script_file],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=tmpdir,
                    env=env
                )
            else:
                # Unix: bash
                os.chmod(script_file, 0o755)
                process = subprocess.run(
                    ['bash', script_file],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=tmpdir,
                    env=env
                )
            
            if process.returncode == 0:
                return {'success': True, 'output': process.stdout, 'data': {}}
            else:
                return {'success': False, 'error': process.stderr or f'Script exited with code {process.returncode}', 'output': process.stdout}
                
    except subprocess.TimeoutExpired:
        return {'success': False, 'error': f'Script timeout after {timeout} seconds', 'output': ''}
    except Exception as e:
        return {'success': False, 'error': f'Failed to execute shell script: {str(e)}', 'output': ''}
