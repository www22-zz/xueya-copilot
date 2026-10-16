'use strict';

const fs=require('node:fs');
const path=require('node:path');

function loadConfig(root=path.resolve(__dirname,'..')){
  const envPath=path.join(root,'.env');
  if(fs.existsSync(envPath)){
    for(const line of fs.readFileSync(envPath,'utf8').split(/\r?\n/)){
      const match=line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/i);
      if(match&&!process.env[match[1]])process.env[match[1]]=match[2].replace(/^["']|["']$/g,'');
    }
  }
  return{
    root,port:Number(process.env.PORT||4173),
    platform:{enabled:true,dataDir:path.resolve(process.env.XUEYA_DATA_DIR||path.join(root,'.xueya-data')),userId:'local-user',apiSlots:Math.max(1,Math.min(8,Number(process.env.API_MAX_CONCURRENT)||2))},
    agent:{toolTimeoutMs:Math.max(1000,Math.min(10000,Number(process.env.MCP_TOOL_TIMEOUT_MS)||5000))},
    ai:{apiKey:process.env.MIMO_API_KEY||'',baseURL:process.env.MIMO_BASE_URL||'https://api.xiaomimimo.com/v1',model:process.env.MIMO_MODEL||'mimo-v2.6-flash'}
  };
}

module.exports={loadConfig};
