// HOD dashboard JS - minimal, self-contained development wiring
(function () {
	const base = '';
	const qs = s => document.querySelector(s);
	const qsa = s => Array.from(document.querySelectorAll(s));

	// tiny helpers
	function toast(msg, ms = 3000) {
		const t = qs('#toast');
		t.textContent = msg; t.hidden = false;
		setTimeout(() => t.hidden = true, ms);
	}

	function getAuth() {
		const token = localStorage.getItem('access_token') || '';
		return token ? { 'Authorization': 'Bearer ' + token } : {};
	}

	function parseJSONSafe(r) { try { return r.json(); } catch (e) { return Promise.resolve({}); } }

	// Content-Disposition filename parser
	function filenameFromDisposition(header) {
		if (!header) return null;
		// filename*=utf-8''... or filename="..."
		const fnameStar = /filename\*=([^;]+)/i.exec(header);
		if (fnameStar) {
			let val = fnameStar[1].trim();
			const parts = val.split("''");
			if (parts.length === 2) {
				try { return decodeURIComponent(parts[1]); } catch (e) { return parts[1]; }
			}
			return val;
		}
		const fname = /filename="?([^";]+)"?/i.exec(header);
		if (fname) return fname[1];
		return null;
	}

	// download and preserve filename
	async function downloadFile(fileId) {
		try {
			const res = await fetch(`${base}/api/files/${fileId}/download`, { headers: getAuth() });
			if (!res.ok) throw new Error('Download failed');
			const disposition = res.headers.get('Content-Disposition') || res.headers.get('content-disposition');
			const fname = filenameFromDisposition(disposition) || `file-${fileId}`;
			const blob = await res.blob();
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a'); a.href = url; a.download = fname; document.body.appendChild(a);
			a.click(); a.remove(); URL.revokeObjectURL(url);
			toast('Download started');
		} catch (err) { console.error(err); toast('Download error'); }
	}

	// show modal helpers (accessible)
	function showModal(id, setup) {
		const modal = qs(`#${id}`); if (!modal) return;
		modal.setAttribute('aria-hidden', 'false');
		const focusable = modal.querySelectorAll('button, [href], input, textarea, select');
		const first = focusable[0]; if (first) first.focus();
		modal._restore = document.activeElement;
		if (typeof setup === 'function') setup(modal);
	}
	function hideModal(id) { const m = qs(`#${id}`); if (!m) return; m.setAttribute('aria-hidden', 'true'); if (m._restore) m._restore.focus(); }

	// selection & bulk actions
	const selection = new Set();
	let currentUser = { id: null, role: null };
	let lastBulkResult = null; // store last bulk result (updated, errors, status, comment)

	function updateBulkToolbar() {
		const n = selection.size; const tb = qs('#bulkToolbar'); const info = qs('#bulkInfo');
		if (n > 0) { tb.hidden = false; info.textContent = `${n} selected`; } else { tb.hidden = true; info.textContent = '0 selected'; }
	}

	// Client-side transition map (mirror of backend)
	const transitions = {
		'submitted': ['acknowledged', 'pending', 'escalated'],
		'acknowledged': ['pending', 'escalated'],
		'pending': ['approved', 'rejected', 'escalated'],
		'approved': ['archived', 'escalated'],
		'rejected': ['submitted', 'escalated'],
		'escalated': ['pending', 'approved', 'archived'],
	};

	function canPerform(actorRole, actorId, receiverId, currentStatus, requestedStatus, comment) {
		if (requestedStatus === currentStatus) return { ok: true };
		if (actorRole === 'Admin') {
			if ((requestedStatus === 'rejected' || requestedStatus === 'escalated') && !comment) return { ok: false, type: 'comment_required' };
			return { ok: true };
		}
		const allowed = transitions[currentStatus] || [];
		if (!allowed.includes(requestedStatus)) return { ok: false, type: 'invalid' };
		if (requestedStatus === 'acknowledged') {
			if (actorId !== receiverId) return { ok: false, type: 'forbidden' };
			return { ok: true };
		}
		if (requestedStatus === 'approved' || requestedStatus === 'rejected') {
			if (actorRole !== 'HOD' && actorId !== receiverId) return { ok: false, type: 'forbidden' };
			if (requestedStatus === 'rejected' && !comment) return { ok: false, type: 'comment_required' };
			return { ok: true };
		}
		if (requestedStatus === 'escalated') {
			if (actorRole !== 'HOD' && actorRole !== 'Admin' && actorId !== receiverId) return { ok: false, type: 'forbidden' };
			if (!comment) return { ok: false, type: 'comment_required' };
			return { ok: true };
		}
		if (actorId === receiverId || actorRole === 'HOD') return { ok: true };
		return { ok: false, type: 'forbidden' };
	}

	function renderInbox(rows) {
		const tbody = qs('#inboxBody'); tbody.innerHTML = '';
		rows.forEach(r => {
			const tr = document.createElement('tr');
			tr.dataset.id = r.workflow_id || r.id || r.workflowId || r.file_id; // flexible

			const receiverId = r.receiver_id || r.receiverId || r.receiver || null;
			const status = (r.status || 'submitted').toString();

			const cb = document.createElement('input'); cb.type = 'checkbox'; cb.addEventListener('change', e => {
				if (e.target.checked) selection.add(tr.dataset.id); else selection.delete(tr.dataset.id);
				updateBulkToolbar();
			});

			const td0 = document.createElement('td'); td0.appendChild(cb);
			const td1 = document.createElement('td'); td1.textContent = r.file_name || r.name || 'file';
			const td2 = document.createElement('td'); td2.textContent = r.sender_name || r.from || r.dept || '-';
			const td3 = document.createElement('td'); td3.textContent = new Date(r.submitted_at || r.created_at || Date.now()).toLocaleString();
			const td4 = document.createElement('td'); td4.innerHTML = `<span class="status">${status}</span>`;
			const td5 = document.createElement('td');

			const view = document.createElement('button'); view.className = 'btn ghost'; view.textContent = 'View'; view.addEventListener('click', () => {
				qs('#modalTitle').textContent = r.file_name || r.name || 'File';
				qs('#modalBody').innerHTML = `<p><strong>From:</strong> ${td2.textContent}</p><p><strong>Submitted:</strong> ${td3.textContent}</p><p><strong>Status:</strong> ${td4.textContent}</p>`;
				qs('#modalDownload').onclick = () => downloadFile(r.file_id || r.fileId || r.id);
				showModal('fileModal');
			});

			const approve = document.createElement('button'); approve.className = 'btn primary'; approve.textContent = 'Approve';
			const reject = document.createElement('button'); reject.className = 'btn warn'; reject.textContent = 'Reject';
			const escalate = document.createElement('button'); escalate.className = 'btn ghost'; escalate.textContent = 'Escalate';

			// Decide whether to show action buttons based on client-side rules
			const canApprove = canPerform(currentUser.role, currentUser.id, receiverId, status, 'approved', '');
			const canReject = canPerform(currentUser.role, currentUser.id, receiverId, status, 'rejected', '');
			const canEscalate = canPerform(currentUser.role, currentUser.id, receiverId, status, 'escalated', '');

			if (canApprove.ok) { approve.addEventListener('click', () => singleUpdate(tr.dataset.id, 'approved', '')); }
			else { approve.disabled = true; approve.title = 'Not allowed'; }

			if (canReject.ok) {
				reject.addEventListener('click', () => {
					qs('#actionModalTitle').textContent = 'Reject file';
					qs('#actionModalMessage').textContent = 'Provide reason for rejection (required)';
					qs('#actionComment').value = '';
					showModal('actionModal');
					qs('#actionConfirm').onclick = () => {
						singleUpdate(tr.dataset.id, 'rejected', qs('#actionComment').value || '');
						hideModal('actionModal');
					};
				});
			} else { reject.disabled = true; reject.title = 'Not allowed'; }

			if (canEscalate.ok) {
				escalate.addEventListener('click', () => {
					qs('#actionModalTitle').textContent = 'Escalate file';
					qs('#actionModalMessage').textContent = 'Provide reason for escalation (required)';
					qs('#actionComment').value = '';
					showModal('actionModal');
					qs('#actionConfirm').onclick = () => {
						singleUpdate(tr.dataset.id, 'escalated', qs('#actionComment').value || '');
						hideModal('actionModal');
					};
				});
			} else { escalate.disabled = true; escalate.title = 'Not allowed'; }

			td5.append(view, approve, reject, escalate);

			tr.append(td0, td1, td2, td3, td4, td5);
			tbody.appendChild(tr);
		});
	}

	// single update (supports optional comment)
	async function singleUpdate(id, status, comment = '') {
		try {
			const res = await fetch(`${base}/api/workflows/${id}`, { method: 'PUT', headers: Object.assign({ 'Content-Type': 'application/json' }, getAuth()), body: JSON.stringify({ status, comment }) });
			const j = await res.json().catch(() => ({}));
			if (!res.ok) {
				const msg = j.error || j.message || 'Update failed';
				toast(msg);
				return;
			}
			toast('Updated');
			loadInbox(); loadStats();
		} catch (err) { console.error(err); toast('Update failed'); }
	}

	// helper to set bulk busy state (spinner + disable actions)
	function setBulkBusy(isBusy, text) {
		const prog = qs('#bulkProgress');
		const textEl = qs('#bulkProgressText');
		const btns = [qs('#bulkApprove'), qs('#bulkReject'), qs('#bulkClear')];
		if (isBusy) {
			if (prog) prog.hidden = false;
			if (textEl && text) textEl.textContent = text;
			btns.forEach(b => { if (b) b.disabled = true; });
		} else {
			if (prog) prog.hidden = true;
			if (textEl) textEl.textContent = 'Working...';
			btns.forEach(b => { if (b) b.disabled = false; });
		}
	}

	// bulk update with results modal. ids === array implies this is a retry for those ids
	async function doBulk(status, comment = '', ids = null) {
		const idsToUse = Array.isArray(ids) ? ids : Array.from(selection);
		if (!idsToUse.length) return toast('No items selected');
		// increment attempt counter only for explicit retries
		const isRetry = Array.isArray(ids);
		// show spinner
		setBulkBusy(true, isRetry ? 'Retrying failed items...' : 'Processing...');
		try {
			const res = await fetch(`${base}/api/workflows/bulk`, { method: 'PUT', headers: Object.assign({ 'Content-Type': 'application/json' }, getAuth()), body: JSON.stringify({ workflow_ids: idsToUse, status, comment }) });
			const j = await res.json().catch(() => ({}));
			// store last result for retry if needed and keep attempt count
			const prevAttempts = (lastBulkResult && lastBulkResult.attempts) || 0;
			const attempts = isRetry ? (prevAttempts + 1) : prevAttempts;
			lastBulkResult = { updated: j.updated || [], errors: j.errors || [], status, comment, attempts };
			if (res.ok) {
				toast(`Bulk ${status} applied`);
				// clear selection only if the call originated from current selection
				if (!Array.isArray(ids)) {
					selection.clear(); updateBulkToolbar();
				}
				loadInbox(); loadStats(); hideModal('bulkConfirm');
				// show results if provided
				if (lastBulkResult && (lastBulkResult.updated.length || lastBulkResult.errors.length)) {
					renderBulkResults(lastBulkResult);
				}
			} else {
				toast(j.error || 'Bulk failed');
				if (lastBulkResult && lastBulkResult.errors.length) {
					renderBulkResults(lastBulkResult);
				}
			}
			return { ok: res.ok, result: lastBulkResult };
		} catch (err) {
			console.error(err); toast('Bulk action error'); return { ok: false, result: null };
		} finally { setBulkBusy(false); }
	}

	function renderBulkResults(bulkResult) {
		const body = qs('#bulkResultsBody');
		let html = `<p>Updated: ${(bulkResult.updated || []).length}</p>`;
		if (bulkResult.errors && bulkResult.errors.length) {
			html += '<h4>Errors</h4><ul>' + bulkResult.errors.map(e => `<li>${e.id}: ${e.error}</li>`).join('') + '</ul>';
		}
		body.innerHTML = html;
		// show retry button when there are errors
		const retryBtn = qs('#bulkRetry');
		if (bulkResult.errors && bulkResult.errors.length) {
			retryBtn.hidden = false;
			retryBtn.disabled = false;
			const attempts = bulkResult.attempts || 0;
			retryBtn.textContent = attempts ? `Retry failed (attempt ${attempts})` : 'Retry failed';
			retryBtn.onclick = async function () {
				const failedIds = bulkResult.errors.map(e => e.id);
				// if we've retried multiple times, ask for confirmation
				if (attempts >= 2) {
					const ok = window.confirm(`You have retried ${attempts} time(s). Retrying again may still fail. Continue?`);
					if (!ok) return;
				}
				retryBtn.disabled = true; retryBtn.textContent = 'Retrying...';
				const r = await doBulk(bulkResult.status, bulkResult.comment || '', failedIds);
				// after retry, render new results (r.result)
				if (r && r.result) {
					renderBulkResults(r.result);
				}
				retryBtn.disabled = false;
			};
		} else {
			retryBtn.hidden = true;
		}
		showModal('bulkResults');
	}

	// load routines
	async function loadStats() {
		try {
			const res = await fetch(`${base}/api/staff/stats`, { headers: getAuth() });
			const j = await res.json();
			qs('#inboxCount').textContent = j.inbox_count ?? '-';
			qs('#pendingCount').textContent = j.pending_count ?? '-';
			qs('#processedToday').textContent = j.processed_today ?? '-';
			qs('#overdueCount').textContent = j.overdue_count ?? '-';
		} catch (e) { console.warn('stats', e) }
	}

	async function loadInbox() {
		try {
			const res = await fetch(`${base}/api/documents/inbox`, { headers: getAuth() });
			const j = await res.json();
			renderInbox(Array.isArray(j) ? j : (j.items || []));
		} catch (e) { console.warn('inbox', e); }
	}

	async function loadFiles() {
		try {
			const res = await fetch(`${base}/api/staff/files`, { headers: getAuth() });
			const j = await res.json();
			const tbody = qs('#filesBody'); tbody.innerHTML = '';
			(Array.isArray(j) ? j : (j.items || [])).forEach(f => {
				const tr = document.createElement('tr');
				const name = document.createElement('td'); name.textContent = f.file_name || f.name;
				const up = document.createElement('td'); up.textContent = new Date(f.uploaded_at || f.created_at || Date.now()).toLocaleString();
				const st = document.createElement('td'); st.textContent = f.status || '';
				const act = document.createElement('td');
				const dl = document.createElement('button'); dl.className = 'btn ghost'; dl.textContent = 'Download'; dl.addEventListener('click', () => downloadFile(f.file_id || f.id));
				act.appendChild(dl);
				tr.append(name, up, st, act);
				tbody.appendChild(tr);
			});
		} catch (e) { console.warn('files', e); }
	}

	// UI wiring
	function wire() {
		qsa('.nav-btn').forEach(b => b.addEventListener('click', e => {
			qsa('.nav-btn').forEach(n => n.classList.remove('active'));
			b.classList.add('active');
			const s = b.dataset.section; qsa('.panel').forEach(p => p.classList.remove('active'));
			qs(`#${s}`).classList.add('active');
			// Reload data when switching to specific sections
			if (s === 'inbox') {
				loadInbox();
				if (typeof loadDocumentInbox === 'function') loadDocumentInbox();
			}
			if (s === 'files') loadFiles();
		}));

		qs('#selectAll').addEventListener('change', e => {
			const checked = e.target.checked; qsa('#inboxBody input[type=checkbox]').forEach(cb => { cb.checked = checked; const tr = cb.closest('tr'); if (checked) selection.add(tr.dataset.id); else selection.delete(tr.dataset.id); }); updateBulkToolbar();
		});

		qs('#bulkApprove').addEventListener('click', () => {
			qs('#bulkMessage').textContent = `Approve ${selection.size} item(s)?`;
			showModal('bulkConfirm');
			qs('#confirmBulkDo').onclick = () => doBulk('approved', qs('#bulkComment').value || '');
		});
		qs('#bulkReject').addEventListener('click', () => {
			qs('#bulkMessage').textContent = `Reject ${selection.size} item(s)?`;
			showModal('bulkConfirm');
			qs('#confirmBulkDo').onclick = () => doBulk('rejected', qs('#bulkComment').value || '');
		});
		qs('#bulkClear').addEventListener('click', () => { selection.clear(); qsa('#inboxBody input[type=checkbox]').forEach(cb => cb.checked = false); updateBulkToolbar(); });

		// modal dismiss
		qsa('.modal [data-dismiss]').forEach(el => el.addEventListener('click', e => { const modal = e.target.closest('.modal'); if (modal) modal.setAttribute('aria-hidden', 'true'); }));
		qsa('.modal-close').forEach(b => b.addEventListener('click', e => { const m = e.target.closest('.modal'); m && m.setAttribute('aria-hidden', 'true'); }));

		qs('#logoutBtn').addEventListener('click', () => { localStorage.removeItem('token'); location.href = '/'; });
	}

	// init
	function init() {
		wire(); loadStats(); loadInbox(); loadFiles();
		// show user and store role/id for client-side action gating
		fetch(`${base}/api/me`, { headers: getAuth() }).then(r => r.json()).then(j => {
			qs('#userMini').textContent = j.username || (j.email || 'Me');
			currentUser.id = j.id || null; currentUser.role = j.role || null;
		}).catch(() => { });
	}

	document.addEventListener('DOMContentLoaded', init);

})();
