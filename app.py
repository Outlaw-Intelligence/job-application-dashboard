#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sqlite3
import subprocess
import time
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DB = ROOT / "dashboard.sqlite3"
JOB_SOURCE_FILE = ROOT / "job-search-sources.json"
JOB_GOAL = {
    "deadline": "Ongoing",
    "monthly_target": "Remote AI work or Salt Lake hybrid AI work",
    "minimum": "Role fit and employer eligibility must be verified per posting",
    "cadence": "Auto-submit only supported, complete, evidence-producing applications",
    "daily_target": "Run bounded discovery and submission batches; block unsupported portals",
    "quality_bar": "AI/forward-deployment role fit, remote or Salt Lake hybrid fit, master resume and cover letter present, no sensitive-field guessing",
}
USER_HOME = Path(os.environ.get("JOB_DASHBOARD_HOME", "/Users/dylanwalls"))
CAREER_ROOT = USER_HOME / "Documents/Outlaw Intelligence/Zeus/Personal/Career"
MASTER_RESUME_PATH = CAREER_ROOT / "Dylan_Walls_Master_Resume.docx"
MASTER_RESUME_PDF_PATH = CAREER_ROOT / "Dylan_Walls_Master_Resume.pdf"
MASTER_COVER_LETTER_PDF_PATH = CAREER_ROOT / "Dylan_Walls_Master_Cover_Letter.pdf"
MASTER_COVER_LETTER_TEXT_PATH = CAREER_ROOT / "Dylan_Walls_Master_Cover_Letter.txt"
JOBOPS_ROOT = Path(os.environ.get("JOBOPS_ROOT", "/Users/dylanwalls/Documents/JobOps Vault/job-ops-integration"))
JOBOPS_DB_CANDIDATES = [
    JOBOPS_ROOT / "data/jobs.db",
    JOBOPS_ROOT / "orchestrator/data/jobs.db",
]
JOBOPS_LAST_SYNC_FILE = ROOT / ".jobops_last_sync.json"
INDEX_ROOTS = {
    "Career Packets": CAREER_ROOT / "Application Packets",
    "JobOps Imports": ROOT / "generated_packets/jobops_imports",
}
TEXT_SUFFIXES = {".md", ".txt", ".csv", ".json", ".yaml", ".yml", ".py", ".js", ".html", ".css", ".ts", ".tsx"}
BLOCKER_TAXONOMY = {
    "login_required": "Login required",
    "captcha": "CAPTCHA",
    "email_verification_code_needed": "Email verification code needed",
    "missing_resume": "Missing resume",
    "missing_cover_letter": "Missing cover letter",
    "broken_apply_link": "Broken apply link",
    "employer_portal_failure": "Employer portal failure",
    "manual_review_required": "Manual review required",
    "max_attempts_reached": "Max 2 attempts reached",
}
FINAL_STATUSES = {"submitted", "submission_blocked", "skipped"}
PROTECTED_IMPORT_STATUSES = {"submit_authorized", "submitted", "submission_blocked", "needs_changes", "skipped"}

RELEVANT_TERMS = {
    "resume", "cv", "cover", "letter", "career", "job", "jobs", "application", "applications",
    "linkedin", "recruiter", "portfolio", "remote", "interview", "packet", "tracker",
    "candidate", "salary", "greenhouse", "lever", "workable", "automation", "workflow",
    "outlaw", "zeus", "apply", "applying", "headhunter", "hiring",
}

