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
t('attachments are metadata and facts only', () => { const q = ctx.buildAnalyzeRequest(mkMsg({atts:[att('x'.repeat(600)+'.exe','application/octet-stream',10)]})); assert.deepEqual(Object.keys(q.attachments[0]).sort(), ['filename','inspection','mime_type','size_bytes']); assert.equal(q.attachments[0].filename.length,512); assert.deepEqual({...q.attachments[0].inspection}, {inspected:false}); });
t('attachments capped at 50', () => assert.equal(ctx.buildAnalyzeRequest(mkMsg({atts:Array(60).fill(att('a.pdf','application/pdf',1))})).attachments.length, 50));
t('field limit sets truncated', () => { const q = ctx.buildAnalyzeRequest(mkMsg({text:'t'.repeat(100001)})); assert.equal(q.body_text.length,100000); assert.equal(q.truncated,true); });
t('html trimmed first to fit budget', () => { const q = ctx.buildAnalyzeRequest(mkMsg({text:'t'.repeat(90000), html:'h'.repeat(150000)})); assert.ok(bytes(q) <= 190000); assert.equal(q.body_text.length,90000); assert.ok(q.body_html.length < 150000); assert.equal(q.truncated,true); });
t('text trimmed when html is not enough', () => { const q = ctx.buildAnalyzeRequest(mkMsg({text:'t'.repeat(100000), html:'h'.repeat(150000), overrides:{getSubject:()=> 's'.repeat(2000)}})); assert.ok(bytes(q) <= 190000); });
t('budget counts multibyte and escaped characters', () => { for (const ch of ['ש','😀','"','<']) { const q = ctx.buildAnalyzeRequest(mkMsg({text:ch.repeat(60000), html:ch.repeat(60000)})); assert.ok(bytes(q) <= 190000, ch); } });
t('never splits a surrogate pair', () => { const q = ctx.buildAnalyzeRequest(mkMsg({text:'😀'.repeat(50000), html:'😀'.repeat(50000)})); for (const f of ['body_text','body_html']) if (q[f]) assert.ok(!/[\ud800-\udbff]$/.test(q[f])); assert.ok(bytes(q) <= 190000); });
t('utf8Length matches Buffer', () => { for (const s of ['abc','ש','😀x','é€']) assert.equal(ctx.utf8Length(s), Buffer.byteLength(s,'utf8')); });
t('known severity kept, unknown dropped to null', () => { const r = ctx.parseAnalyzeResponse({...good, reasons:[{text:'a',severity:'high'},{text:'b',severity:'<b>evil</b>'}]}); assert.equal(r.reasons[0].severity,'high'); assert.equal(r.reasons[1].severity,null); });
t('reason label: shape and severity word in its color', () => { assert.equal(ctx.reasonLabel({severity:'high'}), '<font color="#C5221F">▲ High risk</font>'); assert.equal(ctx.reasonLabel({severity:'medium'}), '<font color="#B06000">● Worth checking</font>'); assert.equal(ctx.reasonLabel({severity:'low'}), '<font color="#5F6368">○ Minor</font>'); });
t('reason label without severity is empty', () => assert.equal(ctx.reasonLabel({severity:null}), ''));
t('score line: bar, exact score and verdict word', () => { const ui = ctx.VERDICT_UI.suspicious; assert.equal(ctx.scoreLine(52, ui), '<font color="#B06000">■■■■■</font>□□□□□  <b>52</b>/100 · Suspicious'); });
t('score line at the edges', () => { assert.ok(ctx.scoreLine(0, ctx.VERDICT_UI.safe).includes('></font>□□□□□□□□□□  <b>0</b>')); assert.ok(ctx.scoreLine(100, ctx.VERDICT_UI.malicious).includes('■■■■■■■■■■</font>  <b>100</b>')); });
t('every verdict has a word, label, color and action', () => { for (const v of ['safe','suspicious','malicious']) { const ui = ctx.VERDICT_UI[v]; assert.ok(ui.word && ui.label && /^#[0-9A-F]{6}$/.test(ui.color) && ui.action, v); } });
t('verdict word is upper case in its color', () => assert.equal(ctx.verdictWord(ctx.VERDICT_UI.malicious), '<font color="#C5221F"><b>MALICIOUS</b></font>'));
t('escapes html', () => assert.equal(ctx.toPlainText('<a href="x">pay</a> & co'), '&lt;a href=&quot;x&quot;&gt;pay&lt;/a&gt; &amp; co'));
t('truncates display', () => assert.equal(ctx.toPlainText('x'.repeat(500)).length, 201));
t('null safe', () => assert.equal(ctx.toPlainText(null), ''));
t('ai section absent on older backend', () => { const r = ctx.parseAnalyzeResponse(good); assert.equal(r.ai.ran,false); assert.deepEqual(ctx.aiLines(r.ai), []); });
t('ai tactics validated against fixed list', () => { const r = ctx.parseAnalyzeResponse({...good, ai:{ran:true, tactics:['urgency','<b>x</b>','urgency','authority'], injection:'yes'}}); assert.deepEqual(Array.from(r.ai.tactics), ['urgency','authority']); assert.equal(r.ai.injection,false); });
t('ai malformed is ignored, not fatal', () => { for (const ai of [null,'x',5,{ran:'true'},{ran:true,tactics:'urgency'}]) { const r = ctx.parseAnalyzeResponse({...good, ai}); assert.ok(r.score === 42); } });
t('ai lines use fixed wording, in the AI color', () => assert.deepEqual(Array.from(ctx.aiLines({ran:true, tactics:['authority','financial'], injection:true})), ['The AI check read this email and found:','<font color="#7627BB"><b>• Claims to come from someone in charge</b></font>','<font color="#7627BB"><b>• Asks for money or payment details</b></font>','<font color="#7627BB"><b>• Tries to give instructions to automated checks</b></font>']));
t('ai found nothing', () => assert.deepEqual(Array.from(ctx.aiLines({ran:true, tactics:[], injection:false})), ["The AI check read the whole email and didn't find it pressuring."]));
t('ai did not run', () => assert.deepEqual(Array.from(ctx.aiLines({ran:false, tactics:['urgency'], injection:true})), []));
t('ai reason labelled', () => { const r = ctx.parseAnalyzeResponse({...good, reasons:[{text:'Pressure', severity:'medium', source:'ai'},{text:'Link', severity:'high', source:'evil'}]}); assert.equal(ctx.reasonLabel(r.reasons[0]), '<font color="#B06000">● Worth checking</font> · <font color="#7627BB">AI check</font>'); assert.equal(ctx.reasonLabel(r.reasons[1]), '<font color="#C5221F">▲ High risk</font>'); });
t('ai impersonation wording', () => assert.deepEqual(Array.from(ctx.aiLines({ran:true, tactics:['impersonation'], injection:false})), ['The AI check read this email and found:', `<font color="#7627BB"><b>• Pretends to come from a company, bank or person it isn't</b></font>`]));
t('impersonation passes validation', () => assert.deepEqual(Array.from(ctx.parseAnalyzeResponse({...good, ai:{ran:true, tactics:['impersonation']}}).ai.tactics), ['impersonation']));
t('reason id kept when catalog-shaped', () => { const r = ctx.parseAnalyzeResponse({...good, reasons:[{text:'a', id:'dmarc_fail'},{text:'b', id:'<b>x</b>'},{text:'c', id:5}]}); assert.deepEqual(r.reasons.map(x => x.id), ['dmarc_fail', null, null]); });
t('report request has exactly schema fields', () => assert.deepEqual(Object.keys(ctx.buildReportRequest('m1', 80, [])).sort(), ['message_id','reason_ids','score']));
t('report request filters and dedupes ids', () => assert.deepEqual(Array.from(ctx.buildReportRequest('m1', 80, ['dmarc_fail','','a,b','dmarc_fail','x'.repeat(65),'link_ip']).reason_ids), ['dmarc_fail','link_ip']));
t('report parameters are strings', () => { const p = ctx.reportParameters(123, {score:82, reasons:[{id:'dmarc_fail'},{id:null},{id:'link_ip'}]}); assert.deepEqual({...p}, {messageId:'123', score:'82', reasonIds:'dmarc_fail,link_ip'}); });
t('personal report guidance mentions Report phishing', () => assert.ok(ctx.PERSONAL_REPORT_LINES.some(l => l.includes('Report phishing'))));
t('images come from our backend only', () => { const urls = []; ctx.CardService = { newImage: () => { const img = { setImageUrl: (u) => { urls.push(u); return img; }, setAltText: () => img }; return img; } }; for (const v of ['wordmark','safe','suspicious','malicious']) ctx.cardImage(v, 'alt'); for (const u of urls) assert.ok(u.startsWith(ctx.BACKEND_BASE_URL + '/static/') && u.endsWith('.png?v=' + ctx.ASSET_VERSION), u); delete ctx.CardService; });
t('report note says no email content is sent', () => assert.ok(/never the email itself/.test(ctx.REPORT_NOTE)));
t('header logo matches the add-on logo', () => assert.ok(fs.readFileSync(path.join(dir,'appsscript.json'),'utf8').includes(ctx.LOGO_URL)));
t('report footer: blue button that calls onReport', () => {
  const log = []; const mk = () => new Proxy(function () {}, { get: (_, k) => (...a) => { log.push([k, a[0]]); return mk(); }, apply: () => mk() });
  ctx.CardService = mk(); ctx.buildReportFooter({ getId: () => 'm1' }, { score: 90, reasons: [] });
  assert.ok(log.some(([k, a]) => k === 'setBackgroundColor' && a === ctx.REPORT_BUTTON_COLOR));
  assert.ok(log.some(([k, a]) => k === 'setFunctionName' && a === 'onReport'));
  assert.ok(!log.some(([k]) => k === 'newColumns'));
  delete ctx.CardService; });
t('technical details and points are not kept', () => { const r = ctx.parseAnalyzeResponse({...good, reasons:[{text:'a', severity:'high', details:'Extension: .exe', points:35}]}); assert.equal(r.reasons[0].details, undefined); assert.equal(r.reasons[0].points, undefined); });
// Attachment inspection (ADR-021): byte samples built here, no real files needed.
const bytesOf = (s) => Array.from(Buffer.from(s, 'latin1')).map(b => b > 127 ? b - 256 : b); // signed, like Apps Script
const le16 = (n) => [n & 255, (n >> 8) & 255]; const le32 = (n) => [...le16(n & 0xffff), ...le16(n >>> 16)];
const mkZip = (entries) => { const local = [0x50,0x4b,0x03,0x04, ...Array(26).fill(0)]; const dir = [];
  for (const e of entries) { const name = Array.from(Buffer.from(e.name, 'latin1')); dir.push(0x50,0x4b,0x01,0x02, 0,0, 0,0, ...le16(e.flags || 0), ...Array(18).fill(0), ...le16(name.length), 0,0, 0,0, ...Array(12).fill(0), ...name); }
  const end = [0x50,0x4b,0x05,0x06, 0,0, 0,0, ...le16(entries.length), ...le16(entries.length), ...le32(dir.length), ...le32(local.length), 0,0];
  return [...local, ...dir, ...end].map(b => b > 127 ? b - 256 : b); };
const budget = () => ({ entries: 50 });
const fileAtt = (name, bytes, size) => ({ getName: () => name, getContentType: () => 'application/octet-stream', getSize: () => size ?? bytes.length, getBytes: () => bytes });
t('kind: program, zip, pdf, ole, html, unknown', () => {
  assert.equal(ctx.fileKind(bytesOf('MZ\x90\x00rest')), 'exe'); assert.equal(ctx.fileKind(bytesOf('\x7fELF')), 'exe');
  assert.equal(ctx.fileKind(mkZip([])), 'zip'); assert.equal(ctx.fileKind(bytesOf('%PDF-1.7\n')), 'pdf');
  assert.equal(ctx.fileKind(bytesOf('junk junk %PDF-1.4')), 'pdf');
  assert.equal(ctx.fileKind([0xd0,0xcf,0x11,0xe0,0xa1].map(b => b - 256)), 'ole');
  assert.equal(ctx.fileKind(bytesOf('\xef\xbb\xbf  <!DOCTYPE html><html>')), 'html'); assert.equal(ctx.fileKind(bytesOf('<svg xmlns="x">')), 'html');
  assert.equal(ctx.fileKind(bytesOf('Dear customer, <b>pay</b>')), 'unknown'); assert.equal(ctx.fileKind([]), 'unknown'); });
t('zip directory: names, folders skipped, nothing unpacked', () => { const d = ctx.readZipDirectory(mkZip([{name:'docs/'},{name:'docs/invoice.pdf.exe'},{name:'a.jpg'}]), budget());
  assert.deepEqual(Array.from(d.entries), ['docs/invoice.pdf.exe','a.jpg']); assert.equal(d.encrypted, false); assert.equal(d.macros, false); });
t('zip directory: encrypted flag', () => assert.equal(ctx.readZipDirectory(mkZip([{name:'a.exe', flags:1}]), budget()).encrypted, true));
t('zip directory: macros in an Office file', () => { assert.equal(ctx.readZipDirectory(mkZip([{name:'[Content_Types].xml'},{name:'word/vbaProject.bin'}]), budget()).macros, true);
  assert.equal(ctx.readZipDirectory(mkZip([{name:'word/document.xml'}]), budget()).macros, false); });
t('zip directory: entry budget shared across files', () => { const b = { entries: 3 }; ctx.readZipDirectory(mkZip(Array.from({length:5}, (_, i) => ({name:`f${i}.txt`}))), b);
  assert.equal(b.entries, 0); assert.equal(ctx.readZipDirectory(mkZip([{name:'x.exe'}]), b).entries.length, 0); });
t('zip directory: long names clipped', () => assert.equal(ctx.readZipDirectory(mkZip([{name:'a'.repeat(400)}]), budget()).entries[0].length, 200));
t('zip without a table of contents is not readable', () => { assert.equal(ctx.readZipDirectory(bytesOf('PK\x03\x04garbage'), budget()), null);
  assert.deepEqual({...ctx.inspectBytes(bytesOf('PK\x03\x04garbage'), budget())}, {inspected:false}); });
t('truncated zip directory stops safely', () => { const z = mkZip([{name:'a.txt'},{name:'b.txt'}]); const end = z.slice(-22); const cut = [...z.slice(0, 40), ...end];
  assert.doesNotThrow(() => ctx.readZipDirectory(cut, budget())); });
t('pdf actions', () => { assert.deepEqual(Array.from(ctx.pdfActions(bytesOf('%PDF-1.7 /OpenAction 5 0 R /JS (app.alert(1)) /Launch /EmbeddedFile'))), ['javascript','open_action','launch','embedded_file']);
  assert.deepEqual(Array.from(ctx.pdfActions(bytesOf('%PDF-1.7 /Type /Catalog /JSON'))), []); });
t('inspectAll: facts per file, never bytes', () => { const r = ctx.inspectAll([fileAtt('invoice.pdf', bytesOf('MZ\x90\x00'))]);
  assert.deepEqual({...r[0]}, {inspected:true, kind:'exe', encrypted:false, entries:[], macros:false, pdf_actions:[]}); assert.ok(!JSON.stringify(r).includes('MZ')); });
t('inspectAll budgets: size, count, errors', () => { const ok = fileAtt('a.pdf', bytesOf('%PDF-1.4'));
  const r = ctx.inspectAll([fileAtt('big.pdf', bytesOf('%PDF'), 20 * 1024 * 1024), ok, ok, ok, ok, ok, { getSize: () => 1, getBytes: () => { throw new Error('boom'); } }]);
  assert.equal(r[0].inspected, false); assert.equal(r[1].inspected, true); assert.equal(r[5].inspected, false); assert.equal(r[6].inspected, false); });
t('inspection travels in the request', () => { const q = ctx.buildAnalyzeRequest(mkMsg({atts:[fileAtt('photos.zip', mkZip([{name:'run.lnk'}]))]}));
  assert.deepEqual(Array.from(q.attachments[0].inspection.entries), ['run.lnk']); assert.equal(q.attachments[0].inspection.kind, 'zip'); });
console.log('addon logic checks passed: ' + n);
