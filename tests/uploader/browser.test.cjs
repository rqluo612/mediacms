const assert=require('node:assert/strict'),fs=require('node:fs'),http=require('node:http');
const {JSDOM}=require(process.cwd()+'/frontend/node_modules/jsdom');
(async()=>{
 let bodies=[];const server=http.createServer((req,res)=>{let body='';req.on('data',c=>body+=c);req.on('end',()=>{bodies.push(body);res.end('{"success":true}');});});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const t=fs.readFileSync('templates/cms/add-media.html','utf8');
 const html=t.match(/<script type="text\/template" id="qq-template">([\s\S]*?)<\/script>/)[0];
 const dom=new JSDOM(html+'<div class="media-uploader"></div><div class="upload-processing-status"></div><button id="start-uploads"></button><button id="apply-common-tags"></button><input id="common-tags"><span id="batch-metadata-error"></span>',{url:`http://127.0.0.1:${server.address().port}`,runScripts:'outside-only',pretendToBeVisual:true});
 try{
 const w=dom.window,source=fs.readFileSync('static/js/upload-metadata.js','utf8');assert.equal(source,fs.readFileSync('frontend/src/static/js/upload-metadata.js','utf8'));w.eval(source);
 for(const key of ['isVideo','tags','validate'])assert.equal(typeof w.UploadMetadata[key],'function');
 w.eval(fs.readFileSync('static/lib/file-uploader/5.13.0/fine-uploader.js','utf8'));
 let uploader;const Original=w.qq.FineUploader;w.qq.FineUploader=function(o){uploader=new Original(o);return uploader;};
 let script=t.match(/<script>\s*(document.addEventListener[\s\S]*?)<\/script>/)[1].replace(/{% url 'uploader:upload' %}/g,'/upload/').replace(/{{UPLOAD_MAX_FILES_NUMBER}}/g,'10').replace(/{{UPLOAD_MAX_SIZE}}/g,'10000000');
 script=script.replace('document.addEventListener("DOMContentLoaded", function(event) {','(function(event) {').replace(/\}\);\s*$/, '})();');w.eval(script);
 uploader.addFiles(new w.File(['video-data'],'lesson.mp4',{type:'video/mp4'}));await new Promise(r=>setTimeout(r,100));
 const row=uploader.getItemByFileId(0);w.document.getElementById('start-uploads').click();assert.equal(bodies.length,0);assert.ok(row.querySelector('.metadata-error').textContent);
 row.querySelector('.metadata-title').value='独立标题';row.querySelector('.metadata-tags').value='Science, science';
 w.document.getElementById('start-uploads').click();for(let i=0;i<50&&!bodies.length;i++)await new Promise(r=>setTimeout(r,20));
 assert.equal(bodies.length,1);assert.ok(bodies[0].includes('独立标题'));assert.ok(bodies[0].includes('["science"]'));assert.ok(bodies[0].includes('video-data'));
 console.log('Browser exports, source parity, prepareMetadata validation and click → actual HTTP upload passed.');
 }finally{dom.window.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
