const API_BASE = '/api';
let channels = [];
let currentUser = null;
let userChannels = [];
let eventSource = null;

// 初始化
document.addEventListener('DOMContentLoaded', function() {
    checkAuthStatus();
});

// 检查认证状态
async function checkAuthStatus() {
    const token = localStorage.getItem('token');
    if (!token) {
        showLoginPage();
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/auth/profile`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (response.ok) {
            const data = await response.json();
            currentUser = data.user;
            showMainApp();
        } else {
            localStorage.removeItem('token');
            showLoginPage();
        }
    } catch (error) {
        localStorage.removeItem('token');
        showLoginPage();
    }
}

// 显示登录页面
function showLoginPage() {
    document.getElementById('loginPage').style.display = 'block';
    document.getElementById('mainApp').style.display = 'none';
    initLoginEvents();
}

// 显示主应用
function showMainApp() {
    document.getElementById('loginPage').style.display = 'none';
    document.getElementById('mainApp').style.display = 'block';
    document.getElementById('currentUsername').textContent = currentUser.username;
    loadChannels();
    loadUserChannels();
    loadTasks();
    initAppEvents();
    setDefaultTime();
    initSSE();

    // 尝试加载日历（如果存在日历脚本且在主界面显示后）
    if (typeof window.loadCalendar === 'function') {
        setTimeout(window.loadCalendar, 200);
    }
}

// 切换登录/注册标签
function switchTab(tab) {
    const tabs = document.querySelectorAll('.login-tab');
    const contents = document.querySelectorAll('.tab-content');

    tabs.forEach(t => t.classList.remove('active'));
    contents.forEach(c => c.classList.remove('active'));

    if (tab === 'login') {
        tabs[0].classList.add('active');
        document.getElementById('loginTab').classList.add('active');
    } else {
        tabs[1].classList.add('active');
        document.getElementById('registerTab').classList.add('active');
    }
}

// 初始化登录事件
function initLoginEvents() {
    document.getElementById('loginForm').addEventListener('submit', handleLogin);
    document.getElementById('registerForm').addEventListener('submit', handleRegister);
}

// 处理登录
async function handleLogin(e) {
    e.preventDefault();
    const formData = new FormData(e.target);
    const loginData = {
        username: formData.get('username'),
        password: formData.get('password')
    };

    try {
        const response = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(loginData)
        });

        const result = await response.json();

        if (response.ok) {
            localStorage.setItem('token', result.data.token);
            currentUser = result.data.user;
            showMainApp();
            showNotification('登录成功！', 'success');
        } else {
            showNotification(result.error, 'error');
        }
    } catch (error) {
        showNotification('登录失败: ' + error.message, 'error');
    }
}

// 处理注册
async function handleRegister(e) {
    e.preventDefault();
    const formData = new FormData(e.target);
    const registerData = {
        username: formData.get('username'),
        email: formData.get('email'),
        password: formData.get('password')
    };

    try {
        const response = await fetch(`${API_BASE}/auth/register`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(registerData)
        });

        const result = await response.json();

        if (response.ok) {
            showNotification('注册成功！请登录', 'success');
            switchTab('login');
            e.target.reset();
        } else {
            showNotification(result.error, 'error');
        }
    } catch (error) {
        showNotification('注册失败: ' + error.message, 'error');
    }
}

// 退出登录
function logout() {
    localStorage.removeItem('token');
    currentUser = null;
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    checkAuthStatus();
}

// 初始化 SSE
function initSSE() {
    if (eventSource) {
        eventSource.close();
    }
    
    const token = localStorage.getItem('token');
    if (!token) return;

    // 使用 query param 传递 token
    eventSource = new EventSource(`${API_BASE}/events?token=${token}`);
    
    eventSource.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'task_executed') {
                const type = data.status === 'sent' ? 'success' : 'error';
                const msgPrefix = data.status === 'sent' ? '✅' : '❌';
                showNotification(`${msgPrefix} 任务 "${data.title}" 执行完成: ${data.message}`, type);
                
                // 刷新列表
                loadTasks();
                
                // 刷新日历
                if (typeof window.loadCalendar === 'function') {
                     delete window.__TASKS_CACHE;
                     window.loadCalendar();
                }
            } else if (data.type === 'calendar_synced') {
                showNotification(`📅 ${data.message}`, 'success');
                loadTasks();
                loadExternalCalendars();
            }
        } catch (e) {
            console.error('SSE parse error', e);
        }
    };
    
    eventSource.onerror = function(err) {
        // 连接错误时，EventSource 会自动重连，这里仅记录
        console.log('SSE connection error/closed');
    };
}

// 初始化应用事件
function initAppEvents() {
    document.getElementById('taskForm').addEventListener('submit', submitTaskForm);
    document.getElementById('channel').addEventListener('change', onChannelChange);
    
    const statusFilter = document.getElementById('statusFilter');
    if (statusFilter) {
        statusFilter.addEventListener('change', loadTasks);
        // 动态添加“已暂停”选项，如果 HTML 中未添加
        if (!statusFilter.querySelector('option[value="paused"]')) {
            const option = document.createElement('option');
            option.value = 'paused';
            option.textContent = '已暂停';
            statusFilter.appendChild(option);
        }
    }

    const recurringFilterEl = document.getElementById('recurringFilter');
    if (recurringFilterEl) recurringFilterEl.addEventListener('change', loadTasks);
    document.getElementById('sortField').addEventListener('change', loadTasks);
    document.getElementById('sortOrder').addEventListener('change', loadTasks);
    document.getElementById('isRecurring').addEventListener('change', function() {
        document.getElementById('cronGroup').style.display = this.checked ? 'block' : 'none';

        // 勾选重复任务时：不可再设置计划发送时间
        const scheduledTimeInput = document.getElementById('scheduledTime');
        if (scheduledTimeInput) {
            if (this.checked) {
                scheduledTimeInput.disabled = true;
                scheduledTimeInput.removeAttribute('required');
                scheduledTimeInput.value = '';
            } else {
                scheduledTimeInput.disabled = false;
                scheduledTimeInput.setAttribute('required', 'required');
                // 恢复默认时间
                setDefaultTime();
            }
        }
    });
    
    // 绑定外部日历表单
    const extCalForm = document.getElementById('externalCalendarForm');
    if (extCalForm) {
        extCalForm.addEventListener('submit', handleAddExternalCalendar);
    }
    
    // 渠道表单提交与类型变更监听（绑定一次）
    const channelForm = document.getElementById('channelForm');
    if (channelForm && !channelForm._bound) {
        channelForm.addEventListener('submit', handleChannelFormSubmit);
        channelForm._bound = true;
    }
    const channelTypeSel = document.getElementById('channelType');
    if (channelTypeSel && !channelTypeSel._bound) {
        channelTypeSel.addEventListener('change', onChannelTypeChange);
        channelTypeSel._bound = true;
    }
}

// 加载通知渠道类型
async function loadChannels() {
    try {
        const response = await fetch(`${API_BASE}/channels`, {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            }
        });
        const data = await response.json();
        channels = data.channels;

        // 填充任务表单中的渠道选择
        const taskChannelSelect = document.getElementById('channel');
        channels.forEach(channel => {
            const option = document.createElement('option');
            option.value = channel.value;
            option.textContent = channel.label;
            option.dataset.fields = JSON.stringify(channel.config_fields);
            taskChannelSelect.appendChild(option);
        });

        // 填充渠道模态框中的渠道类型选择
        const modalChannelSelect = document.getElementById('channelType');
        channels.forEach(channel => {
            const option = document.createElement('option');
            option.value = channel.value;
            option.textContent = channel.label;
            option.dataset.fields = JSON.stringify(channel.config_fields);
            modalChannelSelect.appendChild(option);
        });
    } catch (error) {
        showNotification('加载渠道失败: ' + error.message, 'error');
    }
}

// 加载用户专属渠道
async function loadUserChannels() {
    try {
        const response = await fetch(`${API_BASE}/user/channels`, {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            }
        });
        const data = await response.json();
        userChannels = data.channels;

        renderUserChannels();
    } catch (error) {
        showNotification('加载用户渠道失败: ' + error.message, 'error');
    }
}

// 渲染用户渠道列表
function renderUserChannels() {
    const container = document.getElementById('userChannels');
    if (userChannels.length === 0) {
        container.innerHTML = '<div class="empty-state"><i>📭</i><p>暂无渠道配置</p></div>';
        return;
    }

    container.innerHTML = '';
    userChannels.forEach(channel => {
        const channelItem = document.createElement('div');
        channelItem.className = 'channel-item';

        const channelTypeLabel = channels.find(c => c.value === channel.channel_type)?.label || channel.channel_type;

        channelItem.innerHTML = `
            <div class="channel-info">
                <div class="channel-name">${channel.channel_name} ${channel.is_default ? '(默认)' : ''}</div>
                <div class="channel-type">${channelTypeLabel}</div>
            </div>
            <div class="channel-actions">
                <button class="btn btn-sm btn-info" onclick="editUserChannel(${channel.id})">编辑</button>
                <button class="btn btn-sm btn-danger" onclick="deleteUserChannel(${channel.id})">删除</button>
            </div>
        `;
        container.appendChild(channelItem);
    });
}

// 打开渠道配置模态框
function openChannelModal() {
    // 以创建模式打开模态框
    document.getElementById('editingChannelId').value = '';
    document.getElementById('channelModal').style.display = 'block';
    document.getElementById('channelForm').reset();
    document.getElementById('channelConfigFields').innerHTML = '';
    document.getElementById('channelType').disabled = false;
    // 隐藏测试按钮和清空测试结果
    document.getElementById('channelTestNotificationSection').style.display = 'none';
    document.getElementById('channelTestNotificationResult').innerHTML = '';
    // 设置标题为"添加通知渠道"
    const title = document.querySelector('#channelModal .modal-content h2');
    if (title) title.textContent = '添加通知渠道';
}

// 关闭渠道配置模态框
function closeChannelModal() {
    document.getElementById('channelModal').style.display = 'none';
    document.getElementById('channelForm').reset();
    document.getElementById('channelConfigFields').innerHTML = '';
    document.getElementById('editingChannelId').value = '';
    document.getElementById('channelType').disabled = false;
    // 隐藏测试按钮和清空测试结果
    document.getElementById('channelTestNotificationSection').style.display = 'none';
    document.getElementById('channelTestNotificationResult').innerHTML = '';
}

// 渠道类型改变时更新配置字段
function onChannelTypeChange() {
    const channelSelect = document.getElementById('channelType');
    const selectedOption = channelSelect.options[channelSelect.selectedIndex];
    const configFieldsDiv = document.getElementById('channelConfigFields');
    const testSection = document.getElementById('channelTestNotificationSection');
    const testResultDiv = document.getElementById('channelTestNotificationResult');

    if (!selectedOption.value) {
        configFieldsDiv.innerHTML = '';
        testSection.style.display = 'none';
        testResultDiv.innerHTML = '';
        return;
    }

    const fields = JSON.parse(selectedOption.dataset.fields || '[]');
    configFieldsDiv.innerHTML = '';

    fields.forEach(field => {
        const formGroup = document.createElement('div');
        formGroup.className = 'form-group';

        const label = document.createElement('label');
        label.textContent = getFieldLabel(field);
        formGroup.appendChild(label);

        const input = document.createElement('input');
        input.type = field.includes('token') || field.includes('secret') ? 'password' : 'text';
        input.id = `channelConfig_${field}`;
        input.name = field;
        input.placeholder = `请输入${getFieldLabel(field)}`;
        input.required = true;
        formGroup.appendChild(input);

        configFieldsDiv.appendChild(formGroup);
    });

    // 显示测试按钮
    testSection.style.display = 'block';
    testResultDiv.innerHTML = '';
}

// 处理渠道表单（创建或编辑）
async function handleChannelFormSubmit(e) {
    e.preventDefault();
    const formData = new FormData(e.target);
    const editingId = document.getElementById('editingChannelId').value;
    const channelSelect = document.getElementById('channelType');
    const selectedOption = channelSelect.options[channelSelect.selectedIndex];
    const configFields = JSON.parse(selectedOption?.dataset?.fields || '[]');

    // 构建配置对象
    const channelConfig = {};
    configFields.forEach(field => {
        const el = document.getElementById(`channelConfig_${field}`) || document.getElementById(`editConfig_${field}`) || document.getElementById(`config_${field}`);
        const value = el ? el.value : '';
        channelConfig[field] = value;
    });

    const commonData = {
        channel_name: formData.get('channelName'),
        channel_config: channelConfig,
        is_default: formData.get('isDefault') === 'on'
    };

    try {
        let response;
        if (!editingId) {
            // 创建
            const postData = Object.assign({}, commonData, { channel_type: formData.get('channelType') });
            response = await fetch(`${API_BASE}/user/channels`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('token')}`
                },
                body: JSON.stringify(postData)
            });
        } else {
            // 编辑（只允许修改名称、配置、是否默认）
            response = await fetch(`${API_BASE}/user/channels/${editingId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('token')}`
                },
                body: JSON.stringify(commonData)
            });
        }

        const result = await response.json();

        if (response.ok) {
            showNotification(editingId ? '渠道更新成功！' : '渠道创建成功！', 'success');
            closeChannelModal();
            loadUserChannels();
        } else {
            showNotification(result.error || '操作失败', 'error');
        }
    } catch (error) {
        showNotification('操作失败: ' + error.message, 'error');
    }
}

