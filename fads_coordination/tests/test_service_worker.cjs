const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname, '../web/sw.js'),'utf8');
const destination='http://127.0.0.1:8787/web/employee.html?employeeId=sam&package=fixture';
async function check(mode){
 let navigated=false,focused=false,opened=false;
 const fresh={focus:async()=>{focused=true;return fresh;}};
 const old={url:'http://127.0.0.1:8787/web/employee.html?employeeId=sam',
  focus:async()=>{if(mode==='closed'||navigated)throw Error('WindowClient no longer exists');focused=true;return old;},
  navigate:async url=>{assert.equal(url,destination);navigated=true;return mode==='null'?null:fresh;}};
 const self={location:{origin:'http://127.0.0.1:8787'},addEventListener(){},clients:{
  matchAll:async()=>mode==='new'?[]:[old],openWindow:async url=>{assert.equal(url,destination);opened=true;return fresh;}}};
 const context={self,URL,URLSearchParams};vm.createContext(context);vm.runInContext(source,context);
 await context.openEmployee(destination);
 if(mode==='existing')assert.ok(navigated&&focused&&!opened);
 else assert.ok(opened);
 console.log('PASS Open web: '+mode);
}
(async()=>{for(const mode of ['existing','closed','null','new'])await check(mode);})().catch(e=>{console.error(e.message);process.exitCode=1;});
