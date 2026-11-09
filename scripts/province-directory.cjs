const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {execFileSync} = require('node:child_process');
const {launchOptions, assertBrowserVersion} = require('./browser-security.cjs');
const {outputDirectory, blockedResponse, verifiedPeer} = require('./psa-download.cjs');
const ORIGIN = 'https://www.pangasinan.gov.ph';
function allowed(url) {
  try { const u=new URL(url); return u.origin===ORIGIN && !u.username && !u.password; } catch { return false; }
}
function python(code, value) {
  return JSON.parse(execFileSync(path.resolve('.venv/bin/python'),['-c',code],{input:JSON.stringify(value),encoding:'utf8',timeout:10000}));
}
function contacts(rows) {
  return rows.filter(r=>r.cells.length>=2 && r.cells[0]!=='Name').map(r=>({...r,
    emails:(r.cells[2] || '').match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi) || []}));
}
async function run(target) {
  const output=outputDirectory(target);fs.mkdirSync(output,{recursive:true});
  const report={source_url:ORIGIN+'/directory/',started_at:new Date().toISOString(),review_status:'pending',status:'started',artifacts:[],requests:0};
  let browser, failure;
  const checks=[];
  function save(name,body) {if(body.length>2000000)throw Error('byte_limit');fs.writeFileSync(path.join(output,name),body,{flag:'wx'});report.artifacts.push({artifact:name,sha256:crypto.createHash('sha256').update(body).digest('hex')});}
  const timer=setTimeout(()=>{failure='time_limit';browser?.close().catch(()=>{});},90000);
  try {
    const ip=python('import json; from collector.practice import public_addresses; print(json.dumps(public_addresses("www.pangasinan.gov.ph")))').find(a=>!a.includes(':'));
    if(!ip)throw Error('no_public_ipv4');
    browser=await require('@playwright/test').chromium.launch({...launchOptions,headless:false,args:[`--host-resolver-rules=MAP www.pangasinan.gov.ph ${ip}`,'--no-proxy-server']});
    assertBrowserVersion(browser.version());report.browser_version=browser.version();
    const context=await browser.newContext({serviceWorkers:'block',acceptDownloads:false});
    await context.routeWebSocket('**/*',s=>s.close());
    await context.route('**/*',route=>{
      if(++report.requests>80 || !allowed(route.request().url()) || !['document','script','stylesheet'].includes(route.request().resourceType()))return route.abort();
      return route.continue();
    });
    const page=await context.newPage();page.setDefaultTimeout(20000);
    const cdp=await context.newCDPSession(page), peers=new Map();
    cdp.on('Network.responseReceived',e=>peers.set(e.response.url,e.response));await cdp.send('Network.enable');
    context.on('response',r=>{
      const task=(async()=>{
        const primary=await r.serverAddr();
        if(!primary && !peers.has(r.url()))await new Promise(resolve=>setTimeout(resolve,100));
        verifiedPeer(primary,peers.get(r.url()),ip,r.url());
        if(Number(r.headers()['content-length']||0)>2000000)throw Error('byte_limit');
      })().catch(e=>{failure=e.message;context.close().catch(()=>{});});checks.push(task);
    });
    const robots=await page.goto(ORIGIN+'/robots.txt');const robotsBody=await robots.body();save('robots.raw',robotsBody);
    if(blockedResponse(robots.status(),robots.headers(),robotsBody.toString()) || !robots.headers()['content-type']?.startsWith('text/plain'))throw Error('robots_unavailable');
    const policy=python('import json,sys; from urllib.robotparser import RobotFileParser; v=json.load(sys.stdin); r=RobotFileParser(); r.parse(v.splitlines()); print(json.dumps({"allowed":r.can_fetch("*","https://www.pangasinan.gov.ph/directory/"),"delay":r.crawl_delay("*") or 2}))',robotsBody.toString());
    if(!policy.allowed||policy.delay>30)throw Error('robots_denied_or_deferred');
    await page.waitForTimeout(Math.max(2,policy.delay)*1000);
    const response=await page.goto(report.source_url,{waitUntil:'load'});const body=await response.body();save('directory.raw',body);
    if(blockedResponse(response.status(),response.headers(),body.toString()))throw Error('access_denied');
    await page.waitForFunction(()=>document.querySelectorAll('a.__cf_email__').length===0,{},{timeout:10000});
    await Promise.all(checks);if(failure)throw Error(failure);
    save('directory.rendered.html',Buffer.from(await page.content()));
    const tableRows=await page.locator('table tr').evaluateAll(nodes=>nodes.map((row,index)=>({row:index,cells:[...row.querySelectorAll('th,td')].map(c=>c.innerText.trim()),emails:[...row.querySelectorAll('a[href^="mailto:"]')].map(a=>a.textContent.trim())})));
    const rows=contacts(tableRows);
    save('directory.json',Buffer.from(JSON.stringify({source_url:report.source_url,retrieved_at:new Date().toISOString(),review_status:'pending',contacts_human_verified:false,rows},null,2)));
    report.rows=rows.length;report.email_rows=rows.filter(r=>r.emails.length).length;report.status='collected_for_review';
  }catch(e){report.status='failed';report.error=failure||e.message;}
  finally{clearTimeout(timer);await browser?.close().catch(()=>{});report.finished_at=new Date().toISOString();fs.writeFileSync(path.join(output,'manifest.json'),JSON.stringify(report,null,2));}
  return report;
}
module.exports={allowed,contacts};
if(require.main===module){if(!process.argv.includes('--authorize-live'))throw Error('--authorize-live required');run(process.argv[2]).then(r=>{console.log(JSON.stringify(r));process.exitCode=r.status==='collected_for_review'?0:1;});}
