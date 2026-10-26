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
const att = (name, type, size) => ({ getName:()=> name, getContentType:()=> type, getSize:()=> size });
const mkMsg = (o = {}) => ({ getId:()=> 'id1', getFrom:()=> 'a@b.com', getReplyTo:()=> '', getSubject:()=> 's',
  getHeader:()=> o.auth || '', getPlainBody:()=> o.text || '', getBody:()=> o.html || '', getAttachments:()=> o.atts || [],
  ...o.overrides });
const bytes = (q) => Buffer.byteLength(JSON.stringify(q), 'utf8');
t('request clipped to backend limits', () => { const q = ctx.buildAnalyzeRequest(mkMsg({overrides:{getFrom:()=> 'a'.repeat(1500), getSubject:()=> 's'.repeat(3000)}})); assert.equal(q.from.length,1000); assert.equal(q.subject.length,2000); assert.equal(q.reply_to,null); });
t('request has exactly schema fields', () => assert.deepEqual(Object.keys(ctx.buildAnalyzeRequest(mkMsg())).sort(), ['attachments','auth_results','body_html','body_text','from','message_id','reply_to','subject','truncated']));
t('request carries auth results and bodies', () => { const q = ctx.buildAnalyzeRequest(mkMsg({auth:'mx.google.com; spf=pass', text:'hi', html:'<p>hi</p>'})); assert.equal(q.auth_results,'mx.google.com; spf=pass'); assert.equal(q.body_text,'hi'); assert.equal(q.body_html,'<p>hi</p>'); assert.equal(q.truncated,false); });
t('empty message maps to nulls', () => { const q = ctx.buildAnalyzeRequest(mkMsg()); assert.equal(q.auth_results,null); assert.equal(q.body_html,null); assert.equal(q.body_text,''); });
t('attachments are metadata only', () => { const q = ctx.buildAnalyzeRequest(mkMsg({atts:[att('x'.repeat(600)+'.exe','application/octet-stream',10)]})); assert.deepEqual(Object.keys(q.attachments[0]).sort(), ['filename','mime_type','size_bytes']); assert.equal(q.attachments[0].filename.length,512); });
t('attachments capped at 50', () => assert.equal(ctx.buildAnalyzeRequest(mkMsg({atts:Array(60).fill(att('a.pdf','application/pdf',1))})).attachments.length, 50));
t('field limit sets truncated', () => { const q = ctx.buildAnalyzeRequest(mkMsg({text:'t'.repeat(100001)})); assert.equal(q.body_text.length,100000); assert.equal(q.truncated,true); });
t('html trimmed first to fit budget', () => { const q = ctx.buildAnalyzeRequest(mkMsg({text:'t'.repeat(90000), html:'h'.repeat(150000)})); assert.ok(bytes(q) <= 190000); assert.equal(q.body_text.length,90000); assert.ok(q.body_html.length < 150000); assert.equal(q.truncated,true); });
t('text trimmed when html is not enough', () => { const q = ctx.buildAnalyzeRequest(mkMsg({text:'t'.repeat(100000), html:'h'.repeat(150000), overrides:{getSubject:()=> 's'.repeat(2000)}})); assert.ok(bytes(q) <= 190000); });
t('budget counts multibyte and escaped characters', () => { for (const ch of ['ש','😀','"','<']) { const q = ctx.buildAnalyzeRequest(mkMsg({text:ch.repeat(60000), html:ch.repeat(60000)})); assert.ok(bytes(q) <= 190000, ch); } });
t('never splits a surrogate pair', () => { const q = ctx.buildAnalyzeRequest(mkMsg({text:'😀'.repeat(50000), html:'😀'.repeat(50000)})); for (const f of ['body_text','body_html']) if (q[f]) assert.ok(!/[\ud800-\udbff]$/.test(q[f])); assert.ok(bytes(q) <= 190000); });
t('utf8Length matches Buffer', () => { for (const s of ['abc','ש','😀x','é€']) assert.equal(ctx.utf8Length(s), Buffer.byteLength(s,'utf8')); });
t('known severity kept, unknown dropped to null', () => { const r = ctx.parseAnalyzeResponse({...good, reasons:[{text:'a',severity:'high'},{text:'b',severity:'<b>evil</b>'}]}); assert.equal(r.reasons[0].severity,'high'); assert.equal(r.reasons[1].severity,null); });
t('reason line has severity word', () => assert.equal(ctx.reasonLine({text:'Bad link', severity:'high'}), '<b>High risk:</b> Bad link'));
t('reason line escapes text', () => assert.equal(ctx.reasonLine({text:'<a href=x>', severity:'low'}), '<b>Minor:</b> &lt;a href=x&gt;'));
t('reason line without severity', () => assert.equal(ctx.reasonLine({text:'x', severity:null}), '• x'));
t('escapes html', () => assert.equal(ctx.toPlainText('<a href="x">pay</a> & co'), '&lt;a href=&quot;x&quot;&gt;pay&lt;/a&gt; &amp; co'));
t('truncates display', () => assert.equal(ctx.toPlainText('x'.repeat(500)).length, 201));
t('null safe', () => assert.equal(ctx.toPlainText(null), ''));
t('ai section absent on older backend', () => { const r = ctx.parseAnalyzeResponse(good); assert.equal(r.ai.ran,false); assert.deepEqual(ctx.aiLines(r.ai), []); });
t('ai tactics validated against fixed list', () => { const r = ctx.parseAnalyzeResponse({...good, ai:{ran:true, tactics:['urgency','<b>x</b>','urgency','authority'], injection:'yes'}}); assert.deepEqual(Array.from(r.ai.tactics), ['urgency','authority']); assert.equal(r.ai.injection,false); });
t('ai malformed is ignored, not fatal', () => { for (const ai of [null,'x',5,{ran:'true'},{ran:true,tactics:'urgency'}]) { const r = ctx.parseAnalyzeResponse({...good, ai}); assert.ok(r.score === 42); } });
t('ai lines use fixed wording', () => assert.deepEqual(Array.from(ctx.aiLines({ran:true, tactics:['authority','financial'], injection:true})), ['The AI check read this email and found:','• Claims to come from someone in charge','• Asks for money or payment details','• Tries to give instructions to automated checks']));
t('ai found nothing', () => assert.deepEqual(Array.from(ctx.aiLines({ran:true, tactics:[], injection:false})), ['The AI check read this email and found no pressure tactics.']));
t('ai did not run', () => assert.deepEqual(Array.from(ctx.aiLines({ran:false, tactics:['urgency'], injection:true})), []));
t('ai reason labelled', () => { const r = ctx.parseAnalyzeResponse({...good, reasons:[{text:'Pressure', severity:'medium', source:'ai'},{text:'Link', severity:'high', source:'evil'}]}); assert.equal(ctx.reasonLine(r.reasons[0]), '<b>Worth checking · AI check:</b> Pressure'); assert.equal(ctx.reasonLine(r.reasons[1]), '<b>High risk:</b> Link'); });
console.log('addon logic checks passed: ' + n);
