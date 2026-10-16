'use strict';
/** API-only AI architecture. CPU slots are ordinary parsing, never local model inference. */
function createResources({apiSlots=2,cpuSlots=2}={}){
  const active={api:0,cpu:0};
  return{
    choose(requested){if(!['cpu','api'].includes(requested))throw new Error('RESOURCE_UNSUPPORTED');return requested;},
    acquire(resource){const limit=resource==='api'?apiSlots:cpuSlots;if(active[resource]>=limit)return null;active[resource]++;let released=false;return()=>{if(!released){released=true;active[resource]--;}};},
    stats:()=>({active:{...active},limits:{api:apiSlots,cpu:cpuSlots},inference:'external-api-only'})
  };
}
module.exports={createResources};
