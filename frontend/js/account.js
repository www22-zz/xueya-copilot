/* One shared local account; the server owns sessions and password verification. */
(() => {
'use strict';
const e=v=>window.XueyaRich.escape(String(v)),errors={USERNAME_TAKEN:'这个账号已注册，请换一个账号或返回登录。',PASSWORD_FORMAT:'密码需要在8–16个字符之间，并包含字母和数字。',PASSWORD_MISMATCH:'两次输入的密码不一致。',ACCOUNT_NOT_CONFIGURED:'请先点击下方注册，创建空间账号。',LOGIN_INVALID:'账号或密码不正确。',LOGIN_THROTTLED:'尝试次数较多，请等一分钟再试。',PASSWORD_LENGTH:'密码需为6至256个字符。',INVALID_USERNAME:'账号需为3至40位字母、数字、点、横线或下划线。',ACCOUNT_ALREADY_CONFIGURED:'共享空间已经配置，请返回登录。',LOGIN_REQUIRED:'登录已失效，请刷新并重新登录。'};
let status=null;
async function request(path,body,protectedAction=false){let token='';if(protectedAction){const b=await fetch('/api/platform/bootstrap',{cache:'no-store'});const data=await b.json();if(!b.ok)throw Error(errors[data.error]||'无法读取登录状态');token=data.token;}
const response=await fetch('/api/account/'+path,{method:body?'POST':'GET',cache:'no-store',credentials:'same-origin',headers:{...(body?{'Content-Type':'application/json'}:{}),...(token?{'X-Xueya-Token':token}:{})},...(body?{body:JSON.stringify(body)}:{})});const value=await response.json().catch(()=>({}));if(!response.ok){const error=Error(response.status===404?'当前后台尚未加载账号功能，请重启学涯服务后再试。':errors[value.error]||'操作未完成，请稍后再试。');error.status=response.status;throw error;}return value;}
const fields=(change=false)=>`${change?'<label>当前密码<input name="currentPassword" type="password" autocomplete="current-password" maxlength="256" required></label>':'<label>团队账号<input name="username" value="xueya-team" autocomplete="username" minlength="3" maxlength="40" required></label>'}<label>${change?'新密码':'密码'}<input name="password" type="password" autocomplete="${change?'new-password':'current-password'}" minlength="${change?'6':'1'}" maxlength="256" required></label>`;
function identify(){window.XueyaAccountId=status?.username||'local';try{localStorage.setItem('xueya-last-account',window.XueyaAccountId);}catch{}}
async function refresh(){if(location.protocol==='file:')return;try{status=await request('status');identify();draw();}catch(error){const root=document.querySelector('#accountSettingsBody');if(root)root.textContent=error.message;}}
function draw(){const root=document.querySelector('#accountSettingsBody');if(!root||!status)return;root.innerHTML=status.configured?`<p>已登录团队账号 <strong>${e(status.username)}</strong></p><p>团队共用同一学习空间；不同电脑不会自动同步。</p><details><summary>修改团队密码</summary><form class="account-form" data-account-action="password">${fields(true)}<button class="button button-blue button-small">保存新密码</button></form></details><button type="button" class="button button-outline button-small" data-account-logout style="margin-top:24px">退出登录</button>`:`<p>当前为本地学习空间。设置团队账号后，重新打开时需要登录。</p><form class="account-form" data-account-action="setup">${fields()}<small>密码至少6个字符，三位成员共用此账号。</small><button class="button button-blue button-small">启用团队账号</button></form>`;root.insertAdjacentHTML('beforeend','<p class="account-message" role="status" data-account-message></p>');}
function validate(form){
 const p=form.elements.password,c=form.elements.confirmPassword;
 if(!c)return form.reportValidity();
 const good=p.value.length>=8&&p.value.length<=16&&/[A-Za-z]/.test(p.value)&&/[0-9]/.test(p.value);
 p.setAttribute('aria-invalid',String(!good));c.setAttribute('aria-invalid',String(c.value!==p.value));
 form.querySelector('[data-password-error]').textContent=good?'':'! 密码需要在8–16个字符之间，并包含字母和数字';
 form.querySelector('[data-confirm-error]').textContent=c.value===p.value?'':'! 两次输入的密码不一致';
 return good&&c.value===p.value&&form.reportValidity();
}
document.addEventListener('input',event=>{const f=event.target.closest('[data-account-action="register"]');if(f&&['password','confirmPassword'].includes(event.target.name))validate(f);});
document.addEventListener('submit',async event=>{const form=event.target.closest('[data-account-action]');if(!form)return;event.preventDefault();if(!validate(form))return;const button=form.querySelector('button[type=submit],button:not([type])'),root=form.closest('dialog'),message=root.querySelector('[data-account-message]');button.disabled=true;message.textContent='正在处理…';try{const action=form.dataset.accountAction;await request(action,Object.fromEntries(new FormData(form)),!['login','register'].includes(action));form.reset();if(['login','register'].includes(action)){root.close();root.remove();status=await request('status');identify();loginResolve?.();loginResolve=null;}else{await refresh();root.querySelector('[data-account-message]').textContent='账号设置已保存。';}}catch(error){message.textContent=error.message;message.setAttribute('role','alert');}finally{button.disabled=false;}});
document.addEventListener('click',async event=>{if(!event.target.closest('[data-account-logout]'))return;const b=event.target.closest('button');b.disabled=true;try{await request('logout',{},true);try{localStorage.removeItem('xueya-last-account');}catch{}location.reload();}catch(error){b.disabled=false;document.querySelector('[data-account-message]').textContent=error.message;}});
let loginResolve=null;
function showLogin(register=false){
 let dialog=document.querySelector('#accountLoginDialog');
 if(!dialog){dialog=document.createElement('dialog');dialog.id='accountLoginDialog';dialog.className='account-login';document.body.append(dialog);}
 dialog.setAttribute('aria-label',register?'注册学涯账号':'登录学涯');
 dialog.innerHTML=`<button type="button" class="auth-close" aria-label="关闭登录">×</button><img src="assets/mark.svg" width="42" height="42" alt="学涯"><p class="eyebrow">学习，从这里继续</p><h1>${register?'创建你的学习账号':'欢迎回到学涯'}</h1><p>${register?'把资料、思考和理解，一点点积累起来。':'登录后，进入你的学习空间。'}</p><form class="account-form" data-account-action="${register?'register':'login'}" novalidate><label>账号<input name="username" placeholder="请输入账号" autocomplete="username" minlength="3" maxlength="40" required></label><small>3–40位字母、数字、点、横线或下划线</small><label>密码<input name="password" type="password" placeholder="请输入密码" autocomplete="${register?'new-password':'current-password'}" maxlength="${register?'16':'256'}" required></label>${register?'<small>密码需要在8–16个字符之间，包括字母和数字</small><small class="auth-error" data-password-error></small><label>确认密码<input name="confirmPassword" type="password" placeholder="请再次确认密码" autocomplete="new-password" maxlength="16" required></label><small class="auth-error" data-confirm-error></small>':''}<button type="submit" class="button button-blue">${register?'注册并进入学习空间':'登录'}</button></form><p class="account-message" role="status" data-account-message></p><p class="auth-switch">${register?'已有账号？':'没有账号？'}<button type="button" data-auth-switch>${register?'点击登录':'点击注册'}</button></p><small class="auth-space-note">账号用于此设备上的共享学习空间，资料与学习记录保留在当前服务中。</small>`;
 dialog.querySelector('[data-auth-switch]').onclick=()=>showLogin(!register);
 dialog.querySelector('.auth-close').onclick=()=>{dialog.close();history.replaceState(null,'','#home');};
 dialog.addEventListener('cancel',()=>history.replaceState(null,'','#home'),{once:true});
 if(!dialog.open)dialog.showModal();dialog.querySelector('[name=username]').focus();
}
async function gate(){
 if(location.protocol==='file:')return;
 try{status=await request('status');}catch(error){if(error.status===404)return;status=null;}
 if(status&&typeof status.configured!=='boolean')return;
 if(status?.authenticated&&(status.configured||status.username)){identify();return;}
 if(status?.configured&&!status.authenticated&&/^#space\/(?:practice|review)(?:\/|$)/.test(location.hash)){try{const cached=localStorage.getItem('xueya-last-account');if(cached&&localStorage.getItem('xueya-practice-v1:'+cached)){window.XueyaAccountId=cached;return;}}catch{}}
 if(!status){try{window.XueyaAccountId=localStorage.getItem('xueya-last-account')||'local';}catch{}return;}
 await new Promise(resolve=>{
 loginResolve=resolve;
 document.addEventListener('click',event=>{const link=event.target.closest('a[href^="#space/"]');if(!link||!loginResolve)return;event.preventDefault();history.replaceState(null,'',link.getAttribute('href'));showLogin();},true);
 window.addEventListener('hashchange',()=>{if(loginResolve&&location.hash.startsWith('#space/'))showLogin();});
 if(location.hash.startsWith('#space/'))showLogin();
 });
}
window.XueyaAccount={refresh,async login(){await new Promise(resolve=>{loginResolve=resolve;showLogin();});location.reload();}};window.XueyaAccountReady=gate();
})();
