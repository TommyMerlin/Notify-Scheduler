(function () {
	// 容错解析 ISO/常见时间字符串/时间戳
	function parseDateFlexible(v) {
		if (!v) return null;
		if (v instanceof Date) return isNaN(v) ? null : v;
		if (typeof v === 'number') return new Date(v); // 支持时间戳
		let s = String(v).trim();
		// 如果像 "2023-12-01 09:00:00" -> "2023-12-01T09:00:00"
		if (/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(:\d{2})?/.test(s)) s = s.replace(/\s+/, 'T');
		// 如果没有时区但看起来是日期 (YYYY-MM-DD) -> treat as local midnight by adding T00:00:00
		if (/^\d{4}-\d{2}-\d{2}$/.test(s)) s = s + 'T00:00:00';
		const d = new Date(s);
		return isNaN(d) ? null : d;
	}

	// 辅助：获取认证头（尝试自动获取 Token）
	function getAuthHeaders() {
		const headers = { 
			'Accept': 'application/json',
			'X-Requested-With': 'XMLHttpRequest' // 某些后端需要此头来处理 AJAX
		};
		// 尝试从 localStorage 获取 token (常见命名)
		const token = localStorage.getItem('token') || localStorage.getItem('access_token') || localStorage.getItem('jwt');
		if (token) {
			headers['Authorization'] = `Bearer ${token}`;
		}
		return headers;
	}

	// 尝试从多个端点拉取任务
	async function fetchPendingTasks() {
		if (Array.isArray(window.__TASKS_CACHE) && window.__TASKS_CACHE.length) {
			console.info('[calendar] using window.__TASKS_CACHE', window.__TASKS_CACHE.length);
			return window.__TASKS_CACHE;
		}
		
		const urls = [
			// 移除 status=pending 以获取所有任务，增大 page_size
			'/api/tasks?page_size=300&sort_by=scheduled_time&sort_order=asc',
			'/api/tasks',
			'/api/tasks?status=pending' // 作为后备
		];

		for (const u of urls) {
			try {
				// 使用 include 凭证模式并附加可能的 token 头
				const res = await fetch(u, { 
					credentials: 'include', 
					headers: getAuthHeaders() 
				});
				
				if (!res.ok) {
					if (res.status === 401) console.warn('[calendar] unauthorized for', u);
					continue; 
				}

				// === 关键：一旦获得 200 OK，必须在此处处理完毕 ===
				
				let data;
				try {
					const text = await res.text();
					if (!text) {
						console.warn('[calendar] empty response body from', u);
						return []; 
					}
					data = JSON.parse(text);
				} catch (e) {
					console.error('[calendar] json parse error from', u, e);
					return []; 
				}

				console.log('[calendar] loaded data from', u, data);

				// 策略：深度查找数组
				let tasks = null;
				if (Array.isArray(data)) {
					tasks = data;
				} else if (data && typeof data === 'object') {
					const fields = ['tasks', 'items', 'data', 'results', 'records', 'rows', 'list', 'objects', 'content'];
					for (const f of fields) {
						if (Array.isArray(data[f])) {
							tasks = data[f];
							break;
						}
					}
					if (!tasks && data.data && typeof data.data === 'object') {
						if (Array.isArray(data.data)) {
							tasks = data.data;
						} else {
							for (const f of fields) {
								if (Array.isArray(data.data[f])) {
									tasks = data.data[f];
									break;
								}
							}
						}
					}
					if (!tasks) {
						for (const k in data) {
							if (Array.isArray(data[k])) {
								tasks = data[k];
								break;
							}
						}
					}
				}

				if (tasks) return tasks;
				
				console.warn('[calendar] 200 OK but no array found in', u, 'Stopping attempts.');
				return []; 

			} catch (e) {
				console.warn('[calendar] fetch network error', e);
			}
		}
		return [];
	}

	function toDateIsoOnly(d) {
		if (!d) return null;
		const dt = new Date(d);
		if (isNaN(dt)) return null;
		return dt.getFullYear() + '-' + String(dt.getMonth()+1).padStart(2,'0') + '-' + String(dt.getDate()).padStart(2,'0');
	}

	function normalizeTasks(raw) {
		if (!Array.isArray(raw)) return [];
		return raw.map(t => {
			const keys = ['next_scheduled_time','next_run','scheduled_time','scheduledAt','scheduled_at','scheduledTime','scheduled','run_at','time'];
			let dt = null;
			for (const k of keys) {
				if (t && t[k]) { dt = t[k]; break; }
			}
			if (!dt && t && t.next && (t.next.scheduled || t.next.run_at)) dt = t.next.scheduled || t.next.run_at;
			const parsed = parseDateFlexible(dt);
			
			// 检测是否为重复任务
			const isRecurring = !!(t && (
				t.is_recurring || 
				t.isRecurring || 
				t.recurring || 
				t.cron_expression || 
				t.cronExpression || 
				t.recurrence || 
				t.repeat
			));
			
			return {
				id: t && (t.id ?? t.taskId ?? t._id) || '',
				title: t && (t.title ?? t.name ?? t.summary) || ('任务 ' + (t && (t.id || t.taskId) ? ('#' + (t.id || t.taskId)) : '')),
				scheduled: parsed,
				status: (t && (t.status ?? t.state) || '').toString().toLowerCase(),
				isRecurring: isRecurring,
				raw: t
			};
		}).filter(t => t.scheduled && !isNaN(t.scheduled));
	}

	// 渲染日历
	function renderCalendar(year, month, tasks) {
		const grid = document.getElementById('calendarGrid');
		const monthLabel = document.getElementById('calendarMonthLabel');
		const dayPanel = document.getElementById('calendarDayTasks');
		if (!grid || !monthLabel) return;
		grid.innerHTML = '';
		monthLabel.textContent = new Date(year, month, 1).toLocaleString('zh-CN', { month: 'long', year: 'numeric' });
		// 清空任务列表并隐藏
		if (dayPanel) {
			dayPanel.innerHTML = '';
			dayPanel.style.display = 'none';
		}

		// 获取今天的日期信息
		const today = new Date();
		const todayYear = today.getFullYear();
		const todayMonth = today.getMonth();
		const todayDate = today.getDate();

		// weekday header
		const weekdays = ['日','一','二','三','四','五','六'];
		const header = document.createElement('div'); header.className = 'calendar-row calendar-weekdays';
		for (const w of weekdays) { const c=document.createElement('div'); c.className='calendar-cell calendar-weekday'; c.textContent=w; header.appendChild(c); }
		grid.appendChild(header);

		const start = new Date(year, month, 1);
		const total = new Date(year, month + 1, 0).getDate();
		const firstWeekday = start.getDay();

		const map = {};
		for (const t of tasks) {
			const iso = toDateIsoOnly(t.scheduled);
			if (!iso) continue;
			(map[iso] = map[iso]||[]).push(t);
		}

		const createEmpty = () => { const c = document.createElement('div'); c.className='calendar-cell calendar-day empty'; return c; };

		const cells = [];
		for (let i=0;i<firstWeekday;i++) cells.push(createEmpty());
		for (let d=1; d<= total; d++) {
			const cell = document.createElement('div'); 
			cell.className='calendar-cell calendar-day';
			
			// 判断是否是今天
			if (year === todayYear && month === todayMonth && d === todayDate) {
				cell.classList.add('today');
			}
			
			const dn = document.createElement('div'); dn.className='calendar-day-number'; dn.textContent = String(d); cell.appendChild(dn);
			const iso = toDateIsoOnly(new Date(year, month, d));
			const list = map[iso] || [];
			if (list.length) {
				const badge = document.createElement('div'); badge.className='calendar-badge'; badge.textContent = String(list.length); cell.appendChild(badge);
				const preview = document.createElement('ul'); preview.className='calendar-day-preview';
				for (const t of list.slice(0,3)) { 
					const li=document.createElement('li'); 
					li.textContent = t.title; 
					// 添加状态类名和重复任务类名
					li.className = 'status-' + (t.status || 'pending');
					if (t.isRecurring) {
						li.classList.add('recurring');
					}
					preview.appendChild(li); 
				}
				cell.appendChild(preview);
			}
			// 为所有日期（包括无任务的）添加点击事件
			cell.addEventListener('click', () => {
				// 移除所有日期的选中状态
				document.querySelectorAll('.calendar-day.selected').forEach(el => {
					el.classList.remove('selected');
				});
				// 为当前日期添加选中状态
				cell.classList.add('selected');
				showDayList(iso, list);
			});
			cells.push(cell);
		}
		while (cells.length % 7 !== 0) cells.push(createEmpty());
		for (let i=0;i<cells.length;i+=7) {
			const row = document.createElement('div'); row.className='calendar-row';
			for (let j=0;j<7;j++) row.appendChild(cells[i+j]);
			grid.appendChild(row);
		}

		function showDayList(iso, list) {
			if (!dayPanel) return;
			dayPanel.innerHTML = '';
			dayPanel.style.display = 'block'; // 显示任务列表区域
			
			const h = document.createElement('h3'); 
			h.textContent = iso + ' 的任务列表'; 
			h.style.marginBottom = '12px';
			h.style.fontSize = '1.1rem';
			dayPanel.appendChild(h);

			// 如果没有任务，显示提示信息
			if (!list || list.length === 0) {
				const emptyMsg = document.createElement('div');
				emptyMsg.style.padding = '20px';
				emptyMsg.style.textAlign = 'center';
				emptyMsg.style.color = 'var(--text-muted, #999)';
				emptyMsg.style.fontSize = '0.95rem';
				emptyMsg.textContent = '📭 这一天暂无任务安排';
				dayPanel.appendChild(emptyMsg);
				return;
			}

			const container = document.createElement('div'); 
			container.className='calendar-task-list';
			
			// 按时间排序
			list.sort((a,b) => (a.scheduled||0) - (b.scheduled||0));

			for (const t of list) {
				const row = document.createElement('div');
				// 添加状态类名、重复任务类名和可点击样式
				row.className = 'calendar-task-row status-' + (t.status || 'pending');
				if (t.isRecurring) {
					row.classList.add('recurring');
				}
				row.style.cursor = 'pointer';
				row.dataset.taskId = String(t.id);
				
				const timeDiv = document.createElement('div');
				timeDiv.className = 'calendar-task-time';
				// 强制 24小时制 HH:mm 对齐
				timeDiv.textContent = t.scheduled ? t.scheduled.toLocaleTimeString('en-GB', {hour:'2-digit', minute:'2-digit'}) : '--:--';
				
				const titleDiv = document.createElement('div');
				titleDiv.className = 'calendar-task-title';
				titleDiv.textContent = t.title;
				titleDiv.title = t.title; // tooltip

				// 状态标签
				const statusDiv = document.createElement('div');
				statusDiv.className = 'calendar-task-status-label';
				const statusMap = { 'pending': '待发送', 'waiting': '等待中', 'sent': '已发送', 'failed': '失败', 'cancelled': '已取消' };
				statusDiv.textContent = statusMap[t.status] || t.status;

				row.appendChild(timeDiv);
				row.appendChild(titleDiv);
				row.appendChild(statusDiv);
				
				// 为整行添加点击事件，点击任意位置都能编辑
				row.addEventListener('click', function(e) {
					e.preventDefault();
					const taskId = this.dataset.taskId;
					if (taskId && typeof window.openEditTaskModal === 'function') {
						window.openEditTaskModal(taskId);
					}
				});
				
				// 添加 hover 效果，增强交互提示
				row.addEventListener('mouseenter', function() {
					this.style.backgroundColor = 'rgba(102, 126, 234, 0.08)';
					this.style.transform = 'translateX(2px)';
					this.style.transition = 'all 0.2s ease';
				});
				row.addEventListener('mouseleave', function() {
					this.style.backgroundColor = '';
					this.style.transform = '';
				});
				
				container.appendChild(row);
			}
			dayPanel.appendChild(container);
		}
	}

	let currentYear = (new Date()).getFullYear();
	let currentMonth = (new Date()).getMonth();
	let controlsBound = false;

	async function loadAndRender() {
		const raw = await fetchPendingTasks();
		const tasks = normalizeTasks(raw);
		// 显示所有拉取到的任务（不按时间过滤，防止因时区问题隐藏任务）
		const filtered = tasks; 
		filtered.sort((a,b) => a.scheduled - b.scheduled);
		// 缓存以便其它脚本（若有）使用
		window.__CALENDAR_TASKS = filtered;
		console.info('[calendar] rendering tasks:', filtered.length);
		renderCalendar(currentYear, currentMonth, filtered);
	}

	function bindControls() {
		if (controlsBound) return;
		controlsBound = true;
		const prev = document.getElementById('prevMonth');
		const next = document.getElementById('nextMonth');
		if (prev) prev.addEventListener('click', () => {
			currentMonth--;
			if (currentMonth < 0) { currentMonth = 11; currentYear--; }
			loadAndRender();
		});
		if (next) next.addEventListener('click', () => {
			currentMonth++;
			if (currentMonth > 11) { currentMonth = 0; currentYear++; }
			loadAndRender();
		});
	}

	// 对外接口
	window.loadCalendar = function (forceRefresh = false) {
		// 如果强制刷新，清除缓存
		if (forceRefresh) {
			delete window.__TASKS_CACHE;
			console.log('[calendar] Cache cleared, forcing refresh');
		}
		bindControls();
		loadAndRender();
	};

	// 自动绑定但不自动加载
	document.addEventListener('DOMContentLoaded', () => bindControls());
})();