// 删除用户渠道
async function deleteUserChannel(channelId) {
    if (!confirm('确定要删除这个渠道配置吗？')) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/user/channels/${channelId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            }
        });

        const result = await response.json();

        if (response.ok) {
            showNotification('渠道删除成功', 'success');
            loadUserChannels();
        } else {
            showNotification(result.error, 'error');
        }
    } catch ( error) {
        showNotification('删除渠道失败: ' + error.message, 'error');
    }
}

// 编辑用户渠道（打开模态框并填充数据）
function editUserChannel(channelId) {
    const channel = userChannels.find(uc => uc.id == channelId);
    if (!channel) {
        showNotification('渠道不存在', 'error');
        return;
    }

    document.getElementById('editingChannelId').value = channel.id;
    document.getElementById('channelModal').style.display = 'block';
    // 更新模态框标题
    const title = document.querySelector('#channelModal .modal-content h2');
    if (title) title.textContent = '编辑通知渠道';

    // 填充基本信息
    document.getElementById('channelName').value = channel.channel_name || '';
    const channelTypeSel = document.getElementById('channelType');
    channelTypeSel.value = channel.channel_type;
    channelTypeSel.disabled = true; // 不允许修改渠道类型

    // 触发生成配置字段
    onChannelTypeChange();

    // 填充配置字段
    const selectedOption = channelTypeSel.options[channelTypeSel.selectedIndex];
    const fields = JSON.parse(selectedOption.dataset.fields || '[]');
    const cfg = channel.channel_config || {};
    fields.forEach(field => {
        const input = document.getElementById(`channelConfig_${field}`);
        if (input) input.value = cfg[field] || '';
    });

    // 填充默认渠道选项
    document.getElementById('isDefaultChannel').checked = !!channel.is_default;
}

