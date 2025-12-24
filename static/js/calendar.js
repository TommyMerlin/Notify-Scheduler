(function () {
	// 容错解析 ISO/常见时间字符串/时间戳
	function parseDateFlexible(v) {
		if (!v) return null;
		if (v instanceof Date) return isNaN(v) ? null : v;
		if (typeof v === 'number') return new Date(v);
		let s = String(v).trim();
		if (/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(:\d{2})?/.test(s)) s = s.replace(/\s+/, 'T');
		if (/^\d{4}-\d{2}-\d{2}$/.test(s)) s = s + 'T00:00:00';
		const d = new Date(s);
		return isNaN(d) ? null : d;
	}

	function getAuthHeaders() {
		const headers = { 
			'Accept': 'application/json',
			'X-Requested-With': 'XMLHttpRequest'
		};
		const token = localStorage.getItem('token') || localStorage.getItem('access_token') || localStorage.getItem('jwt');
		if (token) {
			headers['Authorization'] = `Bearer ${token}`;
		}
		return headers;
	}

	async function fetchPendingTasks() {
		if (Array.isArray(window.__TASKS_CACHE) && window.__TASKS_CACHE.length) {
			console.info('[calendar] using window.__TASKS_CACHE', window.__TASKS_CACHE.length);
			return window.__TASKS_CACHE;
		}
		
		const urls = [
			'/api/tasks?page_size=300&sort_by=scheduled_time&sort_order=asc',
			'/api/tasks',
			'/api/tasks?status=pending'
		];

		for (const u of urls) {
			try {
				const res = await fetch(u, { 
					credentials: 'include', 
					headers: getAuthHeaders() 
				});
				
				if (!res.ok) {
					if (res.status === 401) console.warn('[calendar] unauthorized for', u);
					continue; 
				}

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

	function renderCalendar(year, month, tasks) {
		const grid = document.getElementById('calendarGrid');
		const monthLabel = document.getElementById('calendarMonthLabel');
		const dayPanel = document.getElementById('calendarDayTasks');
		if (!grid || !monthLabel) return;
		grid.innerHTML = '';
		monthLabel.textContent = new Date(year, month, 1).toLocaleString('zh-CN', { month: 'long', year: 'numeric' });
		if (dayPanel) {
			dayPanel.innerHTML = '';
			dayPanel.style.display = 'none';
		}

		const today = new Date();
		const todayYear = today.getFullYear();
		const todayMonth = today.getMonth();
		const todayDate = today.getDate();

		const weekdays = ['日','一','二','三','四','五','六'];
		const header = document.createElement('div'); 
		header.className = 'calendar-row calendar-weekdays';
		for (const w of weekdays) { 
			const c=document.createElement('div'); 
			c.className='calendar-cell calendar-weekday'; 
			c.textContent=w; 
			header.appendChild(c); 
		}
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

		const createEmpty = () => { 
			const c = document.createElement('div'); 
			c.className='calendar-cell calendar-day empty'; 
			return c; 
		};

		const cells = [];
		for (let i=0;i<firstWeekday;i++) cells.push(createEmpty());
		for (let d=1; d<= total; d++) {
			const cell = document.createElement('div'); 
			cell.className='calendar-cell calendar-day';
			
			if (year === todayYear && month === todayMonth && d === todayDate) {
				cell.classList.add('today');
			}
			
			const dn = document.createElement('div'); 
			dn.className='calendar-day-number'; 
			dn.textContent = String(d); 
			cell.appendChild(dn);
			
			const iso = toDateIsoOnly(new Date(year, month, d));
			cell.dataset.date = iso;
			
			const list = map[iso] || [];
			if (list.length) {
				const badge = document.createElement('div'); 
				badge.className='calendar-badge'; 
				badge.textContent = String(list.length); 
				cell.appendChild(badge);
				
				const preview = document.createElement('ul'); 
				preview.className='calendar-day-preview';
				
				let draggableCount = 0;
				for (const t of list.slice(0,3)) { 
					const li=document.createElement('li'); 
					li.textContent = t.title; 
					li.className = 'status-' + (t.status || 'pending');
					li.dataset.taskId = t.id;
					
					// 调试日志：输出每个任务的状态
					console.log('[calendar] Rendering task:', {
						id: t.id,
						title: t.title,
						status: t.status,
						isRecurring: t.isRecurring,
						willBeDraggable: !t.isRecurring && t.status === 'pending'
					});
					
					if (t.isRecurring) {
						li.classList.add('recurring');
					} else if (t.status === 'pending') {
						// ✅ 只有待发送状态的非重复任务可拖拽
						li.classList.add('draggable');
						draggableCount++;
						console.log('[calendar] Added draggable class to task:', t.id, t.title);
					}
					
					preview.appendChild(li); 
				}
				
				console.log('[calendar] Date', iso, '- Draggable tasks:', draggableCount, '/', list.slice(0,3).length);
				cell.appendChild(preview);
			}
			
			cell.addEventListener('click', (e) => {
				if (e.target.classList.contains('draggable') || e.target.closest('.draggable')) {
					return;
				}
				
				document.querySelectorAll('.calendar-day.selected').forEach(el => {
					el.classList.remove('selected');
				});
				cell.classList.add('selected');
				showDayList(iso, list);
			});
			cells.push(cell);
		}
		
		while (cells.length % 7 !== 0) cells.push(createEmpty());
		for (let i=0;i<cells.length;i+=7) {
			const row = document.createElement('div'); 
			row.className='calendar-row';
			for (let j=0;j<7;j++) row.appendChild(cells[i+j]);
			grid.appendChild(row);
		}

		// 自动展开当前日期的任务列表
		setTimeout(() => {
			const todayCell = grid.querySelector('.calendar-day.today');
			if (todayCell) {
				todayCell.classList.add('selected');
				const iso = todayCell.dataset.date;
				const list = map[iso] || [];
				showDayList(iso, list);
			}
		}, 100);

		function showDayList(iso, list) {
			if (!dayPanel) return;
			dayPanel.innerHTML = '';
			dayPanel.style.display = 'block';
			
			const h = document.createElement('h3'); 
			h.textContent = iso + ' 的任务列表'; 
			h.style.marginBottom = '12px';
			h.style.fontSize = '1.1rem';
			dayPanel.appendChild(h);

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
			list.sort((a,b) => (a.scheduled||0) - (b.scheduled||0));

			for (const t of list) {
				const row = document.createElement('div');
				row.className = 'calendar-task-row status-' + (t.status || 'pending');
				if (t.isRecurring) {
					row.classList.add('recurring');
				}
				row.style.cursor = 'pointer';
				row.dataset.taskId = String(t.id);
				
				const timeDiv = document.createElement('div');
				timeDiv.className = 'calendar-task-time';
				timeDiv.textContent = t.scheduled ? t.scheduled.toLocaleTimeString('en-GB', {hour:'2-digit', minute:'2-digit'}) : '--:--';
				
				const titleDiv = document.createElement('div');
				titleDiv.className = 'calendar-task-title';
				titleDiv.textContent = t.title;
				titleDiv.title = t.title;

				const statusDiv = document.createElement('div');
				statusDiv.className = 'calendar-task-status-label';
				const statusMap = { 'pending': '待发送', 'waiting': '等待中', 'sent': '已发送', 'failed': '失败', 'cancelled': '已取消', 'paused': '已暂停' };
				statusDiv.textContent = statusMap[t.status] || t.status;

				row.appendChild(timeDiv);
				row.appendChild(titleDiv);
				row.appendChild(statusDiv);
				
				row.addEventListener('click', function(e) {
					e.preventDefault();
					const taskId = this.dataset.taskId;
					if (taskId && typeof window.openEditTaskModal === 'function') {
						window.openEditTaskModal(taskId);
					}
				});
				
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
		const filtered = tasks; 
		filtered.sort((a,b) => a.scheduled - b.scheduled);
		window.__CALENDAR_TASKS = filtered;
		console.info('[calendar] rendering tasks:', filtered.length);
		renderCalendar(currentYear, currentMonth, filtered);
		
		// ⚠️ 关键修改：直接在这里检查并初始化拖拽，不使用 setTimeout
		console.log('[calendar] Checking for draggable items immediately after render...');
		const draggables = document.querySelectorAll('.calendar-day-preview li.draggable');
		console.log('[calendar] Found draggable items:', draggables.length);
		
		if (draggables.length === 0) {
			console.warn('[calendar] No draggable items found immediately, will retry...');
			// 延迟重试
			setTimeout(() => {
				const draggables2 = document.querySelectorAll('.calendar-day-preview li.draggable');
				console.log('[calendar] Retry: Found draggable items:', draggables2.length);
				if (draggables2.length > 0) {
					initDragAndDrop();
				} else {
					console.error('[calendar] Still no draggable items found after retry!');
				}
			}, 500);
		} else {
			initDragAndDrop();
		}
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

	window.loadCalendar = function (forceRefresh = false) {
		if (forceRefresh) {
			delete window.__TASKS_CACHE;
		}
		bindControls();
		loadAndRender();
	};

	document.addEventListener('DOMContentLoaded', () => bindControls());

	let draggedTask = null;
	let draggedElement = null;
	let draggedTaskBackup = null; // ⚠️ 新增备份变量，防止数据丢失

	function initDragAndDrop() {
		const calendarGrid = document.getElementById('calendarGrid');
		if (!calendarGrid) {
			console.warn('[calendar] Calendar grid not found');
			return;
		}
		
		if (calendarGrid._dragInitialized) {
			console.log('[calendar] Already initialized, resetting...');
			calendarGrid._dragInitialized = false;
		}

		const draggables = calendarGrid.querySelectorAll('.calendar-day-preview li.draggable');
		console.log('[calendar] initDragAndDrop: Found', draggables.length, 'draggable items');
		
		if (draggables.length === 0) {
			console.error('[calendar] No draggable items found in initDragAndDrop!');
			// 输出 DOM 结构用于调试
			console.log('[calendar] calendarGrid innerHTML sample:', calendarGrid.innerHTML.substring(0, 500));
			return;
		}
		
		draggables.forEach((item, index) => {
			// 设置拖拽属性
			item.setAttribute('draggable', 'true');
			item.draggable = true;
			
			// 强制设置样式
			item.style.cssText = 'cursor: grab !important; user-select: none; -webkit-user-select: none; -webkit-user-drag: element;';
			
			console.log(`[calendar] Setup item ${index}:`, {
				title: item.textContent,
				taskId: item.dataset.taskId,
				draggableAttr: item.getAttribute('draggable'),
				draggableProp: item.draggable,
				hasClass: item.classList.contains('draggable')
			});
			
			// 直接在元素上绑定事件
			item.ondragstart = function(e) {
				console.log('[calendar] ondragstart triggered on item', index);
				handleDragStart(e);
			};
		});

		// 全局事件监听
		calendarGrid.addEventListener('dragstart', handleDragStart, false);
		calendarGrid.addEventListener('dragend', handleDragEnd, false);
		calendarGrid.addEventListener('dragover', handleDragOver, false);
		calendarGrid.addEventListener('dragenter', handleDragEnter, false);
		calendarGrid.addEventListener('dragleave', handleDragLeave, false);
		calendarGrid.addEventListener('drop', handleDrop, false);

		calendarGrid._dragInitialized = true;
		console.log('[calendar] Drag and drop initialized successfully');
		
		// 验证
		if (draggables.length > 0) {
			const first = draggables[0];
			console.log('[calendar] First item final check:', {
				'getAttribute("draggable")': first.getAttribute('draggable'),
				'element.draggable': first.draggable,
				'can be dragged': first.draggable === true
			});
		}
	}

	function handleDragStart(e) {
		if (e.target.tagName !== 'LI') return;
		const taskItem = e.target;
		
		if (taskItem.classList.contains('recurring')) {
			e.preventDefault();
			return;
		}

		if (!taskItem.classList.contains('draggable')) {
			e.preventDefault();
			return;
		}

		const taskId = taskItem.dataset.taskId;
		if (!taskId) return;

		const allTasks = window.__CALENDAR_TASKS || [];
		const taskData = allTasks.find(t => t.id.toString() === taskId.toString());
		
		if (!taskData) return;

		draggedTask = taskData;
		draggedElement = taskItem;
		draggedTaskBackup = taskData; // ⚠️ 备份任务数据
		
		console.log('[calendar] Drag started, task data:', {
			id: taskData.id,
			title: taskData.title,
			hasRaw: !!taskData.raw
		});
		
		e.dataTransfer.effectAllowed = 'move';
		e.dataTransfer.setData('text/plain', taskItem.textContent);
		
		setTimeout(() => {
			if (draggedElement) {
				draggedElement.classList.add('dragging');
			}
		}, 0);
	}

	function handleDragEnd(e) {
		if (draggedElement) {
			draggedElement.classList.remove('dragging');
		}
		
		document.querySelectorAll('.calendar-day.drag-over').forEach(day => {
			day.classList.remove('drag-over');
		});
		
		// ⚠️ 不要立即清空，等 drop 完成后再清空
		console.log('[calendar] Drag ended, keeping task data for drop');
	}

	function handleDragOver(e) {
		if (e.preventDefault) {
			e.preventDefault();
		}
		e.dataTransfer.dropEffect = 'move';
		return false;
	}

	function handleDragEnter(e) {
		const calendarDay = e.target.closest('.calendar-day');
		if (calendarDay && !calendarDay.classList.contains('empty') && (draggedTask || draggedTaskBackup)) {
			calendarDay.classList.add('drag-over');
		}
	}

	function handleDragLeave(e) {
		const calendarDay = e.target.closest('.calendar-day');
		if (calendarDay && e.target === calendarDay) {
			calendarDay.classList.remove('drag-over');
		}
	}

	async function handleDrop(e) {
		if (e.stopPropagation) e.stopPropagation();
		e.preventDefault();

		// 使用备份数据（如果主数据丢失）
		const task = draggedTask || draggedTaskBackup;

		console.log('[calendar] Drop event triggered, task state:', {
			draggedTask: draggedTask,
			draggedTaskBackup: draggedTaskBackup,
			finalTask: task
		});

		const calendarDay = e.target.closest('.calendar-day');
		if (!calendarDay || calendarDay.classList.contains('empty') || !task) {
			console.warn('[calendar] Invalid drop:', {
				hasCalendarDay: !!calendarDay,
				isEmpty: calendarDay?.classList.contains('empty'),
				hasTask: !!task
			});
			draggedTask = null;
			draggedElement = null;
			draggedTaskBackup = null;
			return false;
		}

		calendarDay.classList.remove('drag-over');

		const targetDate = calendarDay.dataset.date;
		if (!targetDate) {
			console.error('[calendar] Target date not found');
			draggedTask = null;
			draggedElement = null;
			draggedTaskBackup = null;
			return false;
		}

		if (!task.scheduled) {
			console.error('[calendar] Invalid task:', task);
			if (typeof showNotification === 'function') {
				showNotification('任务数据无效，请刷新页面后重试', 'error');
			}
			draggedTask = null;
			draggedElement = null;
			draggedTaskBackup = null;
			return false;
		}

		const originalDateTime = task.scheduled;
		const [targetYear, targetMonth, targetDay] = targetDate.split('-').map(Number);
		
		const targetDateTime = new Date(
			targetYear,
			targetMonth - 1,
			targetDay,
			originalDateTime.getHours(),
			originalDateTime.getMinutes(),
			originalDateTime.getSeconds()
		);

		const originalDate = toDateIsoOnly(originalDateTime);
		if (targetDate === originalDate) {
			draggedTask = null;
			draggedElement = null;
			draggedTaskBackup = null;
			return false;
		}

		const originalTimeStr = originalDateTime.toLocaleTimeString('zh-CN', {
			hour: '2-digit',
			minute: '2-digit',
			hour12: false
		});
		
		const formattedDate = formatDate(targetDateTime);
		
		// ⚠️ 使用更清晰的格式化消息（支持换行）
		const confirmed = await showConfirmDialog({
			title: '确认调整任务日期',
			message: `将任务「${task.title}」\n\n从 ${originalDate} → ${targetDate}\n\n⏰ 时间保持：${originalTimeStr}`,
			confirmText: '确认调整',
			cancelText: '取消'
		});

		if (!confirmed) {
			draggedTask = null;
			draggedElement = null;
			draggedTaskBackup = null;
			return false;
		}

		try {
			const localDateTimeString = formatDateTimeForAPI(targetDateTime);
			
			const updateData = {
				scheduled_time: localDateTimeString
			};

			if (task.raw) {
				updateData.title = task.raw.title || task.title;
				updateData.content = task.raw.content || '';
				
				if (task.raw.config) {
					updateData.config = task.raw.config;
				}
				
				if (task.raw.channel_config) {
					updateData.channel_config = task.raw.channel_config;
				}
			} else {
				updateData.title = task.title || '';
				updateData.content = task.content || '';
				console.warn('[calendar] task.raw is missing, using top-level properties');
			}

			console.log('[calendar] Updating task with data:', updateData);

			const response = await fetch(`/api/tasks/${task.id}`, {
				method: 'PUT',
				headers: {
					'Content-Type': 'application/json',
					...getAuthHeaders()
				},
				credentials: 'include',
				body: JSON.stringify(updateData)
			});

			if (!response.ok) {
				const error = await response.json().catch(() => ({ error: '更新失败' }));
				throw new Error(error.error || '更新失败');
			}

			// ⚠️ 使用自定义通知
			if (typeof showNotification === 'function') {
				showNotification(`✅ 任务已调整到 ${targetDate} ${originalTimeStr}`, 'success');
			}
			
			delete window.__TASKS_CACHE;
			loadAndRender();
			
		} catch (error) {
			console.error('[calendar] Error updating task:', error);
			
			// ⚠️ 使用自定义通知
			if (typeof showNotification === 'function') {
				showNotification(`调整失败：${error.message}`, 'error');
			}
		} finally {
			// ⚠️ 无论成功失败，都要清空拖拽状态
			draggedTask = null;
			draggedElement = null;
			draggedTaskBackup = null;
		}

		return false;
	}

	// 格式化日期显示（用于UI显示）
	function formatDate(date) {
		const year = date.getFullYear();
		const month = String(date.getMonth() + 1).padStart(2, '0');
		const day = String(date.getDate()).padStart(2, '0');
		const hours = String(date.getHours()).padStart(2, '0');
		const minutes = String(date.getMinutes()).padStart(2, '0');
		return `${year}-${month}-${day} ${hours}:${minutes}`;
	}

	// ⚠️ 新增：格式化日期时间为API所需的格式（本地时间，不是UTC）
	function formatDateTimeForAPI(date) {
		const year = date.getFullYear();
		const month = String(date.getMonth() + 1).padStart(2, '0');
		const day = String(date.getDate()).padStart(2, '0');
		const hours = String(date.getHours()).padStart(2, '0');
		const minutes = String(date.getMinutes()).padStart(2, '0');
		const seconds = String(date.getSeconds()).padStart(2, '0');
		return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
	}

})();
