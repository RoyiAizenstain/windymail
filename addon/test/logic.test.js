// Node checks for the add-on's pure logic (no Apps Script services).
// Run from the repo root: node addon/test/logic.test.js
const fs = require('fs'); const path = require('path'); const vm = require('vm');
const dir = path.join(__dirname, '..'); const ctx = { console }; vm.createContext(ctx);
for (const f of ['Config.js','Api.js','Cards.js']) vm.runInContext(fs.readFileSync(path.join(dir,f),'utf8'), ctx);
const assert = require('assert'); let n = 0; const t = (name, fn) => { fn(); n++; };
const good = {score:42,verdict:'suspicious',summary:'s',reasons:[{text:'r',severity:'low',details:'d'}],manipulation:[],herd:null,partial:false,mode:'personal'};
t('valid response', () => { const r = ctx.parseAnalyzeResponse(good); assert.equal(r.score,42); assert.equal(r.reasons.length,1); });
t('strips unknown fields', () => { const r = ctx.parseAnalyzeResponse({...good, evil:'x'}); assert.equal(r.evil, undefined); });
for (const bad of [{score:101},{score:-1},{score:4.5},{score:'42'},{verdict:'fine'},{mode:'admin'},{summary:5},{reasons:'x'}])
  t('rejects '+JSON.stringify(bad), () => assert.throws(() => ctx.parseAnalyzeResponse({...good, ...bad})));
t('rejects null', () => assert.throws(() => ctx.parseAnalyzeResponse(null)));
t('drops malformed reasons', () => assert.equal(ctx.parseAnalyzeResponse({...good, reasons:[null,{x:1},{text:'ok'}]}).reasons.length, 1));
const msg = { getId:()=> 'id1', getFrom:()=> 'a'.repeat(1500), getReplyTo:()=> '', getSubject:()=> 's'.repeat(3000) };
t('request clipped to backend limits', () => { const q = ctx.buildAnalyzeRequest(msg); assert.equal(q.from.length,1000); assert.equal(q.subject.length,2000); assert.equal(q.reply_to,null); });
t('request has exactly schema fields', () => assert.deepEqual(Object.keys(ctx.buildAnalyzeRequest(msg)).sort(), ['attachments','auth_results','body_html','body_text','from','message_id','reply_to','subject']));
t('escapes html', () => assert.equal(ctx.toPlainText('<a href="x">pay</a> & co'), '&lt;a href=&quot;x&quot;&gt;pay&lt;/a&gt; &amp; co'));
t('truncates display', () => assert.equal(ctx.toPlainText('x'.repeat(500)).length, 201));
t('null safe', () => assert.equal(ctx.toPlainText(null), ''));
console.log('addon logic checks passed: ' + n);