// 渠道改变时更新配置字段
function onChannelChange() {
    const channelSelect = document.getElementById('channel');
    const selectedOption = channelSelect.options[channelSelect.selectedIndex];
    const configFieldsDiv = document.getElementById('configFields');
    const testNotificationSection = document.getElementById('testNotificationSection');

    if (!selectedOption || !selectedOption.value) {
        configFieldsDiv.style.display = 'none';
        testNotificationSection.style.display = 'none';
        return;
    }

    const fields = JSON.parse(selectedOption.dataset.fields || '[]');
    configFieldsDiv.innerHTML = '';

    // 先显示用户已保存的渠道选项
    const userChannelSelect = document.createElement('select');
    userChannelSelect.id = 'userChannelSelect';
    userChannelSelect.className = 'user-channel-select';

    const defaultOption = document.createElement('option');
    defaultOption.value = '';
    defaultOption.textContent = '选择已保存的渠道（可选）';
    userChannelSelect.appendChild(defaultOption);

    userChannels.forEach(userChannel => {
        if (userChannel.channel_type === selectedOption.value) {
            const option = document.createElement('option');
            option.value = userChannel.id;
            option.textContent = `${userChannel.channel_name} ${userChannel.is_default ? '(默认)' : ''}`;
            userChannelSelect.appendChild(option);
        }
    });

    if (userChannels.some(uc => uc.channel_type === selectedOption.value)) {
        configFieldsDiv.appendChild(userChannelSelect);
    }

    fields.forEach(field => {
        const formGroup = document.createElement('div');
        formGroup.className = 'form-group';

        const label = document.createElement('label');
        label.textContent = getFieldLabel(field);
        formGroup.appendChild(label);

        const input = document.createElement('input');
        input.type = field.includes('token') || field.includes('secret') ? 'password' : 'text';
        input.id = `config_${field}`;
        input.name = field;
        input.placeholder = `请输入${getFieldLabel(field)}`;
        formGroup.appendChild(input);

        configFieldsDiv.appendChild(formGroup);
    });

    configFieldsDiv.style.display = 'block';

    // 显示测试通知按钮
    document.getElementById('testNotificationSection').style.display = 'block';

    // 辅助函数：根据用户渠道ID填充配置字段
    function populateFromUserChannel(selectedChannelId) {
        if (!selectedChannelId) return;
        const selectedChannel = userChannels.find(uc => uc.id == selectedChannelId);
        if (selectedChannel) {
            const config = selectedChannel.channel_config || {};
            fields.forEach(field => {
                const input = document.getElementById(`config_${field}`);
                if (input) input.value = config[field] || '';
            });
        }
    }

    // 监听用户渠道选择
    userChannelSelect.addEventListener('change', function() {
        const selectedChannelId = this.value;
        if (selectedChannelId) {
            populateFromUserChannel(selectedChannelId);
        }
    });

    // 自动选中并加载“默认”渠道（若存在），若无默认但只有一条已保存配置也自动加载
    const defaultSaved = userChannels.find(uc => uc.channel_type === selectedOption.value && uc.is_default);
    if (defaultSaved) {
        userChannelSelect.value = defaultSaved.id;
        populateFromUserChannel(defaultSaved.id);
    } else {
        const savedForType = userChannels.filter(uc => uc.channel_type === selectedOption.value);
        if (savedForType.length === 1) {
            userChannelSelect.value = savedForType[0].id;
            populateFromUserChannel(savedForType[0].id);
        }
    }
}

