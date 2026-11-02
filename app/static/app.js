const $ = (s) => document.querySelector(s);
const messages = $('#messages');
const details = $('#details');

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}
function addMessage(role, text) {
  const node = document.createElement('article');
  node.className = `message ${role}`;
  node.innerHTML = `<strong>${role === 'user' ? '你' : 'Qwen Agent'}</strong><p>${escapeHtml(text)}</p>`;
  messages.appendChild(node);
  node.scrollIntoView({behavior:'smooth'});
}
async function refreshStatus() {
  try {
    const data = await fetch('/api/status').then(r => r.json());
    $('#status').innerHTML = [
      ['Qwen', data.qwen?.ok], ['MCP', data.mcp?.connected], ['Rhino', data.rhino?.connected]
    ].map(([name, ok]) => `<span class="pill ${ok?'ok':'bad'}">${name} ${ok?'在线':'离线'}</span>`).join('');
  } catch { $('#status').innerHTML = '<span class="pill bad">服务离线</span>'; }
}
$('#send').onclick = async () => {
  const message = $('#prompt').value.trim(); if (!message) return;
  const mode = document.querySelector('input[name=mode]:checked').value;
  addMessage('user', message); $('#prompt').value = ''; $('#send').disabled = true;
  addMessage('assistant', '正在由 Qwen 生成规格并连接 Rhino…');
  try {
    const res = await fetch('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message, mode})});
    const data = await res.json(); if (!res.ok) throw new Error(data.detail || '请求失败');
    messages.lastChild.remove();
    if (mode === 'qa') addMessage('assistant', data.answer.text);
    else {
      addMessage('assistant', data.validation.passed ? '建模与验收通过。' : '建模已停止：验收仍未通过。');
      details.classList.remove('hidden');
      details.innerHTML = `<details open><summary>ModelingSpec</summary><pre>${escapeHtml(JSON.stringify(data.modeling_spec,null,2))}</pre></details>
        <details open><summary>验证结果 · ${data.validation.summary.passed}/${data.validation.summary.checks}</summary><pre>${escapeHtml(JSON.stringify(data.validation,null,2))}</pre></details>
        <details><summary>Qwen 工具计划与修复记录</summary><pre>${escapeHtml(JSON.stringify({plan:data.qwen_plan,repairs:data.repairs},null,2))}</pre></details>`;
    }
  } catch (e) { messages.lastChild.remove(); addMessage('assistant', `错误：${e.message}`); }
  finally { $('#send').disabled = false; refreshStatus(); }
};
$('#stop').onclick = async () => { await fetch('/api/stop', {method:'POST'}); addMessage('assistant', '已请求停止后续 Qwen/MCP 轮次。'); };
$('#undo').onclick = async () => { const r=await fetch('/api/undo',{method:'POST'}); addMessage('assistant', r.ok===false?'撤销失败':'已请求 Rhino 撤销上一轮。'); };
refreshStatus(); setInterval(refreshStatus, 10000);
