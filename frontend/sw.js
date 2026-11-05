/* Cache only the public application shell. API responses and account data are never cached here. */
'use strict';
const CACHE='xueya-public-shell-20261105-course-connection-v9';
self.addEventListener('install',event=>event.waitUntil((async()=>{
  const response=await fetch('./',{cache:'reload'});
  if(!response.ok)throw Error('Shell unavailable');
  const html=await response.clone().text(),cache=await caches.open(CACHE);
  await cache.put(new URL('./',self.location).href,response);
  const paths=[...html.matchAll(/(?:src|href)="([^"#]+\.(?:js|css|svg))"/g)].map(match=>new URL(match[1],self.location).href);
  paths.push(new URL('assets/material-symbols-outlined.woff2',self.location).href);
  await cache.addAll([...new Set(paths.filter(url=>new URL(url).origin===self.location.origin))]);
  await self.skipWaiting();
})()));
self.addEventListener('activate',event=>event.waitUntil((async()=>{
  for(const name of await caches.keys())if(name.startsWith('xueya-public-shell-')&&name!==CACHE)await caches.delete(name);
  await self.clients.claim();
})()));
self.addEventListener('fetch',event=>{
  const request=event.request,url=new URL(request.url);
  if(request.method!=='GET'||url.origin!==self.location.origin||url.pathname.startsWith('/api/'))return;
  const navigation=request.mode==='navigate',asset=/\.(?:js|css|svg|woff2?|png|jpg|webp)$/.test(url.pathname);
  if(!navigation&&!asset)return;
  event.respondWith((async()=>{
    const cache=await caches.open(CACHE);
    try{
      const response=await fetch(request);
      if(response.ok&&response.type!=='opaque')await cache.put(navigation?new URL('./',self.location).href:request,response.clone());
      return response;
    }catch(error){
      const saved=await cache.match(navigation?new URL('./',self.location).href:request);
      if(saved)return saved;
      throw error;
    }
  })());
});