// 测试通知发送
async function testNotification() {
    const channelSelect = document.getElementById('channel');
    const selectedOption = channelSelect.options[channelSelect.selectedIndex];
    const resultDiv = document.getElementById('testNotificationResult');

    if (!selectedOption || !selectedOption.value) {
        showNotification('请先选择通知渠道', 'error');
        return;
    }

    const channel = selectedOption.value;
    const fields = JSON.parse(selectedOption.dataset.fields || '[]');

    // 构建配置对象
    const channelConfig = {};
    let hasEmptyField = false;

    fields.forEach(field => {
        const input = document.getElementById(`config_${field}`);
        const value = input ? input.value : '';
        if (!value) {
            hasEmptyField = true;
        }
        channelConfig[field] = value;
    });

    if (hasEmptyField) {
        showNotification('请先填写完整的渠道配置', 'error');
        return;
    }

    // 获取标题和内容（可选）
    const title = document.getElementById('title').value || undefined;
    const content = document.getElementById('content').value || undefined;

    // 显示加载状态
    resultDiv.innerHTML = '<div class="loading" style="padding: 10px;"><div class="spinner" style="width: 24px; height: 24px; margin: 0 auto 8px;"></div><p style="margin: 0; font-size: 0.9rem;">正在发送测试通知...</p></div>';

    try {
        const response = await fetch(`${API_BASE}/test-notification`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            },
            body: JSON.stringify({
                channel: channel,
                channel_config: channelConfig,
                title: title,
                content: content
            })
        });

        const result = await response.json();

        if (response.ok && result.success) {
            resultDiv.innerHTML = `
                <div style="background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 12px; padding: 12px; color: #047857;">
                    ✅ ${result.message}
                </div>
            `;
            showNotification(result.message, 'success');
        } else {
            const errorMsg = result.error || result.message || '测试失败';
            resultDiv.innerHTML = `
                <div style="background: rgba(248, 113, 113, 0.18); border: 1px solid rgba(248, 113, 113, 0.3); border-radius: 12px; padding: 12px; color: #b91c1c;">
                    ❌ ${errorMsg}
                </div>
            `;
            showNotification(errorMsg, 'error');
        }
    } catch (error) {
        resultDiv.innerHTML = `
            <div style="background: rgba(248, 113, 113, 0.18); border: 1px solid rgba(248, 113, 113, 0.3); border-radius: 12px; padding: 12px; color: #b91c1c;">
                ❌ 请求失败: ${error.message}
            </div>
        `;
        showNotification('测试失败: ' + error.message, 'error');
    }
}

// 测试渠道配置通知发送
async function testChannelNotification() {
    const channelSelect = document.getElementById('channelType');
    const selectedOption = channelSelect.options[channelSelect.selectedIndex];
    const resultDiv = document.getElementById('channelTestNotificationResult');

    if (!selectedOption || !selectedOption.value) {
        showNotification('请先选择渠道类型', 'error');
        return;
    }

    const channel = selectedOption.value;
    const fields = JSON.parse(selectedOption.dataset.fields || '[]');

    // 构建配置对象
    const channelConfig = {};
    let hasEmptyField = false;

    fields.forEach(field => {
        const input = document.getElementById(`channelConfig_${field}`);
        const value = input ? input.value : '';
        if (!value) {
            hasEmptyField = true;
        }
        channelConfig[field] = value;
    });

    if (hasEmptyField) {
        showNotification('请先填写完整的渠道配置', 'error');
        return;
    }

    // 显示加载状态
    resultDiv.innerHTML = '<div class="loading" style="padding: 10px;"><div class="spinner" style="width: 24px; height: 24px; margin: 0 auto 8px;"></div><p style="margin: 0; font-size: 0.9rem;">正在发送测试通知...</p></div>';

    try {
        const response = await fetch(`${API_BASE}/test-notification`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            },
            body: JSON.stringify({
                channel: channel,
                channel_config: channelConfig
            })
        });

        const result = await response.json();

        if (response.ok && result.success) {
            resultDiv.innerHTML = `
                <div style="background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 12px; padding: 12px; color: #047857;">
                    ✅ ${result.message}
                </div>
            `;
            showNotification(result.message, 'success');
        } else {
            const errorMsg = result.error || result.message || '测试失败';
            resultDiv.innerHTML = `
                <div style="background: rgba(248, 113, 113, 0.18); border: 1px solid rgba(248, 113, 113, 0.3); border-radius: 12px; padding: 12px; color: #b91c1c;">
                    ❌ ${errorMsg}
                </div>
            `;
            showNotification(errorMsg, 'error');
        }
    } catch (error) {
        resultDiv.innerHTML = `
            <div style="background: rgba(248, 113, 113, 0.18); border: 1px solid rgba(248, 113, 113, 0.3); border-radius: 12px; padding: 12px; color: #b91c1c;">
                ❌ 请求失败: ${error.message}
            </div>
        `;
        showNotification('测试失败: ' + error.message, 'error');
    }
}

// 获取字段中文标签
function getFieldLabel(field) {
    const labels = {
        'corpid': '企业ID',
        'corpsecret': '应用Secret',
        'agentid': '应用ID',
        'webhook_url': 'Webhook URL',
        'appid': '应用ID',
        'appsecret': '应用Secret',
        'receiver_type': '接收者类型',
        'receiver_id': '接收者ID',
        'token': 'Token'
    };
    return labels[field] || field;
}

// 将 cron 表达式中的星期数字从 Sunday-first (0=Sun) 转换为 Monday-first (0=Mon)
// 转换规则：new = (old + 6) % 7
function convertCronExpressionForBackend(expr) {
    if (!expr || typeof expr !== 'string') return expr;
    const parts = expr.trim().split(/\s+/);
    if (parts.length < 5) return expr; // 非标准 5 字段 cron，直接返回原样
    // 星期字段通常是最后一项（支持 5+ 字段时取最后一项）
    const idx = parts.length - 1;
    parts[idx] = parts[idx].replace(/\b[0-6]\b/g, (m) => {
        const n = parseInt(m, 10);
        return String((n + 6) % 7);
    });
    return parts.join(' ');
}

// 加载任务列表
async function loadTasks() {
    const taskList = document.getElementById('taskList');
    const statusFilter = document.getElementById('statusFilter').value;
    const recurringFilterEl = document.getElementById('recurringFilter');
    const recurringFilter = recurringFilterEl ? recurringFilterEl.value : '';
    const sortFieldSelect = document.getElementById('sortField');
    const sortOrderSelect = document.getElementById('sortOrder');
    const sortField = sortFieldSelect ? sortFieldSelect.value : 'scheduled_time';
    const sortOrder = sortOrderSelect ? sortOrderSelect.value : 'asc';

    taskList.innerHTML = '<div class="loading"><div class="spinner"></div><p>加载中...</p></div>';

    try {
        const params = new URLSearchParams({ page_size: '100' });
        if (statusFilter) params.append('status', statusFilter);
        if (sortField) params.append('sort_by', sortField);
        if (sortOrder) params.append('sort_order', sortOrder.toLowerCase());

        const response = await fetch(`${API_BASE}/tasks?${params.toString()}`, {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            }
        });
        const data = await response.json();

        if (data.tasks && data.tasks.length > 0) {
            taskList.innerHTML = '';
            let tasks = data.tasks;
            // 前端筛选重复任务（后端暂不支持该 query 参数）
            if (recurringFilter === 'recurring') {
                tasks = tasks.filter(t => !!t.is_recurring);
            } else if (recurringFilter === 'non_recurring') {
                tasks = tasks.filter(t => !t.is_recurring);
            }

            if (tasks.length > 0) {
                tasks.forEach(task => taskList.appendChild(createTaskElement(task)));
            } else {
                taskList.innerHTML = '<div class="empty-state"><i>📭</i><p>暂无任务</p></div>';
            }
        } else {
            taskList.innerHTML = '<div class="empty-state"><i>📭</i><p>暂无任务</p></div>';
        }
    } catch (error) {
        taskList.innerHTML = '<div class="empty-state"><i>❌</i><p>加载失败: ' + error.message + '</p></div>';
    }
}

