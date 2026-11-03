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
const referenceInput=$('#referenceImage');
const referenceDrop=$('#referenceDrop');
const showReference=(file)=>{
  $('#referenceName').textContent=file?`${file.name} · ${(file.size/1024/1024).toFixed(2)} MB`:'';
  const preview=$('#referencePreview');
  const clear=$('#clearReference');
  if(file){preview.src=URL.createObjectURL(file);preview.classList.remove('hidden');clear.classList.remove('hidden');}else{preview.classList.add('hidden');preview.removeAttribute('src');clear.classList.add('hidden');}
};
referenceInput.onchange=()=>showReference(referenceInput.files[0]);
referenceDrop.ondragover=e=>{e.preventDefault();referenceDrop.classList.add('dragover');};
referenceDrop.ondragleave=()=>referenceDrop.classList.remove('dragover');
referenceDrop.ondrop=e=>{e.preventDefault();referenceDrop.classList.remove('dragover');if(e.dataTransfer.files.length){referenceInput.files=e.dataTransfer.files;showReference(referenceInput.files[0]);}};
$('#clearReference').onclick=()=>{referenceInput.value='';showReference(null);};
function fileBase64(file){return new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(String(r.result).split(',')[1]);r.onerror=reject;r.readAsDataURL(file);});}
$('#send').onclick = async () => {
  const message = $('#prompt').value.trim(); if (!message) return;
  const mode = document.querySelector('input[name=mode]:checked').value;
  const referenceFile=referenceInput.files[0];
  addMessage('user', message); $('#prompt').value = ''; $('#send').disabled = true;
  addMessage('assistant', referenceFile?'正在由 Qwen 分析参考图、材质与建模参数…':'正在由 Qwen 生成规格并连接 Rhino…');
  try {
    let url='/api/chat',body={message,mode};
    if(referenceFile){
      if(referenceFile.size>20*1024*1024)throw new Error('参考图不能超过 20 MB');
      url='/api/reference-model';body={message,filename:referenceFile.name,mime_type:referenceFile.type,data_base64:await fileBase64(referenceFile),execute:$('#executeReference').checked};
    }
    const res = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    const data = await res.json(); if (!res.ok) throw new Error(data.detail || '请求失败');
    messages.lastChild.remove();
    if(referenceFile && data.modeling_started===false){
      const missing=data.reference_analysis?.critical_dimensions_missing||[];
      addMessage('assistant',missing.length?`参考图分析完成，但缺少关键尺寸：${missing.join('、')}。未写入 Rhino。`:'参考图分析完成，当前仅分析未建模。');
      details.classList.remove('hidden');details.innerHTML=`<details open><summary>参考图分析</summary><pre>${escapeHtml(JSON.stringify(data.reference_analysis,null,2))}</pre></details>`;
    }
    else if (mode === 'qa' && !referenceFile) addMessage('assistant', data.answer.text);
    else {
      addMessage('assistant', data.validation.passed ? '建模与验收通过。' : '建模已停止：验收仍未通过。');
      details.classList.remove('hidden');
      details.innerHTML = `${data.reference_analysis?`<details open><summary>参考图形态与材质分析</summary><pre>${escapeHtml(JSON.stringify(data.reference_analysis,null,2))}</pre></details>`:''}<details open><summary>ModelingSpec</summary><pre>${escapeHtml(JSON.stringify(data.modeling_spec,null,2))}</pre></details>
        <details open><summary>验证结果 · ${data.validation.summary.passed}/${data.validation.summary.checks}</summary><pre>${escapeHtml(JSON.stringify(data.validation,null,2))}</pre></details>
        <details><summary>Qwen 工具计划与修复记录</summary><pre>${escapeHtml(JSON.stringify({plan:data.qwen_plan,repairs:data.repairs},null,2))}</pre></details>`;
    }
  } catch (e) { messages.lastChild.remove(); addMessage('assistant', `错误：${e.message}`); }
  finally { $('#send').disabled = false; refreshStatus(); }
};
$('#stop').onclick = async () => { await fetch('/api/stop', {method:'POST'}); addMessage('assistant', '已请求停止后续 Qwen/MCP 轮次。'); };
$('#undo').onclick = async () => { const r=await fetch('/api/undo',{method:'POST'}); addMessage('assistant', r.ok===false?'撤销失败':'已请求 Rhino 撤销上一轮。'); };
refreshStatus(); setInterval(refreshStatus, 10000);
