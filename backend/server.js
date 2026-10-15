'use strict';

const http=require('node:http');
const {loadConfig}=require('./config.js');
const {createApp}=require('./app.js');
const {sanitizeSources:normalizeSources}=require('../shared/contracts/index.js');
const {sources}=require('../shared/fixtures/course.js');

const config=loadConfig();
const server=http.createServer(createApp({config}));
// Compatibility export retained for existing callers.
const sanitizeSources=input=>normalizeSources(input,sources);

if(require.main===module)server.listen(config.port,'127.0.0.1',()=>console.log('Xueya Copilot running at http://127.0.0.1:'+config.port));
module.exports={server,sanitizeSources};