// 创建任务元素
function createTaskElement(task) {
    const div = document.createElement('div');
    div.className = 'task-item';
    if (task.is_recurring) div.classList.add('recurring');

    // 标记过期任务：状态为 pending 且计划时间早于当前时间
    let isExpired = false;
    try {
        const scheduled = task.scheduled_time ? new Date(task.scheduled_time) : null;
        const now = new Date();
        if (task.status === 'pending' && scheduled && scheduled < now) {
            div.classList.add('expired');
            isExpired = true;
        }
    } catch (e) {
        // 忽略解析错误
    }

    const statusClass = `status-${task.status}`;
    const statusText = {
        'pending': '待发送',
        'sent': '已发送',
        'failed': '发送失败',
        'cancelled': '已取消',
        'paused': '已暂停'
    }[task.status] || task.status;

    const expiredBadgeHTML = isExpired ? `<span class="status-badge status-expired">已过期</span>` : '';

    const channelText = channels.find(c => c.value === task.channel)?.label || task.channel;
    const scheduleLabel = task.is_recurring ? '📅 下一次执行时间' : '📅 计划时间';

    // 定义删除按钮
    const deleteBtn = `<button class="btn btn-sm btn-ghost" style="color: #ef4444; border-color: rgba(239, 68, 68, 0.2);" onclick="deleteTask(${task.id})">🗑️ 删除</button>`;

    div.innerHTML = `
        <div class="task-header">
            <div>
                <div class="task-title">
                    ${escapeHtml(task.title)}
                    ${task.is_recurring ? `<span class="recurring-badge"></span>` : ''}
                </div>
                ${expiredBadgeHTML}
                <span class="status-badge ${statusClass}">${statusText}</span>
                <span class="channel-badge">${channelText}</span>
            </div>
        </div>
        <div class="task-content">${escapeHtml(task.content)}</div>
        <div class="task-meta">
            <span>${scheduleLabel}: ${formatDateTime(task.scheduled_time)}</span>
            ${task.sent_time ? `<span>✅ 发送时间: ${formatDateTime(task.sent_time)}</span>` : ''}
            ${task.is_recurring ? `<span>🔁 重复任务: ${task.cron_expression}</span>` : ''}
            <span>🆔 ID: ${task.id}</span>
        </div>
        ${task.error_msg ? `<div style="color: #e74c3c; margin-top: 10px;">❌ 错误: ${escapeHtml(task.error_msg)}</div>` : ''}
        <div class="task-actions">
            ${task.status === 'pending' ? `
                <button class="btn btn-sm btn-info" onclick="editTask(${task.id})">编辑</button>
                ${task.is_recurring ? `<button class="btn btn-sm btn-warning" onclick="toggleTaskPause(${task.id}, 'pause')">暂停</button>` : ''}
                <button class="btn btn-sm btn-danger" onclick="cancelTask(${task.id})">取消任务</button>
                ${deleteBtn}
            ` : task.status === 'paused' ? `
                <button class="btn btn-sm btn-info" onclick="editTask(${task.id})">编辑</button>
                <button class="btn btn-sm btn-success" onclick="toggleTaskPause(${task.id}, 'resume')">恢复</button>
                <button class="btn btn-sm btn-danger" onclick="cancelTask(${task.id})">取消任务</button>
                ${deleteBtn}
            ` : `
                <button class="btn btn-sm btn-success" onclick="editTask(${task.id})">重新启用</button>
                ${deleteBtn}
            `}
        </div>
    `;

    return div;
}

// 提交任务表单
async function submitTaskForm(e) {
    e.preventDefault();

    const formData = new FormData(e.target);
    const channel = formData.get('channel');
    const channelSelect = document.getElementById('channel');
    const selectedOption = channelSelect.options[channelSelect.selectedIndex];
    const configFields = JSON.parse(selectedOption.dataset.fields || '[]');

    // 构建配置对象
    const channelConfig = {};
    configFields.forEach(field => {
        const value = document.getElementById(`config_${field}`).value;
        channelConfig[field] = value;
    });

    const isRecurring = formData.get('isRecurring') === 'on';

    // 处理并兼容转换 cron 表达式（只在重复任务时）
    let cronForBackend = null;
    if (isRecurring) {
        const rawCron = (formData.get('cronExpression') || '').trim();
        cronForBackend = rawCron ? convertCronExpressionForBackend(rawCron) : null;
    }

    // 构建任务数据
    const scheduledTimeValue = formData.get('scheduledTime');
    const taskData = {
        title: formData.get('title'),
        content: formData.get('content'),
        channel: channel,
        // 重复任务不提交 scheduled_time，由后端根据 cron_expression 计算
        // 如果有秒(长度19)则直接使用，否则(长度16)补:00
        scheduled_time: isRecurring ? undefined : (scheduledTimeValue ? (scheduledTimeValue.length === 16 ? `${scheduledTimeValue}:00` : scheduledTimeValue) : null),
        channel_config: channelConfig,
        is_recurring: isRecurring,
        cron_expression: isRecurring ? cronForBackend : null
    };

    // 移除 undefined 字段，避免后端 required_fields 判断误差
    Object.keys(taskData).forEach(k => taskData[k] === undefined && delete taskData[k]);

    try {
        const response = await fetch(`${API_BASE}/tasks`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            },
            body: JSON.stringify(taskData)
        });

        const result = await response.json();

        if (response.ok) {
            showNotification('任务创建成功！', 'success');
            e.target.reset();
            setDefaultTime();
            document.getElementById('configFields').style.display = 'none';
            document.getElementById('cronGroup').style.display = 'none';
            // 重置“重复任务”禁用态
            const scheduledTimeInput = document.getElementById('scheduledTime');
            if (scheduledTimeInput) {
                scheduledTimeInput.disabled = false;
                scheduledTimeInput.setAttribute('required', 'required');
            }
            loadTasks();

            // 刷新日历
            if (typeof window.loadCalendar === 'function') {
                delete window.__TASKS_CACHE;
                window.loadCalendar();
            }
        } else {
            showNotification('创建失败: ' + result.error, 'error');
        }
    } catch (error) {
        showNotification('创建失败: ' + error.message, 'error');
    }
}

