'use strict';
const fs=require('node:fs'),path=require('node:path');
const {DatabaseSync}=require('node:sqlite');
const MIGRATIONS=[`
CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE courses(user_id TEXT NOT NULL,id TEXT NOT NULL,name TEXT NOT NULL,archived INTEGER NOT NULL DEFAULT 0,version INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(user_id,id));
CREATE TABLE entities(user_id TEXT NOT NULL,course_id TEXT NOT NULL,kind TEXT NOT NULL,id TEXT NOT NULL,version INTEGER NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,deleted INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(user_id,course_id,kind,id));
CREATE TABLE revisions(user_id TEXT NOT NULL,course_id TEXT NOT NULL,kind TEXT NOT NULL,id TEXT NOT NULL,version INTEGER NOT NULL,data TEXT NOT NULL,at TEXT NOT NULL,PRIMARY KEY(user_id,course_id,kind,id,version));
CREATE TABLE workspaces(user_id TEXT PRIMARY KEY,version INTEGER NOT NULL,data TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE imports(user_id TEXT NOT NULL,hash TEXT NOT NULL,backup TEXT NOT NULL,workspace_version INTEGER NOT NULL,at TEXT NOT NULL,PRIMARY KEY(user_id,hash));
CREATE TABLE audits(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,course_id TEXT NOT NULL,action_id TEXT NOT NULL UNIQUE,data TEXT NOT NULL,at TEXT NOT NULL);
CREATE TABLE receipts(user_id TEXT NOT NULL,course_id TEXT NOT NULL,action_id TEXT NOT NULL,receipt TEXT NOT NULL,PRIMARY KEY(user_id,course_id,action_id));
CREATE TABLE jobs(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,course_id TEXT NOT NULL,type TEXT NOT NULL,input TEXT NOT NULL,resource TEXT NOT NULL,status TEXT NOT NULL,progress TEXT NOT NULL DEFAULT '{}',checkpoint TEXT NOT NULL DEFAULT '{}',result TEXT,error TEXT,attempts INTEGER NOT NULL DEFAULT 0,max_attempts INTEGER NOT NULL,idempotency_key TEXT NOT NULL,lease_owner TEXT,lease_until INTEGER,available_at INTEGER NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(user_id,course_id,type,idempotency_key));
CREATE INDEX jobs_queue ON jobs(status,available_at,created_at);
CREATE TABLE job_events(seq INTEGER PRIMARY KEY AUTOINCREMENT,job_id TEXT NOT NULL,event TEXT NOT NULL,at TEXT NOT NULL);
CREATE TABLE invocations(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,course_id TEXT NOT NULL,status TEXT NOT NULL,provider TEXT NOT NULL,request_hash TEXT NOT NULL,at TEXT NOT NULL,updated_at TEXT NOT NULL);
`, `ALTER TABLE invocations ADD COLUMN usage_json TEXT;
ALTER TABLE invocations ADD COLUMN billing_status TEXT NOT NULL DEFAULT 'not_reported';`,
`CREATE TABLE confirmations(id TEXT PRIMARY KEY,data TEXT NOT NULL);`];
function openDatabase(filename){
  if(filename!==':memory:')fs.mkdirSync(path.dirname(path.resolve(filename)),{recursive:true});
  const db=new DatabaseSync(filename);db.exec('PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000;');
  const version=db.prepare('PRAGMA user_version').get().user_version;if(version>MIGRATIONS.length){db.close();throw new Error('DATABASE_NEWER_THAN_APP');}
  for(let i=version;i<MIGRATIONS.length;i++){
    db.exec('BEGIN IMMEDIATE');try{db.exec(MIGRATIONS[i]);db.exec('PRAGMA user_version='+(i+1));db.exec('COMMIT');}catch(e){db.exec('ROLLBACK');db.close();throw e;}
  }
  return db;
}
let savepointId=0;
function transaction(db,fn){const nested=db.isTransaction,name='tx_'+(++savepointId);db.exec(nested?'SAVEPOINT '+name:'BEGIN IMMEDIATE');try{const value=fn();if(value?.then)throw new Error('ASYNC_TRANSACTION_FORBIDDEN');db.exec(nested?'RELEASE '+name:'COMMIT');return value;}catch(error){db.exec(nested?'ROLLBACK TO '+name:'ROLLBACK');if(nested)db.exec('RELEASE '+name);throw error;}}
module.exports={openDatabase,transaction,SCHEMA_VERSION:MIGRATIONS.length};
