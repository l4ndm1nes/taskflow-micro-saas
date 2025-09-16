import { makeAuth } from "./auth.js";

const BASE           = import.meta.env.VITE_API_BASE;
const COGNITO_DOMAIN = import.meta.env.VITE_COGNITO_DOMAIN;
const CLIENT_ID      = import.meta.env.VITE_COGNITO_CLIENT_ID;
const REDIRECT_URI   = import.meta.env.VITE_COGNITO_REDIRECT;

const $   = (id) => document.getElementById(id);
const out = $("out");
const who = $("whoami");

$("base").value = BASE || "";

const log = (obj) => out.textContent = (typeof obj === "string") ? obj : JSON.stringify(obj, null, 2);
const authHeaders = () => {
  const t = $("token").value.trim();
  return t ? { Authorization: `Bearer ${t}` } : {};
};

$("paste").onclick = async () => {
  try { $("token").value = (await navigator.clipboard.readText()).trim(); applyWhoAmI(); }
  catch { alert("Cannot read clipboard. Paste manually."); }
};

function decodeJwt(token) {
  try {
    const [, payload] = token.split(".");
    return JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
  } catch { return null; }
}
function applyWhoAmI() {
  const idt = $("token").value.trim();
  const payload = idt ? decodeJwt(idt) : null;
  if (payload?.email || payload?.["cognito:username"]) {
    who.hidden = false;
    who.textContent = payload.email || payload["cognito:username"];
  } else {
    who.hidden = true;
    who.textContent = "";
  }
}

const Auth = makeAuth({
  domain: COGNITO_DOMAIN,
  clientId: CLIENT_ID,
  redirectUri: REDIRECT_URI,
  scopes: ["openid", "email", "profile"],
});

$("signin").onclick = () => Auth.signIn();
$("signout").onclick = () => {
  $("token").value = "";
  applyWhoAmI();
  Auth.signOut();
};

// handle callback or restore token
(async function onLoad() {
  try {
    const handled = await Auth.handleRedirectCallback();
    if (handled && handled.id_token) {
      $("token").value = handled.id_token;
      applyWhoAmI();
      log({ token_response: handled, note: "ID Token placed into JWT field" });
      return;
    }
  } catch (e) {
    log(String(e));
  }
  const saved = Auth.getIdToken();
  if (saved) {
    $("token").value = saved;
    applyWhoAmI();
  }
})();

// --- API actions ---
$("btnHealth").onclick = async () => {
  try { const r = await fetch(`${$("base").value}/health`); log(await r.json()); }
  catch (e) { log(String(e)); }
};

$("btnMe").onclick = async () => {
  try { const r = await fetch(`${$("base").value}/me`, { headers: authHeaders() }); log(await r.json()); }
  catch (e) { log(String(e)); }
};

$("btnList").onclick = async () => {
  try {
    const url = new URL(`${$("base").value}/tasks`);
    url.searchParams.set("limit", String(Number($("limit").value || 5)));
    const r = await fetch(url, { headers: authHeaders() });
    log(await r.json());
  } catch (e) { log(String(e)); }
};

$("btnUpload").onclick = async () => {
  const file = $("file").files[0];
  if (!file) return alert("Pick a file");

  const base = $("base").value;
  try {
    const pres = await fetch(`${base}/files/presign`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ filename: file.name, content_type: file.type || "application/octet-stream" })
    }).then(r => r.json());

    const putResp = await fetch(pres.upload_url, {
      method: "PUT",
      headers: { "Content-Type": pres.content_type || file.type || "application/octet-stream" },
      body: file
    });
    if (!putResp.ok) throw new Error(`S3 PUT failed: ${putResp.status} ${await putResp.text()}`);

    const created = await fetch(`${base}/tasks`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ client_token: crypto.randomUUID(), file_key: pres.object_key })
    }).then(r => r.json());

    // Автоматически заполняем task ID для удобства
    if (created.task && created.task.task_id) {
      $("taskId").value = created.task.task_id;
    }

    log({ presign: pres, created });
  } catch (e) {
    log(String(e));
  }
};