HTML = r"""
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Zeus Job Application Dashboard</title>
<style>
.badge.generated {
    background: var(--gold);
    color: #080b10;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 0.8em;
    margin-left: 6px;
    vertical-align: middle;
}
:root{color-scheme:dark;--bg:#080b10;--panel:#101722;--panel2:#151f2f;--line:#263448;--text:#edf4ff;--muted:#93a4ba;--gold:#f6c85f;--green:#62d394;--red:#ff6b6b;--blue:#69a7ff;--purple:#b794f6}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top left,#182236,#080b10 45%);font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;color:var(--text)}header{position:sticky;top:0;z-index:5;background:rgba(8,11,16,.92);backdrop-filter:blur(14px);border-bottom:1px solid var(--line);padding:18px 22px;display:flex;gap:16px;align-items:center;justify-content:space-between}h1{margin:0;font-size:22px;letter-spacing:.3px}.sub{color:var(--muted);font-size:13px;margin-top:4px}.wrap{display:grid;grid-template-columns:320px 1fr 420px;gap:16px;padding:16px}.card{background:linear-gradient(180deg,var(--panel),#0c121b);border:1px solid var(--line);border-radius:16px;padding:14px;box-shadow:0 18px 60px rgba(0,0,0,.25)}button,.btn{background:var(--panel2);color:var(--text);border:1px solid var(--line);border-radius:10px;padding:9px 12px;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;gap:6px}button:hover,.btn:hover{border-color:var(--gold)}.primary{background:linear-gradient(135deg,#d69f21,#f6c85f);color:#171000;border:0;font-weight:800}.danger{border-color:#67313a;color:#ffd5dc}.pill{display:inline-flex;border:1px solid var(--line);border-radius:999px;padding:4px 8px;color:var(--muted);font-size:12px;margin:3px}.metric{display:grid;grid-template-columns:1fr 1fr;gap:10px}.metric div{background:var(--panel2);border:1px solid var(--line);border-radius:12px;padding:12px}.metric b{font-size:24px;color:var(--gold)}.board-card{border:1px solid var(--line);border-radius:14px;padding:12px;margin:10px 0;background:linear-gradient(135deg,#111c2a,#0b111a)}.board-card.approval{border-color:#b88725;box-shadow:0 0 0 1px rgba(246,200,95,.2) inset}.board-card.attention{border-color:#7a3340;box-shadow:0 0 0 1px rgba(255,107,107,.18) inset}.board-card h3{margin:0 0 6px;font-size:16px}.board-card .count{font-size:28px;font-weight:900;color:var(--gold);line-height:1}.board-card.attention .count{color:var(--red)}.mini-app{margin-top:8px;padding:8px;border-radius:10px;background:#0a1018;border:1px solid #1b293b;cursor:pointer}.mini-app:hover{border-color:var(--gold)}.mini-app b{display:block}.source-link{margin-top:8px;padding:8px;border-radius:10px;background:#08111c;border:1px solid #22405f}.source-link a{color:#9fcbff}.sprint{border-color:#376a9f;background:linear-gradient(135deg,#10243a,#09111b)}.sprint .count{color:var(--blue)}.empty-state{color:var(--muted);font-size:13px;margin-top:8px}input,select,textarea{width:100%;background:#080d14;color:var(--text);border:1px solid var(--line);border-radius:10px;padding:10px;margin:6px 0}ul{list-style:none;margin:0;padding:0}.file{padding:10px;border-bottom:1px solid #1d2a3b;cursor:pointer}.file:hover{background:#111b28}.file.active{background:#18253a;border-left:3px solid var(--gold)}.name{font-weight:700}.path{font-size:12px;color:var(--muted);word-break:break-all}.tag{font-size:11px;color:#0b1118;background:var(--gold);padding:2px 6px;border-radius:999px}.status-draft{color:var(--muted)}.status-approved{color:var(--green)}.status-needs_changes{color:var(--red)}.status-review{color:var(--blue)}pre{white-space:pre-wrap;word-break:break-word;background:#06090e;border:1px solid var(--line);border-radius:12px;padding:12px;max-height:52vh;overflow:auto}.actions{display:grid;gap:10px}.action{border:1px solid var(--line);border-radius:12px;padding:12px;background:var(--panel2)}.split{display:flex;gap:8px;flex-wrap:wrap}.small{font-size:12px;color:var(--muted)}@media(max-width:1100px){.wrap{grid-template-columns:1fr}.card{min-width:0}}.mini-app{cursor:pointer;transition:transform .12s ease,border-color .12s ease,background .12s ease}.mini-app:hover{transform:translateY(-1px);border-color:var(--gold);background:#172234}.mini-app .open-cta{display:inline-flex;margin-top:8px;color:#171000;background:var(--gold);border-radius:999px;padding:4px 8px;font-size:11px;font-weight:800}.review-actions{position:sticky;top:72px;z-index:3;display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:-4px -4px 12px;padding:10px;background:rgba(16,23,34,.96);backdrop-filter:blur(10px);border:1px solid var(--line);border-radius:14px}.posting-meta{display:grid;gap:8px;margin:10px 0 12px}.posting-links{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}.posting-body{max-height:68vh;overflow:auto;border:1px solid var(--line);border-radius:14px;background:#070b11;padding:14px;line-height:1.45}.posting-body h1,.posting-body h2,.posting-body h3{color:var(--gold);margin:16px 0 8px}.posting-body h1:first-child,.posting-body h2:first-child{margin-top:0}.posting-body p{margin:7px 0}.posting-body li{margin:4px 0}.posting-body code{background:#121b27;border:1px solid var(--line);border-radius:6px;padding:1px 5px}.posting-body a{color:var(--blue)}.focus-flash{animation:flashPanel 1.1s ease}.top-alerts{padding:12px 16px 0}.top-alert{border:1px solid #7a3340;background:linear-gradient(135deg,#32131b,#130b10);border-radius:14px;padding:12px 14px;box-shadow:0 0 0 1px rgba(255,107,107,.2) inset}.top-alert b{color:var(--red)}.top-alert button{margin-top:8px}.board-card.blocked{border-color:#9f3a47;box-shadow:0 0 0 1px rgba(255,107,107,.22) inset}.board-card.blocked .count{color:var(--red)}.board-card.submitted{border-color:#2f7d55;box-shadow:0 0 0 1px rgba(98,211,148,.22) inset}.board-card.submitted .count{color:var(--green)}.status-submission_blocked{color:var(--red)}.status-submitted{color:var(--green)}.back-top{position:fixed;right:18px;bottom:18px;z-index:9;background:linear-gradient(135deg,#1d2e45,#263d5c);border-color:#46668f;box-shadow:0 12px 34px rgba(0,0,0,.35)}@keyframes flashPanel{0%{box-shadow:0 0 0 2px var(--gold)}100%{box-shadow:0 18px 60px rgba(0,0,0,.25)}}</style>
</head><body><header><div><h1>Zeus Job Application Dashboard</h1><div class="sub">Review packets. Approve assets. Keep submission guarded until Dylan explicitly says go.</div></div><div class="split"><button class="primary" onclick="refreshIndex()">Refresh index</button><a class="btn" href="/api/export">Export manifest</a></div></header>
<button class="back-top" onclick="scrollToTop()">↑ Back to top</button>
<div id="topAlerts" class="top-alerts"></div><div class="wrap"><aside class="card"><h3>Command Center</h3><div class="metric"><div><span class="small">Indexed files</span><br><b id="mFiles">—</b></div><div><span class="small">Packages</span><br><b id="mPackages">—</b></div><div><span class="small">Submitted</span><br><b id="mSubmitted">—</b></div><div><span class="small">Mercury queue</span><br><b id="mMercury">—</b></div><div><span class="small">Today submitted</span><br><b id="mTodaySubmitted">—</b></div><div><span class="small">Week submitted</span><br><b id="mWeekSubmitted">—</b></div><div><span class="small">Ready review</span><br><b id="mReadyReview">—</b></div><div><span class="small">JobOps</span><br><b id="mJobOps">—</b></div><div><span class="small">Approved</span><br><b id="mApproved">—</b></div><div><span class="small">Needs work</span><br><b id="mNeeds">—</b></div><div><span class="small">Submission blockers</span><br><b id="mBlocked">—</b></div></div><div id="boardCards"></div><h3>Filters</h3><input id="q" placeholder="Search files, roles, companies…" oninput="loadFiles()"><select id="purpose" onchange="loadFiles()"><option value="">All purposes</option></select><select id="status" onchange="loadFiles()"><option value="">All statuses</option><option>draft</option><option>review</option><option>approved</option><option>submit_authorized</option><option>submission_blocked</option><option>submitted</option><option>needs_changes</option><option>skipped</option></select><h3>Automation Hooks</h3><div class="actions" id="actions"></div><div class="auto-submit"><label><input type="checkbox" id="autoSubmitToggle"> Auto-submit after approval</label></div></aside><main class="card"><h3>Application Assets</h3><div id="files"></div></main><section class="card"><h3>Review Panel</h3><div id="detail" class="small">Select a file or package.</div></section></div>
<script>
let selected=null;const $=id=>document.getElementById(id);
async function api(path,opt){const r=await fetch(path,opt); if(!r.ok){throw new Error(await r.text())} return await r.json()}
async function loadSummary(){const s=await api('/api/summary'); $('mFiles').textContent=s.files; $('mPackages').textContent=s.packages; $('mSubmitted').textContent=s.submitted||0; $('mMercury').textContent=s.submit_authorized||0; $('mTodaySubmitted').textContent=s.today_submitted||0; $('mWeekSubmitted').textContent=s.week_submitted||0; $('mReadyReview').textContent=s.ready_review||0; $('mJobOps').textContent=(s.jobops&&s.jobops.health)||'unknown'; $('mApproved').textContent=s.approved; $('mNeeds').textContent=s.needs_changes; $('mBlocked').textContent=s.submission_blocked||0; renderTopAlerts(s.submission_blockers||[]); const purpose=$('purpose'); const old=purpose.value; purpose.innerHTML='<option value="">All purposes</option>'+s.purposes.map(p=>`<option>${p}</option>`).join(''); purpose.value=old; renderBoardCards(s.board_cards||[]); renderJobRadar(s.job_goal||{},s.job_sources||[]); renderJobOpsStatus(s.jobops||{}); renderActions(s.actions)}
function scrollToTop(){window.scrollTo({top:0,behavior:'smooth'}); const first=document.querySelector('header'); if(first){first.scrollIntoView({behavior:'smooth',block:'start'})}}
function renderTopAlerts(blockers){$('topAlerts').innerHTML=blockers.length?`<div class="top-alert"><b>Submission blocked: ${blockers.length} application${blockers.length===1?'':'s'} need intervention.</b><div class="small">Something stopped full employer submission after Dylan approved it — missing required field, sensitive/legal question, upload failure, login/CAPTCHA, closed posting, or salary/location mismatch.</div><button class="danger" onclick="applyBoardFilter('submission_blocked')">Open submission blockers</button></div>`:''}
function renderBoardCards(cards){$('boardCards').innerHTML=cards.map(c=>`<div class="board-card ${c.tone}"><div class="split"><h3>${esc(c.title)}</h3><span class="count">${c.count}</span></div><div class="small">${esc(c.description)}</div>${c.items.length?c.items.map(i=>`<div class="mini-app" role="button" tabindex="0" onclick="showFile(${i.id})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();showFile(${i.id})}"><b>${esc(cleanJobName(i.name))}</b>${i.is_generated?`<span class="badge generated" title="Zeus-generated">🤖</span>`:''}<span class="small">${esc(i.notes||i.purpose||'Ready to open full compiled listing')}</span><span class="open-cta">Open full listing →</span></div>`).join(''):`<div class="empty-state">${esc(c.empty)}</div>`}<button onclick="applyBoardFilter('${c.status}')">Show all</button></div>`).join('')}
function renderJobRadar(goal,sources){$('boardCards').innerHTML+=`<div class="board-card sprint"><div class="split"><h3>July Remote Exit Sprint</h3><span class="count">${sources.length}</span></div><div class="small"><b>Goal:</b> ${esc(goal.monthly_target)} by ${esc(goal.deadline)}. <b>Floor:</b> ${esc(goal.minimum)}.</div><div class="small"><b>Daily target:</b> ${esc(goal.daily_target||'10+ applications/day')} · <b>Quality bar:</b> ${esc(goal.quality_bar||'verified fit + tailored materials')}</div><div class="small">Search mode: everywhere — company boards, Greenhouse/Lever, LinkedIn, recruiter posts, social posts, communities, referrals, and remote-job feeds.</div>${sources.map(s=>`<div class="source-link"><b>${esc(s.name)}</b> <span class="pill">${esc(s.status)}</span><div class="small">${esc(s.type)} · ${esc(s.notes||'')}</div><a href="${esc(s.url)}" target="_blank">Open source</a></div>`).join('')||'<div class="empty-state">No extra lead sources captured yet.</div>'}</div>`}
function renderJobOpsStatus(j){const warnings=(j.missing_packet_warnings||[]).map(w=>`<div class="mini-app"><b>${esc(w.name)}</b><span class="small">${esc(w.warning)}</span></div>`).join(''); $('boardCards').innerHTML+=`<div class="board-card sprint"><div class="split"><h3>JobOps Sync</h3><span class="count">${esc(j.health||'unknown')}</span></div><div class="small"><b>Last sync:</b> ${esc(j.last_sync||'never')} · <b>DB:</b> ${esc(j.active_db||'not found')}</div><div class="small"><b>JobOps jobs:</b> ${j.job_count||0} · <b>Ready:</b> ${j.jobops_ready||0} · <b>Applied:</b> ${j.jobops_applied||0} · <b>Imported packets:</b> ${j.imported_count||0}</div><div class="small"><b>Today:</b> ${j.today_submitted||0} submitted · <b>This week:</b> ${j.week_submitted||0} submitted · <b>Ready review:</b> ${j.ready_review||0} · <b>Missing packet warnings:</b> ${j.missing_packet_warning_count||0}</div><button onclick="syncJobOps()">Sync / Import JobOps</button>${warnings||'<div class="empty-state">No missing packet warnings from current indexed packets.</div>'}</div>`}
async function syncJobOps(){const r=await api('/api/jobops/sync',{method:'POST'}); alert(r.message||'JobOps sync complete.'); await loadSummary(); await loadFiles()}
function applyBoardFilter(status){$('purpose').value='Application packets / tailored role materials'; $('status').value=status; loadFiles()}
function renderActions(actions){$('actions').innerHTML=actions.map(a=>`<div class="action"><b>${a.label}</b> <span class="pill">${a.status}</span><div class="small">${a.description}</div><button onclick="runAction('${a.id}')" ${a.status==='unavailable'?'disabled':''}>Run guarded action</button></div>`).join('')}
async function runAction(id){let confirm=false;if(id!=='generate_packet'){confirm=window.confirm('Guardrail: this action may touch external workflow steps. Confirm local/guarded execution?')}try{const res=await api('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,confirm})}); alert(res.message||'done'); loadSummary()}catch(e){alert(e.message)}}
async function loadFiles(){const qs=new URLSearchParams({q:$('q').value,purpose:$('purpose').value,status:$('status').value}); const rows=await api('/api/files?'+qs); $('files').innerHTML=rows.map(f=>`<div class="file ${selected===f.id?'active':''}" onclick="showFile(${f.id})"><div class="split"><span class="name">${esc(f.name)}</span><span class="tag">${esc(f.status)}</span>${f.is_generated?`<span class="badge generated" title="Zeus-generated">🤖</span>`:''}<span class="pill" title="Resume asset">${f.resume_path?'📄':'📄 missing'}</span><span class="pill" title="Cover letter asset">${f.cover_letter_path?'✉️':'✉️ missing'}</span><span class="pill" title="Submission attempts">${f.attempt_count||0}/2</span></div><div class="small">${esc(f.purpose)} · Packet ${f.packet_complete?'complete':'incomplete'}</div><div class="path">${esc(f.path)}</div></div>`).join('')||'<p class="small">No matching assets.</p>'}
async function showFile(id){selected=id;loadFiles(); const f=await api('/api/files/'+id); const links=extractLinks(f.preview); $('detail').innerHTML=`<div class="review-actions"><button class="primary" onclick="submitApproval(${id})">Submit / Fire It Off</button><button onclick="generateTailoredDocuments(${id})">Generate Tailored Documents</button><button onclick="markSubmitted(${id})">Mark Fully Submitted</button><button onclick="incrementAttempt(${id})">Increment Attempt</button><button class="danger" onclick="requestWork(${id})">Review / Additional Work Needed</button><button class="danger" onclick="markSubmissionBlocked(${id})">Submission Blocked</button><button onclick="saveEvidence(${id})">Save Evidence</button><button onclick="setStatus(${id},'review')">Keep In Review</button><button onclick="openFinder(${id})">Open in Finder</button></div><h2>Full compiled listing</h2><h3>${esc(cleanJobName(f.name))}</h3><div class="posting-meta"><p class="path">${esc(f.path)}</p><p><span class="pill">${esc(f.purpose)}</span><span class="pill status-${f.status}">${esc(f.status)}</span><span class="pill">Packet: ${f.packet_complete?'complete':'incomplete'}</span><span class="pill">Attempts: ${f.attempt_count||0}/2</span></p><p class="small"><b>Resume:</b> ${esc(f.resume_path||'missing')}<br><b>Cover letter:</b> ${esc(f.cover_letter_path||'missing')}<br><b>Blocker:</b> ${esc(f.blocker_reason||'none')}<br><b>Evidence:</b> ${esc(f.confirmation_evidence||'none')}</p>${links.html}</div><textarea id="notes" placeholder="Review notes / updates needed">${esc(f.notes||'')}</textarea><button onclick="saveNotes(${id})">Save notes</button><h3>Compiled packet overview</h3><div class="posting-body">${markdownLite(f.preview)}</div>`; const panel=$('detail').closest('.card'); panel.classList.remove('focus-flash'); void panel.offsetWidth; panel.classList.add('focus-flash'); panel.scrollIntoView({behavior:'smooth',block:'start'});}
async function submitApproval(id){
  if(!confirm('Approve this application for Zeus to submit? This records explicit submission authorization. If the employer form blocks full submission, Zeus will route it to Submission Blocked instead of guessing.')) return;
  const res=await api('/api/files/'+id+'/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({notes:$('notes')?.value||''})});
  alert(res.message||'Submission authorization recorded.');
  await loadSummary();
  await showFile(id);
  if($('autoSubmitToggle') && $('autoSubmitToggle').checked){
    alert('Auto-submit is disabled by guardrail. Authorization was recorded only; no employer submission was attempted.');
  }
}
async function requestWork(id){const msg=prompt('What needs updating before this application is submitted?'); if(msg===null) return; const res=await api('/api/files/'+id+'/additional-work',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({notes:msg})}); alert(res.message||'Moved to Needs Your Attention.'); await loadSummary(); await showFile(id)}
async function markSubmitted(id){const msg=prompt('Employer confirmation evidence (receipt, confirmation URL, or screenshot path):'); if(msg===null) return; const res=await api('/api/files/'+id+'/submitted',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({notes:msg,evidence:msg})}); alert(res.message||'Marked fully submitted.'); await loadSummary(); await showFile(id)}
async function markSubmissionBlocked(id){const taxonomy='login_required, captcha, email_verification_code_needed, missing_resume, missing_cover_letter, broken_apply_link, employer_portal_failure, manual_review_required'; const reason=prompt('Blocker reason ('+taxonomy+'):', 'manual_review_required'); if(reason===null) return; const msg=prompt('Blocker notes / evidence:', reason); if(msg===null) return; const res=await api('/api/files/'+id+'/submission-blocked',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({notes:msg,reason})}); alert(res.message||'Moved to Submission Blocked.'); await loadSummary(); await showFile(id)}
async function incrementAttempt(id){const res=await api('/api/files/'+id+'/attempt',{method:'POST'}); alert(res.message||'Attempt recorded.'); await loadSummary(); await showFile(id)}
async function generateTailoredDocuments(id){if(!confirm('Guarded action: call JobOps to generate tailored documents for this packet, then sync local dashboard. No employer submission will be attempted.')) return; try{const res=await api('/api/files/'+id+'/generate-tailored-documents',{method:'POST'}); alert(res.message||'Tailored document generation attempted.'); await loadSummary(); await showFile(id)}catch(e){alert(e.message)}}
async function saveEvidence(id){const msg=prompt('Paste submission confirmation/evidence note, URL, receipt ID, or screenshot path.'); if(msg===null) return; const res=await api('/api/files/'+id+'/evidence',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({evidence:msg})}); alert(res.message||'Evidence saved.'); await loadSummary(); await showFile(id)}
async function setStatus(id,status){await api('/api/files/'+id+'/status',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({status,notes:$('notes')?.value||''})}); await loadSummary(); await showFile(id)}
async function saveNotes(id){await setStatus(id, $('detail .pill.status-approved')?'approved':'review')}
async function openFinder(id){await api('/api/files/'+id+'/open',{method:'POST'}); alert('Opened in Finder.')}
function cleanJobName(name){return String(name||'').replace(/ — Application Packet\.md$/,'').replace(/\.md$/,'')}
function extractLinks(txt){const out=[]; const seen=new Set(); const patterns=[/^- URL:\s*(https?:\/\/[^\s)<>"']+)/gmi,/^- Apply URL:\s*(https?:\/\/[^\s)<>"']+)/gmi,/(https?:\/\/[^\s)<>"']+)/gmi]; for(const re of patterns){let m; while((m=re.exec(txt||''))){const u=m[1].replace(/[.,]+$/,''); if(!seen.has(u)){seen.add(u); out.push(u)}}} const html=out.length?`<div class="posting-links">${out.slice(0,4).map((u,i)=>`<a class="btn" href="${esc(u)}" target="_blank">${i===0?'Open source / apply':'Open link '+(i+1)}</a>`).join('')}</div>`:''; return {urls:out,html}}
function inlineMd(s){return esc(s).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<b>$1</b>').replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g,'<a href="$2" target="_blank">$1</a>')}
function markdownLite(txt){const lines=String(txt||'').split(/\r?\n/); let html='', inList=false; for(const line of lines){if(/^###\s+/.test(line)){if(inList){html+='</ul>';inList=false} html+=`<h3>${inlineMd(line.replace(/^###\s+/,''))}</h3>`}else if(/^##\s+/.test(line)){if(inList){html+='</ul>';inList=false} html+=`<h2>${inlineMd(line.replace(/^##\s+/,''))}</h2>`}else if(/^#\s+/.test(line)){if(inList){html+='</ul>';inList=false} html+=`<h1>${inlineMd(line.replace(/^#\s+/,''))}</h1>`}else if(/^[-*]\s+/.test(line)){if(!inList){html+='<ul>';inList=true} html+=`<li>${inlineMd(line.replace(/^[-*]\s+/,''))}</li>`}else if(line.trim()===''){if(inList){html+='</ul>';inList=false} html+='<br>'}else{if(inList){html+='</ul>';inList=false} html+=`<p>${inlineMd(line)}</p>`}} if(inList) html+='</ul>'; return html}

async function refreshIndex(){const r=await api('/api/refresh',{method:'POST'}); alert(`Indexed ${r.indexed} files.`); await loadSummary(); await loadFiles()}
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
loadSummary().then(loadFiles);
</script></body></html>


"""


