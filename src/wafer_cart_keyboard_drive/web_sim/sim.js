'use strict';
const $=id=>document.getElementById(id),client=crypto.randomUUID().replaceAll('-','');
let token='',seq=0,held=new Set(),busy=false,selected=null,current=null,message='',initialized=false;
const scene=new Booth3D($('scene'),point=>{if(selected){send('point',{name:selected,x:point[0],y:point[1]});selected=null;}},text=>{message=text;});
async function send(op,values={}){
 if(!token)return;
 try{const response=await fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json','X-Sim-Token':token},body:JSON.stringify({client,seq:++seq,op,...values}),signal:AbortSignal.timeout(1500)});const data=await response.json();if(!response.ok)throw Error(data.error||'명령 실패');message='';}
 catch(error){held.clear();message=error.message;}
}
function stop(){held.clear();send('stop');}
const keys=new Set(['w','s','a','d','q','e','up','down']);
function validKey(key){return current?.mode==='single'?['up','down'].includes(key):!['up','down'].includes(key);}
window.addEventListener('keydown',e=>{if(/INPUT|SELECT/.test(e.target.tagName))return;const key=e.key==='ArrowUp'?'up':e.key==='ArrowDown'?'down':e.key.toLowerCase();if(e.code==='Space'){e.preventDefault();stop();return;}if(key==='x'){held.clear();send('estop');return;}if(keys.has(key)&&validKey(key)){e.preventDefault();held.add(key);}});
window.addEventListener('keyup',e=>{const key=e.key==='ArrowUp'?'up':e.key==='ArrowDown'?'down':e.key.toLowerCase();if(held.delete(key)&&!held.size)stop();});
window.addEventListener('blur',stop);document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
for(const button of document.querySelectorAll('[data-key]')){
 button.addEventListener('pointerdown',e=>{e.preventDefault();if(validKey(button.dataset.key)){button.setPointerCapture(e.pointerId);held.add(button.dataset.key);}});
 for(const event of ['pointerup','pointercancel','lostpointercapture'])button.addEventListener(event,stop);
}
setInterval(async()=>{if(!held.size||busy)return;busy=true;try{await send('keys',{keys:[...held]});}finally{busy=false;}},70);
$('prepare').onclick=()=>{held.clear();send('prepare');};$('stop').onclick=stop;$('estop').onclick=()=>{held.clear();send('estop');};$('reset').onclick=()=>send('reset');
$('apply').onclick=()=>send('settings',{percent:Number($('speed').value),mode:$('mode').value,motor:Number($('motor').value)});
$('slider').oninput=()=>{$('speed').value=$('slider').value;};$('speed').oninput=()=>{$('slider').value=$('speed').value;};
$('view').onchange=()=>scene.setPreset($('view').value);$('reload').onclick=()=>scene.loadCad();
$('slam-overlay').onchange=()=>{scene.dirty=true;};
for(const b of document.querySelectorAll('[data-point]'))b.onclick=()=>{selected=b.dataset.point;message='빈 바닥을 선택하세요';};
async function poll(){
 try{if(!token)token=(await(await fetch('/api/token')).json()).token;const response=await fetch('/api/state',{cache:'no-store',signal:AbortSignal.timeout(1200)});if(!response.ok)throw Error('서버 상태 오류');current=await response.json();if(!current.pose)return;scene.update(current,null,selected);
  if(!initialized){$('speed').value=$('slider').value=current.percent;$('mode').value=current.mode;$('motor').value=current.motor;initialized=true;}
  const p=current.pose;$('pose').textContent=`X ${p[0].toFixed(3)} m / Y ${p[1].toFixed(3)} m / 방향 ${(p[2]*180/Math.PI).toFixed(1)}° / 가상 이동 ${current.distance_m.toFixed(3)} m`;
  $('wheels').textContent=current.outputs.map((v,i)=>`M${i+1}: 출력 ${v}, 가상 ENC ${current.encoder_counts[i]}`).join('  |  ');
  $('ros-status').textContent=`Gazebo ${current.gazebo?.connected?'연결':'대기'} · ROS2 ${current.ros?.connected?'연결':'대기/끊김'} · ${current.map?`가상 SLAM ${current.map.width}×${current.map.height} / ${current.map.resolution.toFixed(3)} m`:'지도 대기'} · 실제 센서 데이터 아님`;
  $('status').textContent=current.error||message||(current.latched?'비상정지/오류 잠금 · 서버 재시작':current.collision?'충돌 방지 정지 · '+current.collision:current.navigation?.enabled?'Nav2 가상 제어 · 정지 버튼으로 수동 전환':current.armed?'수동 주행':current.prepared?'수동 준비 · 키/버튼을 누르세요':'정지 · 수동 준비가 필요합니다');
  const locked=current.navigation?.enabled||current.prepared||current.armed||current.outputs.some(v=>v!==0);for(const id of ['speed','slider','mode','motor','apply','reset','prepare'])$(id).disabled=id==='prepare'?Boolean(current.navigation?.enabled):Boolean(locked);
  for(const b of document.querySelectorAll('[data-key]'))b.hidden=(current.mode==='single')!==['up','down'].includes(b.dataset.key);
 }catch(error){held.clear();$('status').textContent='연결 중단 · 자동 정지 대기 · '+error.message;}
 finally{setTimeout(poll,180);}
}
poll();