// 自定义二次确认弹窗
function showConfirmDialog({
    title = '确认操作',
    message = '请确认是否继续',
    confirmText = '确认',
    cancelText = '再想想'
} = {}) {
    return new Promise(resolve => {
        const modal = document.getElementById('confirmModal');
        const titleEl = document.getElementById('confirmTitle');
        const messageEl = document.getElementById('confirmMessage');
        const confirmBtn = document.getElementById('confirmOkBtn');
        const cancelBtn = document.getElementById('confirmCancelBtn');

        // 如果元素缺失则回退到原生 confirm
        if (!modal || !titleEl || !messageEl || !confirmBtn || !cancelBtn) {
            resolve(confirm(message));
            return;
        }

        titleEl.textContent = title;
        messageEl.textContent = message;
        confirmBtn.textContent = confirmText;
        cancelBtn.textContent = cancelText;

        const removeListeners = () => {
            confirmBtn.removeEventListener('click', onConfirm);
            cancelBtn.removeEventListener('click', onCancel);
            modal.removeEventListener('click', onBackdrop);
            document.removeEventListener('keydown', onKeydown);
        };

        const closeModal = () => {
            modal.classList.remove('show');
            setTimeout(() => {
                modal.style.display = 'none';
            }, 180);
            removeListeners();
        };

        const onConfirm = () => {
            closeModal();
            resolve(true);
        };

        const onCancel = () => {
            closeModal();
            resolve(false);
        };

        const onBackdrop = (e) => {
            if (e.target === modal) {
                onCancel();
            }
        };

        const onKeydown = (e) => {
            if (e.key === 'Escape') {
                onCancel();
            }
        };

        confirmBtn.addEventListener('click', onConfirm);
        cancelBtn.addEventListener('click', onCancel);
        modal.addEventListener('click', onBackdrop);
        document.addEventListener('keydown', onKeydown);

        modal.style.display = 'block';
        // 下一帧再加 show 类，确保动画能正常触发；兜底用 setTimeout
        const addShowClass = () => modal.classList.add('show');
        if (typeof requestAnimationFrame === 'function') {
            requestAnimationFrame(addShowClass);
        } else {
            setTimeout(addShowClass, 16);
        }
    });
}

// 取消任务（软删除）
async function cancelTask(taskId) {
    const confirmed = await showConfirmDialog({
        title: '取消任务',
        message: '确定要取消这个任务吗？\n取消后任务将停止发送，但保留在列表中，可以重新启用。',
        confirmText: '确认取消',
        cancelText: '保留任务'
    });

    if (!confirmed) return;

    try {
        // 使用 PUT 更新状态为 cancelled
        const response = await fetch(`${API_BASE}/tasks/${taskId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            },
            body: JSON.stringify({ status: 'cancelled' })
        });

        const result = await response.json();

        if (response.ok) {
            showNotification('任务已取消', 'success');
            loadTasks();

            // 刷新日历
            if (typeof window.loadCalendar === 'function') {
                delete window.__TASKS_CACHE;
                window.loadCalendar();
            }
        } else {
            showNotification('取消失败: ' + result.error, 'error');
        }
    } catch (error) {
        showNotification('取消失败: ' + error.message, 'error');
    }
}

// 彻底删除任务（硬删除）
async function deleteTask(taskId) {
    const confirmed = await showConfirmDialog({
        title: '彻底删除任务',
        message: '⚠️ 确定要彻底删除这个任务吗？\n此操作将永久移除任务记录，无法恢复！',
        confirmText: '彻底删除',
        cancelText: '取消'
    });

    if (!confirmed) return;

    try {
        const response = await fetch(`${API_BASE}/tasks/${taskId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            }
        });

        const result = await response.json();

        if (response.ok) {
            showNotification('任务已彻底删除', 'success');
            loadTasks();

            // 刷新日历
            if (typeof window.loadCalendar === 'function') {
                delete window.__TASKS_CACHE;
                window.loadCalendar();
            }
        } else {
            showNotification('删除失败: ' + result.error, 'error');
        }
    } catch (error) {
        showNotification('删除失败: ' + error.message, 'error');
    }
}