def tokens(path: Path) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", str(path).lower()) if t}


def purpose_for(path: Path) -> str:
    t = tokens(path)
    if {"resume", "cv"} & t:
        return "Resume / CV assets"
    if "cover" in t or ({"letter", "template"} <= t):
        return "Cover-letter assets"
    if {"linkedin", "recruiter"} & t:
        return "LinkedIn / recruiter messaging"
    if "tracker" in t or path.suffix.lower() == ".csv":
        return "Trackers / job lead data"
    if {"portfolio", "proof"} & t:
        return "Portfolio / proof assets"
    if {"automation", "workflow", "script", "scripts"} & t:
        return "Workflow / automation / operating notes"
    if {"packet", "application", "applications", "greenhouse", "lever", "workable"} & t:
        return "Application packets / tailored role materials"
    return "Application profile / answer bank"


def relevant(path: Path) -> bool:
    if path.name.startswith("."):
        return False
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".mov", ".mp4", ".zip"}:
        return bool(tokens(path) & RELEVANT_TERMS)
    return bool(tokens(path) & RELEVANT_TERMS)


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS files(
        id INTEGER PRIMARY KEY, path TEXT UNIQUE, name TEXT, root_label TEXT, purpose TEXT,
        suffix TEXT, size INTEGER, mtime REAL, status TEXT DEFAULT 'draft', notes TEXT DEFAULT '',
        updated_at REAL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS audit(
        id INTEGER PRIMARY KEY, ts REAL, path TEXT, action TEXT, detail TEXT
    )""")
    cols = {r[1] for r in c.execute("PRAGMA table_info(files)")}
    schema_additions = {
        "is_generated": "INTEGER NOT NULL DEFAULT 0",
        "attempt_count": "INTEGER NOT NULL DEFAULT 0",
        "blocker_reason": "TEXT NOT NULL DEFAULT ''",
        "confirmation_evidence": "TEXT NOT NULL DEFAULT ''",
        "resume_path": "TEXT NOT NULL DEFAULT ''",
        "cover_letter_path": "TEXT NOT NULL DEFAULT ''",
        "packet_complete": "INTEGER NOT NULL DEFAULT 0",
    }
    for col, ddl in schema_additions.items():
        if col not in cols:
            c.execute(f"ALTER TABLE files ADD COLUMN {col} {ddl}")
    c.commit()
    return c


def iter_index_files():
    for label, root in INDEX_ROOTS.items():
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", ".venv", "venv", "__pycache__", "Library"}]
            for name in filenames:
                p = Path(dirpath) / name
                try:
                    if p.is_file() and relevant(p):
                        yield label, p
                except OSError:
                    pass


def refresh() -> dict:
    c = conn(); count = 0; pruned = 0
    seen: set[str] = set()
    live_roots = [r.resolve() for r in INDEX_ROOTS.values() if r.exists()]
    for label, p in iter_index_files():
        try:
            st = p.stat()
        except OSError:
            continue
        sp = str(p)
        seen.add(sp)
        c.execute("""INSERT INTO files(path,name,root_label,purpose,suffix,size,mtime,updated_at)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(path) DO UPDATE SET name=excluded.name, root_label=excluded.root_label,
            purpose=excluded.purpose, suffix=excluded.suffix, size=excluded.size, mtime=excluded.mtime, updated_at=excluded.updated_at""",
            (sp, p.name, label, purpose_for(p), p.suffix.lower(), st.st_size, st.st_mtime, time.time()))
        count += 1
    # Drop index rows whose files vanished from a live index root. Rows outside
    # the indexed roots (imports, manual entries) are never pruned.
    if live_roots:
        for (fid, fpath) in c.execute("select id, path from files").fetchall():
            if fpath in seen:
                continue
            try:
                rp = str(Path(fpath).resolve())
            except OSError:
                continue
            under_root = any(rp == str(rt) or rp.startswith(str(rt) + os.sep) for rt in live_roots)
            if under_root and not Path(fpath).exists():
                c.execute("delete from files where id=?", (fid,))
                pruned += 1
    c.commit(); c.close()
    return {"indexed": count, "pruned": pruned}


def preview(path: Path) -> str:
    if not path.exists():
        return "File not found."
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return f"Binary/rich document: {path.name}\nUse Open in Finder to inspect it."
    try:
        txt = path.read_text(errors="replace")
        return txt[:8000] + ("\n\n… truncated …" if len(txt) > 8000 else "")
    except Exception as e:
        return f"Preview unavailable: {e}"


def packet_completeness_for(row_or_path, resume_path: str = "", cover_letter_path: str = "") -> int:
    if isinstance(row_or_path, (str, Path)):
        txt = preview(Path(row_or_path)).lower()
    else:
        txt = preview(Path(row_or_path["path"])).lower()
        resume_path = resume_path or (row_or_path["resume_path"] if "resume_path" in row_or_path.keys() else "")
        cover_letter_path = cover_letter_path or (row_or_path["cover_letter_path"] if "cover_letter_path" in row_or_path.keys() else "")
    resume_ok = bool(resume_path and Path(resume_path).exists()) or any(term in txt for term in ["tailored resume", "resume/pdf:", "resume path", "cv"])
    cover_ok = bool(cover_letter_path and Path(cover_letter_path).exists()) or any(term in txt for term in ["cover letter", "letter path"])
    missing_markers = ["tailored resume/pdf: missing", "cover letter: missing", "pdf generated at: missing"]
    if any(marker in txt for marker in missing_markers) and not (resume_path and cover_letter_path):
        return 0
    return 1 if resume_ok and cover_ok else 0


def refresh_packet_completeness(c: sqlite3.Connection) -> None:
    rows = c.execute("""select id,path,resume_path,cover_letter_path from files
        where purpose like 'Application packets%'""").fetchall()
    for r in rows:
        c.execute("update files set packet_complete=? where id=?", (packet_completeness_for(r), r["id"]))


def actions():
    return [
        {"id":"generate_packet","label":"Generate local packet","status":"ready/local","description":"Creates local packet materials only. Does not submit anything."},
        {"id":"open_job_page","label":"Open job page","status":"partial/guarded","description":"Guarded helper for opening target job pages manually."},
        {"id":"fill_known_fields","label":"Fill known fields","status":"partial/guarded","description":"Requires explicit confirmation; blocks sensitive fields."},
        {"id":"export_approved","label":"Export approved materials","status":"ready/guarded","description":"Exports a local manifest of approved assets."},
        {"id":"submit_application","label":"Submit application","status":"unavailable","description":"Disabled by design until Dylan explicitly authorizes submission."},
    ]


def _card_items(status: str) -> list[dict]:
    c = conn()
    try:
        rows = c.execute("""select id,path,name,purpose,status,notes,mtime,is_generated from files
            where status=? and purpose like 'Application packets%'
            order by mtime desc limit 20""", (status,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()


def board_cards() -> list[dict]:
    blocked_items = _card_items("submission_blocked")
    submitted_items = _card_items("submitted")
    mercury_items = _card_items("submit_authorized")
    approval_items = _card_items("review")
    attention_items = _card_items("needs_changes")
    return [
        {
            "id": "submitted_queue",
            "tone": "submitted",
            "status": "submitted",
            "title": "Submitted to Employer",
            "description": "Confirmed external submissions. These are no longer just approved — they were actually sent to the employer.",
            "empty": "No confirmed employer submissions yet.",
            "count": len(submitted_items),
            "items": submitted_items,
        },
        {
            "id": "mercury_queue",
            "tone": "approval",
            "status": "submit_authorized",
            "title": "Mercury Submission Queue",
            "description": "Dylan clicked Submit / Fire It Off. These are authorized and waiting for browser/email-gate completion before they can become Submitted to Employer.",
            "empty": "No applications are waiting in Mercury submission queue.",
            "count": len(mercury_items),
            "items": mercury_items,
        },
        {
            "id": "submission_blocked_queue",
            "tone": "blocked",
            "status": "submission_blocked",
            "title": "Submission Blocked",
            "description": "Dylan approved these, but the employer form stopped full submission. Resolve the blocker before retrying.",
            "empty": "No employer-submission blockers right now.",
            "count": len(blocked_items),
            "items": blocked_items,
        },
        {
            "id": "approval_queue",
            "tone": "approval",
            "status": "review",
            "title": "Needs Dylan Approval",
            "description": "Applications staged for your yes before Zeus submits anything.",
            "empty": "No applications are waiting on approval right now.",
            "count": len(approval_items),
            "items": approval_items,
        },
        {
            "id": "attention_queue",
            "tone": "attention",
            "status": "needs_changes",
            "title": "Needs Your Attention",
            "description": "Applications blocked by missing answers, edits, or review notes.",
            "empty": "No blocked applications need your attention right now.",
            "count": len(attention_items),
            "items": attention_items,
        },
    ]


def job_sources() -> list[dict]:
    if not JOB_SOURCE_FILE.exists():
        return []
    try:
        data = json.loads(JOB_SOURCE_FILE.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _jobops_health() -> str:
    try:
        with urlopen("http://localhost:3005/health", timeout=2) as r:
            data = json.loads(r.read().decode("utf-8", "replace") or "{}")
        return "ok" if data.get("status") == "ok" else "degraded"
    except Exception:
        return "offline"


def _read_jobops_env() -> dict[str, str]:
    env = JOBOPS_ROOT / ".env"
    if not env.exists():
        return {}
    vals: dict[str, str] = {}
    for line in env.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def _read_jobops_local_dashboard_token() -> str | None:
    token = _read_jobops_env().get("LOCAL_DASHBOARD_TOKEN", "").strip()
    return token or None


def _jobops_id_from_packet_text(text: str) -> str | None:
    m = re.search(r"^JobOps ID:\s*(\S+)", text or "", re.MULTILINE)
    return m.group(1).strip() if m else None


def _invoke_jobops_pdf_generation(jobops_id: str) -> tuple[bool, str]:
    token = _read_jobops_local_dashboard_token()
    if not token:
        return False, "JobOps LOCAL_DASHBOARD_TOKEN is not configured; guarded local generate-pdf bridge is unavailable."
    req = Request(
        f"http://localhost:3005/api/jobs/{jobops_id}/generate-pdf",
        method="POST",
        headers={"X-Local-Dashboard-Token": token},
    )
    try:
        with urlopen(req, timeout=240) as r:
            if 200 <= r.status < 300:
                return True, "JobOps tailored resume PDF generation completed."
            return False, f"JobOps generate-pdf returned HTTP {r.status}."
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        return False, f"JobOps generate-pdf failed with HTTP {e.code}: {detail}"
    except Exception as e:
        return False, f"JobOps generate-pdf failed: {type(e).__name__}: {e}"


def generate_tailored_documents_for_file(c: sqlite3.Connection, fid: str) -> dict:
    r = c.execute("select id,path,name from files where id=?", (fid,)).fetchone()
    if not r:
        return {"ok": False, "message": "Dashboard packet not found."}
    text = preview(Path(r["path"]))
    jobops_id = _jobops_id_from_packet_text(text)
    if not jobops_id:
        msg = "No JobOps ID found in this packet. Sync/import JobOps first."
        c.execute("update files set status=?, blocker_reason=?, updated_at=? where id=?", ("needs_changes", msg, time.time(), fid))
        c.commit()
        return {"ok": False, "message": msg}
    ok, message = _invoke_jobops_pdf_generation(jobops_id)
    if ok:
        sync_jobops_status()
        c.execute("update files set notes=?, blocker_reason='', updated_at=? where id=?", ("JobOps tailored document generation completed and dashboard sync attempted.", time.time(), fid))
        c.commit()
        return {"ok": True, "jobops_id": jobops_id, "message": message + " Dashboard sync completed."}
    c.execute("update files set status=?, blocker_reason=?, updated_at=? where id=?", ("needs_changes", message, time.time(), fid))
    c.execute("insert into audit(ts,path,action,detail) values(?,?,?,?)", (time.time(), r["name"], "generate_tailored_documents_blocked", message))
    c.commit()
    return {"ok": False, "jobops_id": jobops_id, "message": message}


def _active_jobops_db() -> Path | None:
    for p in JOBOPS_DB_CANDIDATES:
        if p.exists():
            try:
                con = sqlite3.connect(p)
                has_jobs = con.execute("select name from sqlite_master where type='table' and name='jobs'").fetchone()
                con.close()
                if has_jobs:
                    return p
            except Exception:
                continue
    return None


def _jobops_db_stats() -> dict:
    p = _active_jobops_db()
    if not p:
        return {"active_db": None, "jobops_tables": [], "job_count": 0, "jobops_ready": 0, "jobops_applied": 0, "job_status_counts": {}, "imported_count": 0}
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    try:
        tables = [r[0] for r in con.execute("select name from sqlite_master where type='table' order by name")]
        job_count = con.execute("select count(*) from jobs").fetchone()[0] if "jobs" in tables else 0
        status_counts = {}
        if "jobs" in tables:
            status_counts = {r["status"] or "unknown": r["c"] for r in con.execute("select status, count(*) c from jobs group by status")}
        imported_count = 0
        try:
            dash = conn()
            imported_count = dash.execute("select count(*) from files where root_label='JobOps Import'").fetchone()[0]
            dash.close()
        except Exception:
            imported_count = 0
        return {
            "active_db": str(p),
            "jobops_tables": tables,
            "job_count": job_count,
            "jobops_ready": status_counts.get("ready", 0),
            "jobops_applied": status_counts.get("applied", 0) + status_counts.get("submitted", 0),
            "job_status_counts": status_counts,
            "imported_count": imported_count,
        }
    finally:
        con.close()


def _last_jobops_sync() -> str | None:
    if not JOBOPS_LAST_SYNC_FILE.exists():
        return None
    try:
        data = json.loads(JOBOPS_LAST_SYNC_FILE.read_text())
        return data.get("last_sync")
    except Exception:
        return None


def _missing_packet_warnings(c: sqlite3.Connection, limit: int = 8) -> list[dict]:
    warnings = []
    rows = c.execute("""select id,name,path,notes from files
        where purpose like 'Application packets%' and suffix='.md'
          and (name like '%Application Packet%' or path like '%Application Packets%')
          and status in ('draft','review','needs_changes','submit_authorized')
        order by updated_at desc, mtime desc limit 80""").fetchall()
    for r in rows:
        p = Path(r["path"])
        txt = preview(p).lower() if p.suffix.lower() in TEXT_SUFFIXES else ""
        missing = []
        if "resume" not in txt and "cv" not in txt:
            missing.append("resume")
        if "cover" not in txt and "letter" not in txt:
            missing.append("cover letter")
        if missing:
            warnings.append({"id": r["id"], "name": r["name"], "warning": "Missing visible " + " + ".join(missing)})
        if len(warnings) >= limit:
            break
    return warnings


def jobops_status_payload(c: sqlite3.Connection | None = None) -> dict:
    own_conn = c is None
    c = c or conn()
    try:
        now = time.time()
        day_start = now - ((time.localtime(now).tm_hour * 3600) + (time.localtime(now).tm_min * 60) + time.localtime(now).tm_sec)
        week_start = now - (7 * 86400)
        today_submitted = c.execute("select count(*) from audit where action='submitted' and ts >= ?", (day_start,)).fetchone()[0]
        week_submitted = c.execute("select count(*) from audit where action='submitted' and ts >= ?", (week_start,)).fetchone()[0]
        ready_review = c.execute("select count(*) from files where status='review' and purpose like 'Application packets%'").fetchone()[0]
        warnings = _missing_packet_warnings(c)
        db_stats = _jobops_db_stats()
        return {
            "health": _jobops_health(),
            "jobops_root_exists": JOBOPS_ROOT.exists(),
            "dashboard_db": str(DB),
            "shared_db_ready": bool(db_stats.get("jobops_tables")),
            "last_sync": _last_jobops_sync(),
            "today_submitted": today_submitted,
            "week_submitted": week_submitted,
            "ready_review": ready_review,
            "missing_packet_warning_count": len(warnings),
            "missing_packet_warnings": warnings,
            "note": "Safe local status/import sync only. No employer submissions are attempted.",
            **db_stats,
        }
    finally:
        if own_conn:
            c.close()


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", value or "unknown").strip(" ._")
    return re.sub(r"\s+", "_", cleaned)[:90] or "unknown"


def _host_jobops_path(value: str | None) -> str:
    raw = (value or "").strip()
    if raw.startswith("/app/data/"):
        return str(JOBOPS_ROOT / "data" / raw[len("/app/data/"):])
    return raw




def _normalize_blocker_reason(reason: str | None) -> str:
    raw = (reason or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "login": "login_required",
        "auth": "login_required",
        "authentication": "login_required",
        "2fa": "email_verification_code_needed",
        "verification_code": "email_verification_code_needed",
        "email_code": "email_verification_code_needed",
        "cover_letter_missing": "missing_cover_letter",
        "resume_missing": "missing_resume",
        "portal_failure": "employer_portal_failure",
        "manual": "manual_review_required",
        "max_attempts": "max_attempts_reached",
    }
    raw = aliases.get(raw, raw)
    return raw if raw in BLOCKER_TAXONOMY else "manual_review_required"


def _cover_letter_candidate(company: str, title: str) -> Path | None:
    cover_dir = ROOT / "generated_packets" / "cover_letters"
    if not cover_dir.exists():
        return None
    base = f"{_safe_name(company)} — {_safe_name(title)} — Cover Letter"
    for suffix in (".docx", ".pdf", ".md", ".txt"):
        p = cover_dir / f"{base}{suffix}"
        if p.exists():
            return p
    company_key = _safe_name(company).lower()
    title_key = _safe_name(title).lower()
    for p in cover_dir.iterdir():
        n = p.name.lower()
        if company_key in n and title_key in n and "cover" in n:
            return p
    for master in (MASTER_COVER_LETTER_PDF_PATH, MASTER_COVER_LETTER_TEXT_PATH):
        if master.is_file():
            return master
    return None


def _extract_apply_url(packet_text: str) -> str:
    match = re.search(r"^- Apply URL:\s*(\S+)", packet_text or "", re.MULTILINE)
    if not match:
        return ""
    value = match.group(1).strip()
    return "" if value.lower() in {"missing", "none", "n/a"} else value


def _packet_blockers(resume_path: str, cover_letter_path: str, apply_url: str = "") -> list[str]:
    blockers = []
    if not apply_url:
        blockers.append("broken_apply_link")
    if not (resume_path and Path(resume_path).exists()):
        blockers.append("missing_resume")
    if not (cover_letter_path and Path(cover_letter_path).exists()):
        blockers.append("missing_cover_letter")
    return blockers

def import_jobops_jobs(limit: int = 200) -> int:
    p = _active_jobops_db()
    if not p:
        return 0
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    imported = 0
    outdir = ROOT / "generated_packets" / "jobops_imports"
    outdir.mkdir(parents=True, exist_ok=True)
    try:
        rows = con.execute("""select id,title,employer,job_url,application_link,status,suitability_score,
            suitability_reason,tailored_summary,tailored_headline,pdf_path,pdf_generated_at,created_at,updated_at
            from jobs order by updated_at desc limit ?""", (limit,)).fetchall()
        dash = conn()
        try:
            for r in rows:
                company = r["employer"] or "Unknown Company"
                title = r["title"] or "Unknown Role"
                out = outdir / f"{_safe_name(company)} — {_safe_name(title)} — JobOps Import.md"
                resume_path = _host_jobops_path(r["pdf_path"])
                cover_letter_path = str(_cover_letter_candidate(company, title) or "")
                blockers = _packet_blockers(resume_path, cover_letter_path, r["application_link"] or r["job_url"] or "")
                body = f"""# {company} — {title} — JobOps Import

Status: NOT SUBMITTED
Source: JobOps
JobOps ID: {r['id']}
JobOps Status: {r['status'] or 'unknown'}
Suitability Score: {r['suitability_score'] if r['suitability_score'] is not None else 'n/a'}

- URL: {r['job_url'] or ''}
- Apply URL: {r['application_link'] or ''}
- Tailored Resume/PDF: {f'[{resume_path}]({resume_path})' if resume_path else "missing"}
- Cover Letter: {f'[{cover_letter_path}]({cover_letter_path})' if cover_letter_path else "missing"}
- Packet Blockers: {', '.join(blockers) if blockers else 'none'}
- PDF Generated At: {f'[{r["pdf_generated_at"]}]({r["pdf_generated_at"]})' if r["pdf_generated_at"] else "missing"}
- Created: {r['created_at'] or ''}
- Updated: {r['updated_at'] or ''}

## Tailored Headline
{r['tailored_headline'] or 'missing'}

## Tailored Summary
{r['tailored_summary'] or 'missing'}

## Suitability Reason
{r['suitability_reason'] or 'missing'}

## Dashboard Workflow
- Review packet completeness before authorization.
- Do not submit until Dylan explicitly authorizes this specific application.
- Max 2 attempts per employer site before blocker/skip.
"""
                if not out.exists() or out.read_text(errors="replace") != body:
                    out.write_text(body)
                st = out.stat()
                complete = packet_completeness_for(out, resume_path, cover_letter_path)
                existing = dash.execute("select status,attempt_count from files where path=?", (str(out),)).fetchone()
                import_status = existing["status"] if existing and existing["status"] in PROTECTED_IMPORT_STATUSES else "review"
                note = "Imported from JobOps; review packet completeness before authorization."
                if blockers:
                    note += " Missing/blocker: " + ", ".join(blockers)
                dash.execute("""INSERT INTO files(path,name,root_label,purpose,suffix,size,mtime,status,notes,updated_at,is_generated,packet_complete,resume_path,cover_letter_path,blocker_reason)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(path) DO UPDATE SET name=excluded.name, root_label=excluded.root_label,
                    purpose=excluded.purpose, suffix=excluded.suffix, size=excluded.size, mtime=excluded.mtime,
                    updated_at=excluded.updated_at, is_generated=excluded.is_generated, packet_complete=excluded.packet_complete,
                    resume_path=excluded.resume_path, cover_letter_path=excluded.cover_letter_path,
                    blocker_reason=case when excluded.blocker_reason != '' then excluded.blocker_reason else files.blocker_reason end""",
                    (str(out), out.name, "JobOps Import", "Application packets / tailored role materials", ".md", st.st_size, st.st_mtime, import_status, note, time.time(), 1, complete, resume_path, cover_letter_path, ",".join(blockers)))
                imported += 1
            dash.commit()
        finally:
            dash.close()
        return imported
    finally:
        con.close()


def sync_jobops_status() -> dict:
    imported = import_jobops_jobs()
    status = jobops_status_payload()
    status["imported_this_sync"] = imported
    payload = {"last_sync": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "status": status}
    JOBOPS_LAST_SYNC_FILE.write_text(json.dumps(payload, indent=2))
    status["last_sync"] = payload["last_sync"]
    return status


def summary_payload() -> dict:
    c = conn()
    try:
        files = c.execute("select count(*) from files").fetchone()[0]
        approved = c.execute("select count(*) from files where status='approved'").fetchone()[0]
        submitted = c.execute("select count(*) from files where status='submitted' and confirmation_evidence is not null and trim(confirmation_evidence)!=''").fetchone()[0]
        submitted_unverified = c.execute("select count(*) from files where status='submitted' and (confirmation_evidence is null or trim(confirmation_evidence)='')").fetchone()[0]
        submit_authorized = c.execute("select count(*) from files where status='submit_authorized'").fetchone()[0]
        needs = c.execute("select count(*) from files where status='needs_changes'").fetchone()[0]
        blocked = c.execute("select count(*) from files where status='submission_blocked'").fetchone()[0]
        skipped = c.execute("select count(*) from files where status='skipped'").fetchone()[0]
        blockers = [dict(r) for r in c.execute("""select id,path,name,purpose,status,notes,mtime from files
            where status='submission_blocked' and purpose like 'Application packets%'
            order by updated_at desc, mtime desc limit 10""")]
        purposes = [r[0] for r in c.execute("select distinct purpose from files order by purpose")]
        packages = c.execute("select count(*) from files where purpose like 'Application packets%'").fetchone()[0]
        refresh_packet_completeness(c)
        packet_complete_count = c.execute("select count(*) from files where purpose like 'Application packets%' and packet_complete=1").fetchone()[0]
        packet_incomplete_count = c.execute("select count(*) from files where purpose like 'Application packets%' and packet_complete=0").fetchone()[0]
        max_attempt_blocked_count = c.execute("select count(*) from files where purpose like 'Application packets%' and attempt_count>=2 and status!='submitted'").fetchone()[0]
        jobops = jobops_status_payload(c)
        return {"files":files,"packages":packages,"approved":approved,"submitted":submitted,"submitted_unverified":submitted_unverified,"submit_authorized":submit_authorized,"today_submitted":jobops["today_submitted"],"week_submitted":jobops["week_submitted"],"ready_review":jobops["ready_review"],"packet_complete_count":packet_complete_count,"packet_incomplete_count":packet_incomplete_count,"max_attempt_blocked_count":max_attempt_blocked_count,"needs_changes":needs,"submission_blocked":blocked,"skipped":skipped,"submission_blockers":blockers,"purposes":purposes,"actions":actions(),"board_cards":board_cards(),"job_goal":JOB_GOAL,"job_sources":job_sources(),"jobops":jobops}
    finally:
        c.close()


class Handler(BaseHTTPRequestHandler):
    def send(self, code=200, body=b"", ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, indent=2).encode()
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def read_json(self):
        raw = self.headers.get("Content-Length", "0") or "0"
        try:
            n = int(raw)
        except (TypeError, ValueError):
            n = 0
        n = max(0, min(n, 10 * 1024 * 1024))  # never read more than 10 MiB
        data = self.rfile.read(n) if n else b"{}"
        try:
            return json.loads(data or b"{}")
        except json.JSONDecodeError:
            return {}
    def do_GET(self):
        u = urlparse(self.path); c = conn()
        try:
            if u.path == "/":
                return self.send(200, HTML, "text/html; charset=utf-8")
            if u.path == "/favicon.ico":
                return self.send(204, b"", "image/x-icon")
            if u.path == "/api/summary":
                return self.send(body=summary_payload())
            if u.path == "/api/jobops/status":
                return self.send(body=jobops_status_payload(c))
            if u.path == "/api/files":
                qs = parse_qs(u.query); where=[]; args=[]
                if qs.get("q", [""])[0]:
                    q = f"%{qs['q'][0]}%"; where.append("(path like ? or name like ? or purpose like ?)"); args += [q,q,q]
                if qs.get("purpose", [""])[0]: where.append("purpose=?"); args.append(qs["purpose"][0])
                if qs.get("status", [""])[0]: where.append("status=?"); args.append(qs["status"][0])
                sql = "select id,path,name,purpose,status,size,mtime,is_generated,packet_complete,attempt_count,blocker_reason,confirmation_evidence,resume_path,cover_letter_path from files" + (" where "+" and ".join(where) if where else "") + " order by case status when 'submitted' then 0 when 'submission_blocked' then 1 when 'needs_changes' then 2 when 'review' then 3 when 'submit_authorized' then 4 when 'draft' then 5 else 6 end, mtime desc limit 500"
                return self.send(body=[dict(r) for r in c.execute(sql,args)])
            m = re.match(r"/api/files/(\d+)$", u.path)
            if m:
                r = c.execute("select * from files where id=?", (m.group(1),)).fetchone()
                if not r: return self.send(404,{"error":"not found"})
                d = dict(r); d["preview"] = preview(Path(d["path"])); return self.send(body=d)
            if u.path == "/api/export":
                rows = [dict(r) for r in c.execute("select * from files order by purpose,name")]
                return self.send(200, rows, "application/json")
            return self.send(404,{"error":"not found"})
        finally:
            c.close()
    def do_POST(self):
        u = urlparse(self.path); c = conn()
        try:
            if u.path == "/api/refresh":
                return self.send(body=refresh())
            if u.path == "/api/jobops/sync":
                status = sync_jobops_status()
                return self.send(body={"ok": True, "message": "JobOps status synced and import bridge checked. No employer submissions attempted.", "jobops": status})
            m = re.match(r"/api/files/(\d+)/status$", u.path)
            if m:
                data = self.read_json(); status = data.get("status", "draft")
                if status == "submitted":
                    return self.send(code=409,body={"ok":False,"message":"Use the evidence-bearing /submitted endpoint; local status changes cannot claim an employer submission."})
                if status not in {"draft","review","approved","needs_changes","submit_authorized","submission_blocked","skipped"}: status="draft"
                c.execute("update files set status=?, notes=? where id=?", (status, data.get("notes",""), m.group(1)))
                c.commit(); return self.send(body={"ok":True})
            m = re.match(r"/api/files/(\d+)/submit$", u.path)
            if m:
                data = self.read_json(); fid = m.group(1)
                r = c.execute("select name,attempt_count,resume_path,cover_letter_path,path from files where id=?", (fid,)).fetchone()
                if not r: return self.send(404,{"error":"not found"})
                packet_text = preview(Path(r["path"]))
                blockers = _packet_blockers(r["resume_path"], r["cover_letter_path"], _extract_apply_url(packet_text))
                if int(r["attempt_count"] or 0) >= 2:
                    blockers.append("max_attempts_reached")
                if blockers:
                    reason = blockers[0]
                    detail = "Submit authorization blocked: " + ",".join(blockers)
                    c.execute("update files set status=?, blocker_reason=?, updated_at=? where id=?", ("submission_blocked", detail, time.time(), fid))
                    c.execute("insert into audit(ts,path,action,detail) values(?,?,?,?)", (time.time(), r["name"], "submit_blocked", detail))
                    c.commit(); return self.send(409,{"ok":False,"message":detail,"blockers":blockers})
                note = (data.get("notes") or "").strip()
                suffix = "\n\n[Dylan approved submission from dashboard. Zeus may submit this application.]"
                c.execute("update files set status=?, notes=?, updated_at=? where id=?", ("submit_authorized", (note + suffix).strip(), time.time(), fid))
                c.execute("insert into audit(ts,path,action,detail) values(?,?,?,?)", (time.time(), r[0], "submit_authorized", "Dylan clicked Submit / Fire It Off"))
                c.commit(); return self.send(body={"ok":True,"message":"Submission authorization recorded. Zeus can now fire this application off."})
            m = re.match(r"/api/files/(\d+)/additional-work$", u.path)
            if m:
                data = self.read_json(); fid = m.group(1)
                r = c.execute("select name from files where id=?", (fid,)).fetchone()
                if not r: return self.send(404,{"error":"not found"})
                note = (data.get("notes") or "Additional work requested by Dylan.").strip()
                c.execute("update files set status=?, notes=?, updated_at=? where id=?", ("needs_changes", note, time.time(), fid))
                c.execute("insert into audit(ts,path,action,detail) values(?,?,?,?)", (time.time(), r[0], "needs_changes", note))
                c.commit(); return self.send(body={"ok":True,"message":"Moved to Needs Your Attention with Dylan's requested update."})
            m = re.match(r"/api/files/(\d+)/submission-blocked$", u.path)
            if m:
                data = self.read_json(); fid = m.group(1)
                r = c.execute("select name from files where id=?", (fid,)).fetchone()
                if not r: return self.send(404,{"error":"not found"})
                note = (data.get("notes") or "Employer submission blocked after Dylan approval. Needs intervention before retry.").strip()
                reason = _normalize_blocker_reason(data.get("reason") or note)
                blocker_detail = f"{reason}: {note}"
                c.execute("update files set status=?, notes=?, blocker_reason=?, updated_at=? where id=?", ("submission_blocked", note, blocker_detail, time.time(), fid))
                c.execute("insert into audit(ts,path,action,detail) values(?,?,?,?)", (time.time(), r[0], "submission_blocked", blocker_detail))
                c.commit(); return self.send(body={"ok":True,"message":"Moved to Submission Blocked. Top alert and blocker section are now active."})
            m = re.match(r"/api/files/(\d+)/submitted$", u.path)
            if m:
                data = self.read_json(); fid = m.group(1)
                r = c.execute("select name from files where id=?", (fid,)).fetchone()
                if not r: return self.send(404,{"error":"not found"})
                note = (data.get("notes") or "").strip()
                evidence = (data.get("evidence") or "").strip()
                if not evidence:
                    return self.send(code=409,body={"ok":False,"message":"Employer confirmation evidence is required before a packet can be marked submitted."})
                suffix = "\n\n[External employer submission completed and confirmed.]"
                c.execute("update files set status=?, notes=?, confirmation_evidence=?, updated_at=? where id=?", ("submitted", (note + suffix).strip(), evidence, time.time(), fid))
                c.execute("insert into audit(ts,path,action,detail) values(?,?,?,?)", (time.time(), r[0], "submitted", evidence))
                c.commit(); return self.send(body={"ok":True,"message":"Marked as Submitted to Employer with confirmation evidence."})
            m = re.match(r"/api/files/(\d+)/generate-tailored-documents$", u.path)
            if m:
                result = generate_tailored_documents_for_file(c, m.group(1))
                code = 200 if result.get("ok") else 409
                return self.send(code=code, body=result)
            m = re.match(r"/api/files/(\d+)/attempt$", u.path)
            if m:
                fid = m.group(1)
                r = c.execute("select name,attempt_count from files where id=?", (fid,)).fetchone()
                if not r: return self.send(404,{"error":"not found"})
                attempt_count = int(r["attempt_count"] or 0) + 1
                status = "submission_blocked" if attempt_count >= 2 else None
                if status:
                    reason = "max_attempts_reached: Max 2 attempts reached. Blocked until manual review."
                    c.execute("update files set attempt_count=?, status=?, blocker_reason=?, updated_at=? where id=?", (attempt_count, status, reason, time.time(), fid))
                else:
                    c.execute("update files set attempt_count=?, updated_at=? where id=?", (attempt_count, time.time(), fid))
                c.execute("insert into audit(ts,path,action,detail) values(?,?,?,?)", (time.time(), r["name"], "attempt", f"Attempt {attempt_count}/2 recorded"))
                c.commit(); return self.send(body={"ok":True,"attempt_count":attempt_count,"message":f"Attempt {attempt_count}/2 recorded." + (" Max attempts reached; moved to Submission Blocked." if status else "")})
            m = re.match(r"/api/files/(\d+)/evidence$", u.path)
            if m:
                data = self.read_json(); fid = m.group(1)
                r = c.execute("select name from files where id=?", (fid,)).fetchone()
                if not r: return self.send(404,{"error":"not found"})
                evidence = (data.get("evidence") or "").strip()
                c.execute("update files set confirmation_evidence=?, updated_at=? where id=?", (evidence, time.time(), fid))
                c.execute("insert into audit(ts,path,action,detail) values(?,?,?,?)", (time.time(), r["name"], "evidence", evidence))
                c.commit(); return self.send(body={"ok":True,"message":"Confirmation evidence saved locally."})
            m = re.match(r"/api/files/(\d+)/open$", u.path)
            if m:
                r = c.execute("select path from files where id=?", (m.group(1),)).fetchone()
                if r: subprocess.Popen(["open", "-R", r[0]])
                return self.send(body={"ok":True})
            if u.path == "/api/action":
                data = self.read_json(); aid = data.get("id")
                if aid == "submit_application": return self.send(403,{"message":"Submission is disabled by design. Dylan must explicitly authorize final external submissions."})
                if aid in {"open_job_page","fill_known_fields","export_approved"} and not data.get("confirm"):
                    return self.send(403,{"message":"Explicit confirmation required for guarded automation."})
                if aid == "export_approved":
                    rows = [dict(r) for r in c.execute("select * from files where status='approved' order by purpose,name")]
                    out = ROOT / "approved-materials-manifest.json"; out.write_text(json.dumps(rows, indent=2))
                    return self.send(body={"message":f"Exported approved manifest: {out}"})
                if aid == "generate_packet":
                    outdir = ROOT / "generated_packets"; outdir.mkdir(exist_ok=True)
                    out = outdir / f"packet-{int(time.time())}.md"
                    out.write_text("# Local Application Packet\n\nStatus: NOT SUBMITTED\n\nGenerated locally by Zeus dashboard.\n")
                    return self.send(body={"message":f"Generated local packet: {out}"})
                return self.send(body={"message":"Guarded action acknowledged. No external submission performed."})
            return self.send(404,{"error":"not found"})
        finally:
            c.close()
    def log_message(self, fmt, *args):
        return


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--host", default="127.0.0.1"); ap.add_argument("--port", type=int, default=8765); ap.add_argument("--refresh-only", action="store_true")
    args = ap.parse_args(); ROOT.mkdir(parents=True, exist_ok=True); conn().close(); r = refresh()
    if args.refresh_only:
        print(json.dumps(r, indent=2)); return
    print(f"Zeus Job Application Dashboard: http://{args.host}:{args.port}")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()

if __name__ == "__main__": main()