$("btnGetTask").onclick = async () => {
  const taskId = $("taskId").value.trim();
  if (!taskId) return alert("Enter Task ID");
  
  try {
    const r = await fetch(`${$("base").value}/tasks/${taskId}`, { headers: authHeaders() });
    const result = await r.json();
    log(result);
  } catch (e) {
    log(String(e));
  }
};

$("btnDownloadOriginal").onclick = async () => {
  const taskId = $("taskId").value.trim();
  if (!taskId) return alert("Enter Task ID");
  
  const base = $("base").value;
  const btn = $("btnDownloadOriginal");
  const originalText = btn.textContent;
  
  try {
    btn.textContent = "Downloading...";
    btn.disabled = true;
    
    // Получаем информацию о задаче
    const taskResp = await fetch(`${base}/tasks/${taskId}`, { headers: authHeaders() });
    const taskData = await taskResp.json();
    
    if (!taskData.task) {
      return log({ error: "Task not found" });
    }
    
    const task = taskData.task;
    if (!task.file_key) {
      return log({ error: "No file_key found for this task" });
    }
    
    // Получаем presigned URL для скачивания исходного файла
    const downloadResp = await fetch(`${base}/files/download`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ file_key: task.file_key })
    });
    
    const downloadData = await downloadResp.json();
    if (downloadData.download_url) {
      // Скачиваем исходный файл
      const fileResp = await fetch(downloadData.download_url);
      const blob = await fileResp.blob();
      
      // Извлекаем имя файла из file_key
      const fileName = task.file_key.split('/').pop().split('-').slice(1).join('-') || `task-${taskId}-original`;
      
      // Создаем URL для blob и скачиваем
      const blobUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = blobUrl;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      
      // Освобождаем память
      window.URL.revokeObjectURL(blobUrl);
      
      log({ message: "Original file downloaded", file_key: task.file_key, fileName });
    } else {
      log({ error: "Failed to get download URL", response: downloadData });
    }
  } catch (e) {
    log(String(e));
  } finally {
    btn.textContent = originalText;
    btn.disabled = false;
  }
};