// 切换任务暂停/恢复状态
async function toggleTaskPause(taskId, action) {
    const isPause = action === 'pause';
    const confirmMsg = isPause 
        ? '确定要暂停这个重复任务吗？暂停后将不再自动执行。' 
        : '确定要恢复这个任务吗？恢复后将根据 Cron 表达式重新计算下次执行时间。';
    
    const confirmed = await showConfirmDialog({
        title: isPause ? '暂停任务' : '恢复任务',
        message: confirmMsg,
        confirmText: isPause ? '暂停' : '恢复',
        cancelText: '取消'
    });

    if (!confirmed) return;

    try {
        const response = await fetch(`${API_BASE}/tasks/${taskId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            },
            body: JSON.stringify({ 
                status: isPause ? 'paused' : 'pending' 
            })
        });

        const result = await response.json();

        if (response.ok) {
            showNotification(isPause ? '任务已暂停' : '任务已恢复', 'success');
            loadTasks();

            // 刷新日历
            if (typeof window.loadCalendar === 'function') {
                delete window.__TASKS_CACHE;
                window.loadCalendar();
            }
        } else {
            showNotification((isPause ? '暂停' : '恢复') + '失败: ' + result.error, 'error');
        }
    } catch (error) {
        showNotification('操作失败: ' + error.message, 'error');
    }
}

// 设置默认时间为当前时间+1小时（东八区本地时间）
function setDefaultTime() {
    const now = new Date();
    now.setHours(now.getHours() + 1);
    now.setSeconds(0);
    now.setMilliseconds(0);
    document.getElementById('scheduledTime').value = toLocalInputValue(now);
}

// 将 Date 转为 datetime-local 可用的本地时间字符串
function toLocalInputValue(date) {
    const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
    return local.toISOString().slice(0, 19);
}

// 显示通知
function showNotification(message, type = 'success') {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);

    setTimeout(() => {
        notification.remove();
    }, 3000);
}

// 格式化时间
function formatDateTime(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

// HTML 转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 自动刷新任务列表（每30秒）
// setInterval(loadTasks, 30000);

// 响应式增强功能
function initResponsiveFeatures() {
    // 添加触摸反馈
    document.addEventListener('touchstart', function(e) {
        if (e.target.classList.contains('btn') ||
            e.target.classList.contains('task-item') ||
            e.target.closest('.btn') ||
            e.target.closest('.task-item')) {
            const element = e.target.classList.contains('btn') ? e.target :
                            e.target.closest('.btn') || e.target.closest('.task-item');
            element.style.transform = 'scale(0.98)';
            element.style.transition = 'transform 0.1s ease';
        }
    });

    document.addEventListener('touchend', function(e) {
        if (e.target.classList.contains('btn') ||
            e.target.classList.contains('task-item') ||
            e.target.closest('.btn') ||
            e.target.closest('.task-item')) {
            const element = e.target.classList.contains('btn') ? e.target :
                            e.target.closest('.btn') || e.target.closest('.task-item');
            setTimeout(() => {
                element.style.transform = 'scale(1)';
            }, 100);
        }
    });

    // 优化移动端滚动体验
    if ('ontouchstart' in window) {
        document.body.style.webkitOverflowScrolling = 'touch';

        // 为移动端优化输入框焦点
        const inputs = document.querySelectorAll('input, textarea, select');
        inputs.forEach(input => {
            input.addEventListener('focus', function() {
                // 延迟滚动以确保输入框可见
                setTimeout(() => {
                    this.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }, 300);
            });
        });
    }

    // 智能布局调整
    adjustLayoutForScreenSize();
    window.addEventListener('resize', debounce(adjustLayoutForScreenSize, 250));
    window.addEventListener('orientationchange', debounce(adjustLayoutForScreenSize, 500));
}

// 防抖函数
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// 根据屏幕尺寸调整布局
function adjustLayoutForScreenSize() {
    const width = window.innerWidth;
    const height = window.innerHeight;
    const isMobile = width <= 768;
    const isSmallMobile = width <= 480;

    // 调整任务列表高度
    const taskList = document.getElementById('taskList');
    if (taskList && taskList.style.display !== 'none') {
        if (isMobile) {
            // 简化移动端高度计算，避免受隐藏元素影响
            const viewportHeight = window.innerHeight;
            // 预留头部和底部空间
            const maxListHeight = Math.max(300, viewportHeight - 250);
            taskList.style.maxHeight = `${maxListHeight}px`;
        } else {
            // 非移动端移除 max-height 限制，使用 CSS flex 自适应
            taskList.style.maxHeight = '';
        }
    }

    // 移动端优化
    if (isMobile) {
        // 确保模态框在移动端正常显示
        const modals = document.querySelectorAll('.modal');
        modals.forEach(modal => {
            if (modal.style.display === 'block') {
                const modalContent = modal.querySelector('.modal-content');
                if (modalContent) {
                    modalContent.style.maxHeight = '80vh';
                    modalContent.style.overflowY = 'auto';
                }
            }
        });

        // 优化通知显示
        const notifications = document.querySelectorAll('.notification');
        notifications.forEach(notification => {
            notification.style.fontSize = isSmallMobile ? '14px' : '16px';
            notification.style.padding = isSmallMobile ? '12px 20px' : '15px 25px';
        });
    }
}

// 优化移动端表单体验
function optimizeMobileForms() {
    // 检测是否为移动设备
    const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);

    if (isMobile) {
        // 为移动设备优化输入类型
        const emailInputs = document.querySelectorAll('input[type="email"]');
        emailInputs.forEach(input => {
            input.setAttribute('autocomplete', 'email');
        });

        const passwordInputs = document.querySelectorAll('input[type="password"]');
        passwordInputs.forEach(input => {
            input.setAttribute('autocomplete', 'current-password');
        });

        // 优化数字输入
        const numberInputs = document.querySelectorAll('input[type="number"], input[type="tel"]');
        numberInputs.forEach(input => {
            input.setAttribute('inputmode', 'numeric');
            input.setAttribute('pattern', '[0-9]*');
        });
    }
}

function initMobileSectionToggle() {
    const tabsContainer = document.querySelector('.mobile-tabs');
    const tabs = tabsContainer ? tabsContainer.querySelectorAll('.mobile-tab') : [];
    const sections = document.querySelectorAll('.card-section');

    if (!tabs.length || !sections.length) {
        return;
    }

    let activeTarget = tabs[0].dataset.target;

    const syncSections = (isCompact) => {
        if (isCompact) {
            sections.forEach(section => {
                section.classList.toggle('active', section.dataset.section === activeTarget);
            });
        } else {
            sections.forEach(section => section.classList.add('active'));
        }
    };

    const setActiveSection = (target) => {
        activeTarget = target;
        tabs.forEach(tab => {
            const isActive = tab.dataset.target === target;
            tab.classList.toggle('active', isActive);
            tab.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        });
        syncSections(window.innerWidth <= 640);
    };

    const handleViewportChange = () => {
        syncSections(window.innerWidth <= 640);
    };

    tabs.forEach(tab => {
        tab.addEventListener('click', () => setActiveSection(tab.dataset.target));
    });

    setActiveSection(activeTarget);
    window.addEventListener('resize', debounce(handleViewportChange, 150));
    window.addEventListener('orientationchange', debounce(handleViewportChange, 150));
}

// 添加下拉刷新功能（仅移动端）
function initPullToRefresh() {
    let startY = 0;
    let isPulling = false;
    const pullThreshold = 80;

    const taskList = document.getElementById('taskList');
    if (!taskList) return;

    taskList.addEventListener('touchstart', function(e) {
        if (taskList.scrollTop === 0) {
            startY = e.touches[0].clientY;
            isPulling = true;
        }
    });

    taskList.addEventListener('touchmove', function(e) {
        if (!isPulling) return;

        const currentY = e.touches[0].clientY;
        const diff = currentY - startY;

        if (diff > 0 && diff < pullThreshold) {
            taskList.style.transform = `translateY(${diff * 0.5}px)`;
            taskList.style.transition = 'none';
        }
    });

    taskList.addEventListener('touchend', function(e) {
        if (!isPulling) return;

        isPulling = false;
        taskList.style.transform = '';
        taskList.style.transition = 'transform 0.3s ease';

        const currentY = e.changedTouches[0].clientY;
        const diff = currentY - startY;

        if (diff > pullThreshold) {
            loadTasks();
            showNotification('正在刷新...', 'success');
        }
    });
}

// 页面加载完成后初始化响应式功能
document.addEventListener('DOMContentLoaded', function() {
    // 在原有的 checkAuthStatus() 调用后添加
    setTimeout(() => {
        initMobileSectionToggle();
        initResponsiveFeatures();
        optimizeMobileForms();

        // 如果是移动设备且支持触摸，启用下拉刷新
        if ('ontouchstart' in window && window.innerWidth <= 768) {
            initPullToRefresh();
        }
    }, 1000);

    // 增加：当移动端 tab 切换到 calendar 时触发日历加载（防止与页面其它切换逻辑冲突）
    const tabs = document.querySelectorAll('.mobile-tab');
    tabs.forEach(t => {
        t.addEventListener('click', function () {
            const target = t.dataset && t.dataset.target;
            if (target === 'calendar' && typeof window.loadCalendar === 'function') {
                // 让日历脚本负责加载和渲染
                window.loadCalendar();
            }
        });
    });
});

// 监听页面可见性变化，优化性能
document.addEventListener('visibilitychange', function() {
    if (document.hidden) {
        // 页面隐藏时降低刷新频率
        clearInterval(window.taskRefreshInterval);
    } else {
        // 页面显示时恢复正常刷新频率
        window.taskRefreshInterval = setInterval(loadTasks, 30000);
        loadTasks(); // 立即刷新数据
    }
});

// 存储刷新间隔ID，便于管理
window.taskRefreshInterval = setInterval(loadTasks, 30000);

// --- 日历同步功能 ---

function openSyncModal() {
    document.getElementById('syncModal').style.display = 'block';
    // 加载订阅链接
    fetchCalendarToken();
    // 加载外部日历列表
    loadExternalCalendars();
    // 填充导入渠道选择
    populateImportChannels();
}

function closeSyncModal() {
    document.getElementById('syncModal').style.display = 'none';
}

function switchSyncTab(tab) {
    const tabs = document.querySelectorAll('#syncModal .login-tab');
    const contents = document.querySelectorAll('#syncModal .tab-content');
    
    tabs.forEach(t => t.classList.remove('active'));
    contents.forEach(c => c.classList.remove('active'));
    
    if (tab === 'export') {
        tabs[0].classList.add('active');
        document.getElementById('syncExportTab').classList.add('active');
    } else {
        tabs[1].classList.add('active');
        document.getElementById('syncImportTab').classList.add('active');
    }
}

async function fetchCalendarToken(regenerate = false) {
    try {
        const method = regenerate ? 'POST' : 'GET';
        const response = await fetch(`${API_BASE}/calendar/token`, {
            method: method,
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        });
        const data = await response.json();
        if (data.feed_url) {
            document.getElementById('calendarFeedUrl').value = data.feed_url;
            if (regenerate) showNotification('订阅链接已更新', 'success');
        }
    } catch (e) {
        console.error(e);
    }
}

function generateCalendarToken() {
    if (confirm('重置链接后，旧的订阅链接将失效，确定要重置吗？')) {
        fetchCalendarToken(true);
    }
}

function copyFeedUrl() {
    const input = document.getElementById('calendarFeedUrl');
    input.select();
    document.execCommand('copy');
    showNotification('链接已复制到剪贴板', 'success');
}

function populateImportChannels() {
    const select = document.getElementById('importChannelSelect');
    // 保留第一个选项
    select.innerHTML = '<option value="">不发送通知 (仅导入)</option>';
    
    userChannels.forEach(uc => {
        const opt = document.createElement('option');
        opt.value = uc.id;
        opt.textContent = `${uc.channel_name} (${uc.channel_type})`;
        select.appendChild(opt);
    });
}

async function loadExternalCalendars() {
    const list = document.getElementById('externalCalendarList');
    list.innerHTML = '<div class="loading"><div class="spinner" style="width:20px;height:20px;"></div></div>';
    
    try {
        const response = await fetch(`${API_BASE}/calendar/external`, {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        });
        const data = await response.json();
        
        list.innerHTML = '';
        if (data.calendars && data.calendars.length > 0) {
            data.calendars.forEach(cal => {
                const div = document.createElement('div');
                div.className = 'channel-item';
                div.innerHTML = `
                    <div class="channel-info">
                        <div class="channel-name">${escapeHtml(cal.name)}</div>
                        <div class="channel-type" style="font-size: 0.8rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 200px;">${escapeHtml(cal.url)}</div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 4px;">
                            上次同步: ${formatDateTime(cal.last_sync) || '从未'}
                        </div>
                    </div>
                    <div class="channel-actions">
                        <button class="btn btn-sm btn-info" onclick="syncExternalCalendar(${cal.id})">立即同步</button>
                        <button class="btn btn-sm btn-danger" onclick="deleteExternalCalendar(${cal.id})">删除</button>
                    </div>
                `;
                list.appendChild(div);
            });
        } else {
            list.innerHTML = '<div class="empty-state" style="padding: 20px;">暂无订阅的外部日历</div>';
        }
    } catch (e) {
        list.innerHTML = `<div class="error">加载失败: ${e.message}</div>`;
    }
}

async function handleAddExternalCalendar(e) {
    e.preventDefault();
    const formData = new FormData(e.target);
    const data = {
        name: formData.get('name'),
        url: formData.get('url'),
        channel_id: formData.get('channel_id') || null
    };
    
    try {
        const response = await fetch(`${API_BASE}/calendar/external`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            },
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            showNotification('日历订阅成功，正在后台同步...', 'success');
            e.target.reset();
            loadExternalCalendars();
        } else {
            const res = await response.json();
            showNotification(res.error, 'error');
        }
    } catch (e) {
        showNotification(e.message, 'error');
    }
}

async function deleteExternalCalendar(id) {
    if (!confirm('确定要取消订阅此日历吗？已导入的任务不会被删除。')) return;
    
    try {
        const response = await fetch(`${API_BASE}/calendar/external/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        });
        if (response.ok) {
            showNotification('已取消订阅', 'success');
            loadExternalCalendars();
        }
    } catch (e) {
        showNotification(e.message, 'error');
    }
}

async function syncExternalCalendar(id) {
    try {
        const response = await fetch(`${API_BASE}/calendar/sync/${id}`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        });
        if (response.ok) {
            showNotification('同步请求已发送', 'success');
        }
    } catch (e) {
        showNotification(e.message, 'error');
    }
}