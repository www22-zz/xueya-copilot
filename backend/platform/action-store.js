'use strict';
/** Map-shaped D port with durable state. Recovery consults receipts, never replays writes. */
function createActionStore(db,{recover=true}={}){
  const store={
    get size(){return db.prepare('SELECT COUNT(*) AS n FROM confirmations').get().n;},
    get(id){const row=db.prepare('SELECT data FROM confirmations WHERE id=?').get(id);return row?JSON.parse(row.data):undefined;},
    set(id,value){db.prepare('INSERT INTO confirmations VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data').run(id,JSON.stringify(value));return store;},
    delete(id){return!!db.prepare('DELETE FROM confirmations WHERE id=?').run(id).changes;},
    *[Symbol.iterator](){for(const row of db.prepare('SELECT * FROM confirmations').all())yield[row.id,JSON.parse(row.data)];}
  };
  if(recover)for(const [id,action] of store)if(['executing','uncertain'].includes(action.state)){
    const row=db.prepare('SELECT receipt FROM receipts WHERE user_id=? AND course_id=? AND action_id=?').get(action.scope.userId,action.scope.courseId,id);
    if(row){action.state='applied';action.receipt=JSON.parse(row.receipt);}else action.state='uncertain';store.set(id,action);
  }
  return store;
}
module.exports={createActionStore};