$("btnDownloadResult").onclick = async () => {
  const taskId = $("taskId").value.trim();
  if (!taskId) return alert("Enter Task ID");
  
  const base = $("base").value;
  const btn = $("btnDownloadResult");
  const originalText = btn.textContent;
  
  try {
    btn.textContent = "Downloading...";
    btn.disabled = true;
    // Сначала получаем информацию о задаче
    const taskResp = await fetch(`${base}/tasks/${taskId}`, { headers: authHeaders() });
    const taskData = await taskResp.json();
    
    if (!taskData.task) {
      return log({ error: "Task not found" });
    }
    
    const task = taskData.task;
    if (task.status !== "DONE") {
      return log({ error: `Task status is ${task.status}, not DONE. Cannot download result.` });
    }
    
    if (!task.result_key) {
      return log({ error: "No result_key found for this task" });
    }
    
    // Получаем presigned URL для скачивания
    const downloadResp = await fetch(`${base}/files/download`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ file_key: task.result_key })
    });
    
    const downloadData = await downloadResp.json();
    if (downloadData.download_url) {
      // Скачиваем файл через fetch и создаем blob
      const fileResp = await fetch(downloadData.download_url);
      const blob = await fileResp.blob();
      
      // Создаем URL для blob и скачиваем
      const blobUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = blobUrl;
      link.download = `task-${taskId}-result.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      
      // Освобождаем память
      window.URL.revokeObjectURL(blobUrl);
      
      log({ message: "Download completed", result_key: task.result_key, stats: task.stats });
    } else {
      log({ error: "Failed to get download URL", response: downloadData });
    }
  } catch (e) {
    log(String(e));
  } finally {
    btn.textContent = originalText;
    btn.disabled = false;
  }
};

$("btnViewResult").onclick = async () => {
  const taskId = $("taskId").value.trim();
  if (!taskId) return alert("Enter Task ID");
  
  const base = $("base").value;
  try {
    // Сначала получаем информацию о задаче
    const taskResp = await fetch(`${base}/tasks/${taskId}`, { headers: authHeaders() });
    const taskData = await taskResp.json();
    
    if (!taskData.task) {
      return log({ error: "Task not found" });
    }
    
    const task = taskData.task;
    if (task.status !== "DONE") {
      return log({ error: `Task status is ${task.status}, not DONE. Cannot view result.` });
    }
    
    if (!task.result_key) {
      return log({ error: "No result_key found for this task" });
    }
    
    // Получаем presigned URL для просмотра
    const downloadResp = await fetch(`${base}/files/download`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ file_key: task.result_key })
    });
    
    const downloadData = await downloadResp.json();
    if (downloadData.download_url) {
      // Открываем в новой вкладке для просмотра
      window.open(downloadData.download_url, '_blank');
      log({ message: "Result opened in new tab", result_key: task.result_key, stats: task.stats });
    } else {
      log({ error: "Failed to get download URL", response: downloadData });
    }
  } catch (e) {
    log(String(e));
  }
};

// --- Tasks Table ---
let autoRefreshInterval = null;

function formatDate(isoString) {
  if (!isoString) return '-';
  return new Date(isoString).toLocaleString();
}

function formatFileKey(fileKey) {
  if (!fileKey) return '-';
  const parts = fileKey.split('/');
  const fileName = parts[parts.length - 1];
  return fileName.split('-').slice(1).join('-') || fileName;
}

function renderTasksTable(tasks) {
  const container = $("tasksTable");
  
  if (!tasks || tasks.length === 0) {
    container.innerHTML = '<p>No tasks found. Upload a file to create your first task!</p>';
    return;
  }
  
  const table = `
    <table class="tasks-table">
      <thead>
        <tr>
          <th>Task ID</th>
          <th>File</th>
          <th>Status</th>
          <th>Created</th>
          <th>Processed</th>
          <th>Stats</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        ${tasks.map(task => `
          <tr>
            <td class="task-id">${task.task_id || task.sk}</td>
            <td>${formatFileKey(task.file_key)}</td>
            <td class="status-${(task.status || 'pending').toLowerCase()}">${task.status || 'PENDING'}</td>
            <td>${formatDate(task.created_at)}</td>
            <td>${formatDate(task.processed_at)}</td>
            <td>
              ${task.stats ? `${task.stats.byte_count} bytes, ${task.stats.line_count} lines` : '-'}
            </td>
            <td>
              <button class="btn-small" onclick="viewTask('${task.task_id || task.sk}')">View</button>
              ${task.status === 'DONE' ? `
                <button class="btn-small" onclick="downloadOriginal('${task.task_id || task.sk}')">📄 File</button>
                <button class="btn-small" onclick="downloadResult('${task.task_id || task.sk}')">📊 Result</button>
              ` : ''}
            </td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
  
  container.innerHTML = table;
}

async function refreshTasks() {
  const btn = $("btnRefreshTasks");
  const originalText = btn.textContent;
  
  try {
    btn.textContent = "Loading...";
    btn.disabled = true;
    
    const response = await fetch(`${$("base").value}/tasks?limit=10`, { 
      headers: authHeaders() 
    });
    const data = await response.json();
    
    if (data.items) {
      renderTasksTable(data.items);
      log({ message: `Loaded ${data.items.length} tasks`, timestamp: new Date().toISOString() });
    } else {
      log({ error: "Failed to load tasks", response: data });
    }
  } catch (e) {
    log({ error: String(e) });
  } finally {
    btn.textContent = originalText;
    btn.disabled = false;
  }
}

function toggleAutoRefresh() {
  const btn = $("btnAutoRefresh");
  
  if (autoRefreshInterval) {
    clearInterval(autoRefreshInterval);
    autoRefreshInterval = null;
    btn.textContent = "Auto-refresh: OFF";
    btn.classList.remove("auto-refresh-on");
  } else {
    autoRefreshInterval = setInterval(refreshTasks, 3000);
    btn.textContent = "Auto-refresh: ON";
    btn.classList.add("auto-refresh-on");
    refreshTasks();
  }
}

window.viewTask = (taskId) => {
  $("taskId").value = taskId;
  $("btnGetTask").click();
};

window.downloadOriginal = (taskId) => {
  $("taskId").value = taskId;
  $("btnDownloadOriginal").click();
};

window.downloadResult = (taskId) => {
  $("taskId").value = taskId;
  $("btnDownloadResult").click();
};

$("btnRefreshTasks").onclick = refreshTasks;
$("btnAutoRefresh").onclick = toggleAutoRefresh;
