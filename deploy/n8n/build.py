"""Builds the two import-ready n8n workflows for BNN Asia.

  A. "BNN Asia · Rights Monitor (daily 08:00)"  collect → AI triage → AI write → AI check → AI image → WordPress
  B. "BNN Asia · Social Publisher (every 15 min)" new country_news posts → photocard → Facebook (+ link comment) and X (+ link reply)

Run: python3 build.py  → writes workflow-a-rights-monitor.json and workflow-b-social-publisher.json
Credentials are attached in n8n after import (OpenAI, WordPress, Facebook Graph, X OAuth2).
"""
import json
import uuid
from pathlib import Path

HERE = Path(__file__).parent
RULEBOOK = (HERE / "rulebook.md").read_text().strip()
assert "`" not in RULEBOOK and "${" not in RULEBOOK

COUNTRIES = {  # name → (slug, WordPress term id in country_select)
    "Afghanistan": ("afghanistan", 211), "Armenia": ("armenia", 212), "Azerbaijan": ("azerbaijan", 213),
    "Bahrain": ("bahrain", 214), "Bangladesh": ("bangladesh", 210), "Bhutan": ("bhutan", 215), "Brunei": ("brunei", 216),
    "Cambodia": ("cambodia", 217), "China": ("china", 218), "Cyprus": ("cyprus", 219), "Georgia": ("georgia", 220),
    "India": ("india", 221), "Indonesia": ("indonesia", 222), "Iran": ("iran", 223), "Iraq": ("iraq", 224),
    "Israel": ("israel", 225), "Japan": ("japan", 226), "Jordan": ("jordan", 227), "Kazakhstan": ("kazakhstan", 228),
    "Kuwait": ("kuwait", 229), "Kyrgyzstan": ("kyrgyzstan", 230), "Laos": ("laos", 231), "Lebanon": ("lebanon", 232),
    "Malaysia": ("malaysia", 233), "Maldives": ("maldives", 234), "Mongolia": ("mongolia", 235), "Myanmar": ("myanmar", 236),
    "Nepal": ("nepal", 237), "North Korea": ("north-korea", 238), "Oman": ("oman", 239), "Pakistan": ("pakistan", 240),
    "Palestine": ("palestine", 241), "Philippines": ("philippines", 242), "Qatar": ("qatar", 243),
    "Saudi Arabia": ("saudi-arabia", 244), "Singapore": ("singapore", 245), "South Korea": ("south-korea", 246),
    "Sri Lanka": ("sri-lanka", 247), "Syria": ("syria", 248), "Taiwan": ("taiwan", 249), "Tajikistan": ("tajikistan", 250),
    "Thailand": ("thailand", 251), "Timor-Leste": ("timor-leste", 252), "Turkey": ("turkey", 253),
    "Turkmenistan": ("turkmenistan", 254), "United Arab Emirates": ("uae", 255), "Uzbekistan": ("uzbekistan", 256),
    "Vietnam": ("vietnam", 257), "Yemen": ("yemen", 258),
}
FLAGS = {
    "Afghanistan": "🇦🇫", "Armenia": "🇦🇲", "Azerbaijan": "🇦🇿", "Bahrain": "🇧🇭", "Bangladesh": "🇧🇩", "Bhutan": "🇧🇹",
    "Brunei": "🇧🇳", "Cambodia": "🇰🇭", "China": "🇨🇳", "Cyprus": "🇨🇾", "Georgia": "🇬🇪", "India": "🇮🇳",
    "Indonesia": "🇮🇩", "Iran": "🇮🇷", "Iraq": "🇮🇶", "Israel": "🇮🇱", "Japan": "🇯🇵", "Jordan": "🇯🇴",
    "Kazakhstan": "🇰🇿", "Kuwait": "🇰🇼", "Kyrgyzstan": "🇰🇬", "Laos": "🇱🇦", "Lebanon": "🇱🇧", "Malaysia": "🇲🇾",
    "Maldives": "🇲🇻", "Mongolia": "🇲🇳", "Myanmar": "🇲🇲", "Nepal": "🇳🇵", "North Korea": "🇰🇵", "Oman": "🇴🇲",
    "Pakistan": "🇵🇰", "Palestine": "🇵🇸", "Philippines": "🇵🇭", "Qatar": "🇶🇦", "Saudi Arabia": "🇸🇦",
    "Singapore": "🇸🇬", "South Korea": "🇰🇷", "Sri Lanka": "🇱🇰", "Syria": "🇸🇾", "Taiwan": "🇹🇼",
    "Tajikistan": "🇹🇯", "Thailand": "🇹🇭", "Timor-Leste": "🇹🇱", "Turkey": "🇹🇷", "Turkmenistan": "🇹🇲",
    "United Arab Emirates": "🇦🇪", "Uzbekistan": "🇺🇿", "Vietnam": "🇻🇳", "Yemen": "🇾🇪",
}

# Words that trigger reduced reach on Facebook/X. Applied to social captions and card titles only, never to the website.
SOFTEN = {
    "murdered": "mur-dered", "murder": "mur-der", "murders": "mur-ders", "killed": "k!lled", "killing": "k!lling",
    "killings": "k!llings", "kill": "k!ll", "dead": "de@d", "death": "de@th", "deaths": "de@ths", "died": "d!ed",
    "shot": "sh0t", "shooting": "sh0oting", "gunmen": "gunm3n", "gun": "g*n", "stabbed": "st@bbed",
    "beaten": "be@ten", "torture": "tor-ture", "tortured": "tor-tured", "rape": "r@pe", "raped": "r@ped",
    "bomb": "b0mb", "bombing": "b0mbing", "blood": "bl00d", "suicide": "su!cide", "massacre": "mass@cre",
    "executed": "exe-cuted", "execution": "exe-cution", "hanged": "h@nged", "lynched": "lyn-ched",
    "lynching": "lyn-ching", "violence": "vi0lence", "violent": "vi0lent", "assault": "as-sault",
    "assaulted": "as-saulted", "attack": "att@ck", "attacked": "att@cked", "corpse": "c0rpse", "body": "b0dy",
}


def nid():
    return str(uuid.uuid4())


def code(name, js, pos, each=False):
    p = {"jsCode": js}
    if each:
        p["mode"] = "runOnceForEachItem"
    return {"parameters": p, "id": nid(), "name": name, "type": "n8n-nodes-base.code", "typeVersion": 2, "position": pos}


def http(name, pos, method, url, *, auth=None, generic=None, json_body=None, query=None, headers=None,
         binary_field=None, multipart=None, form=None, response=None, timeout=60000, on_error=True, execute_once=False,
         retry=False):
    p = {"method": method, "url": url}
    if auth:
        p["authentication"] = "predefinedCredentialType"
        p["nodeCredentialType"] = auth
    if generic:
        p["authentication"] = "genericCredentialType"
        p["genericAuthType"] = generic
    if query:
        p["sendQuery"] = True
        p["queryParameters"] = {"parameters": [{"name": k, "value": v} for k, v in query]}
    if headers:
        p["sendHeaders"] = True
        p["headerParameters"] = {"parameters": [{"name": k, "value": v} for k, v in headers]}
    if json_body is not None:
        p["sendBody"] = True
        p["specifyBody"] = "json"
        p["jsonBody"] = json_body
    if binary_field:
        p["sendBody"] = True
        p["contentType"] = "binaryData"
        p["inputDataFieldName"] = binary_field
    if multipart:
        p["sendBody"] = True
        p["contentType"] = "multipart-form-data"
        params = []
        for k, v in multipart:
            if isinstance(v, dict) and "binary" in v:
                params.append({"parameterType": "formBinaryData", "name": k, "inputDataFieldName": v["binary"]})
            else:
                params.append({"name": k, "value": v})
        p["bodyParameters"] = {"parameters": params}
    if form:
        p["sendBody"] = True
        p["contentType"] = "form-urlencoded"
        p["bodyParameters"] = {"parameters": [{"name": k, "value": v} for k, v in form]}
    opts = {"timeout": timeout}
    if response == "text":
        opts["response"] = {"response": {"responseFormat": "text", "outputPropertyName": "data"}}
    elif response and response.startswith("file:"):
        opts["response"] = {"response": {"responseFormat": "file", "outputPropertyName": response[5:]}}
    p["options"] = opts
    node = {"parameters": p, "id": nid(), "name": name, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
            "position": pos}
    if on_error:
        node["onError"] = "continueRegularOutput"
    if execute_once:
        node["executeOnce"] = True
    if retry:
        node["retryOnFail"] = True
        node["maxTries"] = 3
        node["waitBetweenTries"] = 5000
    return node


def chain(*names):
    conns = {}
    for a, b in zip(names, names[1:]):
        conns.setdefault(a, {"main": [[]]})["main"][0].append({"node": b, "type": "main", "index": 0})
    return conns


def merge(*dicts):
    out = {}
    for d in dicts:
        for k, v in d.items():
            if k in out:
                out[k]["main"][0].extend(v["main"][0])
            else:
                out[k] = json.loads(json.dumps(v))
    return out


def workflow(name, nodes, connections):
    return {"name": name, "nodes": nodes, "connections": connections, "active": False,
            "settings": {"executionOrder": "v1", "timezone": "Asia/Dhaka", "saveManualExecutions": True},
            "pinData": {}, "meta": {"templateCredsSetupCompleted": False}, "tags": []}


def js_obj(o):
    return json.dumps(o, ensure_ascii=False)


SOFTEN_JS = """
const SOFTEN = %s;
function soften(text) {
  return String(text || '').replace(/[A-Za-z]+/g, w => {
    const r = SOFTEN[w.toLowerCase()];
    if (!r) return w;
    if (w === w.toUpperCase()) return r.toUpperCase();
    if (w[0] === w[0].toUpperCase()) return r[0].toUpperCase() + r.slice(1);
    return r;
  });
}
""" % js_obj(SOFTEN)

DECODE_JS = r"""
function decode(s) {
  return String(s || '')
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(+n))
    .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCharCode(parseInt(n, 16)))
    .replace(/&quot;/g, '"').replace(/&apos;|&#039;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&')
    .replace(/\s+/g, ' ').trim();
}
"""

# ---------------------------------------------------------------------------------------------------------------
# A. Rights monitor
# ---------------------------------------------------------------------------------------------------------------
CONFIG_A = """// ===== BNN Asia settings: edit here =====
const RULEBOOK = `%s`;
return [{ json: {
  models: { fast: 'gpt-5-mini', writer: 'gpt-5', image: 'gpt-image-2' },
  max_posts: 2,                 // most stories published per day (BNN Asia is not a news channel)
  approval: 'auto',             // 'auto' = scheduled publishing, 'review' = saved as drafts for an editor
  run_window: [8, 23],          // Dhaka hours: runs once a day at a random time between 08:00 and 23:59
  wp_base: 'https://www.bnnasia.org',
  lookback_hours: 48,
  countries: %s,
  rulebook: RULEBOOK
}}];
""" % (RULEBOOK, js_obj({k: {"slug": v[0], "id": v[1]} for k, v in COUNTRIES.items()}))

GDELT_QUERIES = [
    '(journalist OR reporter OR editor OR photojournalist OR "media worker" OR newspaper) (arrested OR detained OR jailed OR sentenced OR charged OR abducted OR attacked OR assaulted OR killed OR "shot dead" OR threatened OR harassed)',
    '(blogger OR activist OR "human rights defender" OR youtuber OR cartoonist OR "rights lawyer" OR dissident) (arrested OR detained OR jailed OR abducted OR disappeared OR sentenced OR tortured)',
    '("internet shutdown" OR "press freedom" OR "media crackdown" OR "enforced disappearance" OR "custodial death" OR "extrajudicial killing" OR "cyber security act" OR "digital security act" OR "sedition charges" OR "blasphemy charges")',
]

SOURCES_A = """const q = %s;
const gdelt = q.map(query => ({
  kind: 'gdelt', source: 'GDELT',
  url: 'https://api.gdeltproject.org/api/v2/doc/doc?format=json&mode=artlist&sort=datedesc&maxrecords=250&timespan=2d&query=' +
       encodeURIComponent(query + ' sourcelang:english')
}));
const rss = [
  ['CPJ', 'https://cpj.org/feed/'],
  ['Amnesty', 'https://www.amnesty.org/en/feed/'],
  ['Global Voices Advox', 'https://advox.globalvoices.org/feed/'],
  ['IFEX', 'https://ifex.org/feed/'],
  ['Article 19', 'https://www.article19.org/feed/'],
  ['Front Line Defenders', 'https://www.frontlinedefenders.org/en/rss.xml'],
].map(([source, url]) => ({ kind: 'rss', source, url }));
return [...gdelt, ...rss].map(json => ({ json }));
""" % js_obj(GDELT_QUERIES)

PARSE_A = DECODE_JS + r"""
const sources = $('Sources').all();
const out = [];
function gdeltDate(s) { // 20261124T081500Z
  const m = String(s || '').match(/^(\d{4})(\d\d)(\d\d)T(\d\d)(\d\d)(\d\d)Z$/);
  return m ? Date.UTC(+m[1], m[2] - 1, +m[3], +m[4], +m[5], +m[6]) : Date.now();
}
$input.all().forEach((item, i) => {
  const src = (sources[i] || {}).json || {};
  const body = typeof item.json.data === 'string' ? item.json.data : '';
  if (!body) return;
  if (src.kind === 'gdelt') {
    let j; try { j = JSON.parse(body); } catch (e) { return; }
    for (const a of (j.articles || [])) {
      out.push({ title: decode(a.title), link: a.url, published: gdeltDate(a.seendate), summary: '',
                 source: a.domain || 'news', kind: 'news', image: a.socialimage || '' });
    }
    return;
  }
  const blocks = body.match(/<item[\s>][\s\S]*?<\/item>/gi) || body.match(/<entry[\s>][\s\S]*?<\/entry>/gi) || [];
  for (const x of blocks) {
    const tag = t => { const m = x.match(new RegExp('<' + t + '(?:\\s[^>]*)?>([\\s\\S]*?)</' + t + '>', 'i')); return m ? m[1] : ''; };
    let link = decode(tag('link'));
    if (!link) { const m = x.match(/<link[^>]*href="([^"]+)"/i); link = m ? m[1] : ''; }
    const date = Date.parse(decode(tag('pubDate') || tag('published') || tag('updated') || tag('dc:date'))) || Date.now();
    out.push({ title: decode(tag('title')), link, published: date,
               summary: decode(tag('description') || tag('summary') || tag('content:encoded')).slice(0, 700),
               source: src.source, kind: 'ngo', image: '' });
  }
});
return out.filter(a => a.title && a.link).map(json => ({ json }));
"""

CANDIDATES_A = r"""
const cfg = $('Config').first().json;
const st = $getWorkflowStaticData('global');
st.seen = st.seen || {};
const now = Date.now();
for (const k of Object.keys(st.seen)) if (now - st.seen[k] > 30 * 864e5) delete st.seen[k];

// Country hints: names, demonyms and well-known places. Georgia needs Georgian/Tbilisi (not the US state).
const HINTS = {
  Afghanistan: 'afghan|kabul|taliban', Armenia: 'armenia|yerevan', Azerbaijan: 'azerbaijan|azeri|baku',
  Bahrain: 'bahrain', Bangladesh: 'bangladesh|dhaka|chattogram|chittagong', Bhutan: 'bhutan', Brunei: 'brunei',
  Cambodia: 'cambodia|phnom penh', China: 'china|chinese|beijing|hong kong|xinjiang|uyghur|tibet', Cyprus: 'cyprus|cypriot',
  Georgia: 'georgian|tbilisi', India: 'india|indian|delhi|mumbai|kashmir|manipur', Indonesia: 'indonesia|jakarta|papua',
  Iran: 'iran|tehran', Iraq: 'iraq|baghdad|kurdistan region', Israel: 'israel', Japan: 'japan|tokyo', Jordan: 'jordan|amman',
  Kazakhstan: 'kazakh|astana|almaty', Kuwait: 'kuwait', Kyrgyzstan: 'kyrgyz|bishkek', Laos: 'laos|lao |vientiane',
  Lebanon: 'leban|beirut', Malaysia: 'malaysia|kuala lumpur', Maldives: 'maldiv', Mongolia: 'mongolia|ulaanbaatar',
  Myanmar: 'myanmar|burma|burmese|yangon|junta', Nepal: 'nepal|kathmandu', 'North Korea': 'north korea|pyongyang',
  Oman: 'oman|muscat', Pakistan: 'pakistan|islamabad|karachi|lahore|balochistan|peshawar', Palestine: 'palestin|gaza|west bank',
  Philippines: 'philippine|filipino|manila|mindanao', Qatar: 'qatar|doha', 'Saudi Arabia': 'saudi|riyadh',
  Singapore: 'singapore', 'South Korea': 'south korea|seoul', 'Sri Lanka': 'sri lanka|colombo|tamil', Syria: 'syria|damascus',
  Taiwan: 'taiwan|taipei', Tajikistan: 'tajik|dushanbe', Thailand: 'thailand|thai |bangkok', 'Timor-Leste': 'timor',
  Turkey: 'turkey|türkiye|turkish|istanbul|ankara', Turkmenistan: 'turkmen', 'United Arab Emirates': 'emirat|uae|dubai|abu dhabi',
  Uzbekistan: 'uzbek|tashkent', Vietnam: 'vietnam|hanoi|ho chi minh', Yemen: 'yemen|sanaa|houthi',
};
const HINT_RE = Object.entries(HINTS).map(([c, re]) => [c, new RegExp('\\b(' + re + ')', 'i')]);
const TOPIC = /(journalist|reporter|editor|correspondent|photograph|camera|media|press|newspaper|broadcaster|blogger|youtuber|podcast|cartoonist|writer|activist|human rights|rights defender|dissident|lawyer|internet|shutdown|censor|cyber|sedition|blasphemy|disappear|torture|custod|extrajudicial|protest)/i;

const items = $('Parse feeds').all().map(i => i.json)
  .filter(a => now - a.published < cfg.lookback_hours * 3600e3)
  .map(a => {
    const text = a.title + ' ' + a.summary;
    const countries = HINT_RE.filter(([, re]) => re.test(text)).map(([c]) => c);
    return { ...a, countries };
  })
  .filter(a => a.countries.length && TOPIC.test(a.title + ' ' + a.summary));

const key = s => String(s).toLowerCase().replace(/[^a-z0-9 ]/g, '').split(/\s+/).filter(w => w.length > 2).slice(0, 9).join(' ');
const seenNow = new Set();
const fresh = [];
for (const a of items.sort((x, y) => (y.kind === 'ngo') - (x.kind === 'ngo') || y.published - x.published)) {
  const k = key(a.title);
  const lk = a.link.replace(/[?#].*$/, '');
  if (seenNow.has(k) || seenNow.has(lk) || st.seen[k] || st.seen[lk]) continue;
  seenNow.add(k); seenNow.add(lk);
  fresh.push({ ...a, _key: k, _lk: lk });
}
const candidates = fresh.slice(0, 70).map((a, i) => ({ id: i + 1, ...a }));
const recent = $('Recent BNN posts').all().map(i => i.json && i.json.title && (i.json.title.rendered || i.json.title)).filter(Boolean);
if (!candidates.length) return [];
return [{ json: { candidates, recent } }];
"""

TRIAGE_BODY = r"""={{ JSON.stringify({
  model: $('Config').first().json.models.fast,
  reasoning_effort: 'low',
  response_format: { type: 'json_object' },
  messages: [
    { role: 'system', content: 'You are the desk editor of BNN Asia, a press-freedom and human-rights organisation. Select which candidate news items deserve a BNN Asia country alert today.\n\nRULES FROM THE BNN ASIA RULEBOOK:\n' + $('Config').first().json.rulebook + '\n\nTASK: Group candidates that describe the same incident. Return only incidents that fit WHAT WE COVER, happened in one of these countries: ' + Object.keys($('Config').first().json.countries).join(', ') + ', and are not already covered by a recent BNN Asia post. Be strict: BNN Asia publishes at most 2 alerts a day, so pick only the most serious, clearly Asian, well-sourced incidents; returning fewer or none is fine. Rank by severity (killing > enforced disappearance or abduction > imprisonment or sentence > arrest or detention > physical attack > charges or lawsuit > threats or harassment > restrictive law or shutdown) and by how many independent items report it. Return at most ' + $('Config').first().json.max_posts + ' incidents.\n\nReply with JSON only: {"stories":[{"candidate_ids":[numbers, best source first],"country":"exact country name from the list","type":"killing|abduction|imprisonment|arrest|attack|legal_harassment|threat|law_or_shutdown|other_violation","victim":"who","priority":1-5,"reason":"one sentence"}]}. Use {"stories":[]} when nothing qualifies.' },
    { role: 'user', content: JSON.stringify({ today: new Date().toISOString().slice(0, 10), recent_bnn_posts: $json.recent, candidates: $json.candidates.map(c => ({ id: c.id, title: c.title, summary: (c.summary || '').slice(0, 300), source: c.source, kind: c.kind, published: new Date(c.published).toISOString().slice(0, 16), country_hints: c.countries })) }) }
  ]
}) }}"""

PICK_A = r"""
const cfg = $('Config').first().json;
const st = $getWorkflowStaticData('global');
st.seen = st.seen || {};
const cands = $('Candidates').first().json.candidates;
for (const c of cands) { st.seen[c._key] = Date.now(); st.seen[c._lk] = Date.now(); }  // never triage the same item twice
let parsed = {};
try { parsed = JSON.parse($json.choices[0].message.content); } catch (e) { return []; }
const byId = Object.fromEntries(cands.map(c => [c.id, c]));
const out = [];
for (const s of (parsed.stories || []).slice(0, cfg.max_posts)) {
  if (!cfg.countries[s.country]) continue;
  const items = (s.candidate_ids || []).map(id => byId[id]).filter(Boolean);
  if (!items.length) continue;
  out.push({ json: {
    country: s.country, type: s.type, victim: s.victim, priority: s.priority, reason: s.reason,
    link: items[0].link, source_title: items[0].title,
    other_reports: items.slice(1, 5).map(i => ({ title: i.title, summary: (i.summary || '').slice(0, 500) })),
    first_summary: items[0].summary || '',
    published: new Date(items[0].published).toISOString(),
    trusted: items.some(i => i.kind === 'ngo') || items.length >= 2,
  }});
}
return out;
"""

EXTRACT_A = DECODE_JS + r"""
const story = $('Pick stories').item.json;
const html = typeof $json.data === 'string' ? $json.data : '';
const cleaned = html.replace(/<script[\s\S]*?<\/script>/gi, ' ').replace(/<style[\s\S]*?<\/style>/gi, ' ')
  .replace(/<(nav|footer|header|aside|form)[\s\S]*?<\/\1>/gi, ' ');
const paras = (cleaned.match(/<p[\s>][\s\S]*?<\/p>/gi) || []).map(decode).filter(p => p.length > 60);
let text = paras.join('\n\n').slice(0, 9000);
if (text.length < 400) {
  text = [story.source_title, story.first_summary, ...story.other_reports.map(r => r.title + '. ' + r.summary)].join('\n\n');
}
return { json: { ...story, source_text: text } };
"""

WRITE_BODY = r"""={{ JSON.stringify({
  model: $('Config').first().json.models.writer,
  reasoning_effort: 'medium',
  response_format: { type: 'json_object' },
  messages: [
    { role: 'system', content: $('Config').first().json.rulebook + '\n\nCOUNTRY LIST: ' + Object.keys($('Config').first().json.countries).join(', ') + '\n\nWrite one BNN Asia country alert from the material the user gives you. Reply with JSON only, keys: {"reject":false,"reject_reason":"","country":"exact name from the country list","title":"","body_html":"","lead_summary":"","card_title":"","seo_title":"max 60 characters","seo_description":"max 155 characters","focus_keyword":"","slug":"lowercase-words-with-hyphens, max 8 words","photo_query":"","image_prompt":"","image_alt":""}. Set reject:true with a reason if the material does not meet the rulebook.' },
    { role: 'user', content: JSON.stringify({ today: new Date().toISOString().slice(0, 10), country_hint: $json.country, incident_type: $json.type, victim_hint: $json.victim, first_reported: $json.published, source_headline: $json.source_title, source_text: $json.source_text, other_reports: $json.other_reports }) }
  ]
}) }}"""

CHECK_BODY = r"""={{ JSON.stringify({
  model: $('Config').first().json.models.fast,
  reasoning_effort: 'medium',
  response_format: { type: 'json_object' },
  messages: [
    { role: 'system', content: 'You are the fact checker of BNN Asia. Compare the DRAFT with the SOURCE material and with the rulebook below. Check: every name, number, date, place, charge and quote in the draft is supported by the source; nothing is invented; allegations are attributed; no motive is stated as fact; no media outlet or website is named and there is no source link; no run of more than 8 words is copied from the source; minors and survivors of sexual violence are not named; the title follows the format; the last paragraph is the standard BNN Asia paragraph. If problems can be fixed by deleting or rewording, fix them and return verdict "fix" with the corrected title and body_html. If the story does not meet the rulebook at all, return "reject".\n\nRULEBOOK:\n' + $('Config').first().json.rulebook + '\n\nReply with JSON only: {"verdict":"pass|fix|reject","problems":["..."],"title":"","body_html":""}' },
    { role: 'user', content: JSON.stringify({ SOURCE: $('Extract text').item.json.source_text, OTHER_REPORTS: $('Extract text').item.json.other_reports, DRAFT: (() => { try { return JSON.parse($json.choices[0].message.content); } catch (e) { return {}; } })() }) }
  ]
}) }}"""

APPROVE_A = r"""
const cfg = $('Config').first().json;
const ENDING = '<p>BNN Asia promotes and defends press freedom, human rights and good governance, and the freedom to inform and be informed across Asia.</p>';
const out = [];
const checks = $input.all();
const drafts = $('Write (AI)').all();
const facts = $('Extract text').all();
checks.forEach((item, i) => {
  let d = {}, q = {};
  try { d = JSON.parse(drafts[i].json.choices[0].message.content); } catch (e) { return; }
  try { q = JSON.parse(item.json.choices[0].message.content); } catch (e) { q = { verdict: 'reject', problems: ['checker failed'] }; }
  if (d.reject || q.verdict === 'reject') return;
  if (q.verdict === 'fix') { if (q.title) d.title = q.title; if (q.body_html) d.body_html = q.body_html; }
  const country = cfg.countries[d.country] ? d.country : facts[i].json.country;
  const term = cfg.countries[country];
  if (!term || !d.title || !d.body_html) return;
  // Clean HTML: keep only the allowed tags, then add BNN Asia colours and the press-release footer.
  let body = String(d.body_html)
    .replace(/<(?!\/?(p|strong|em|ul|li|h3)\b)[^>]*>/gi, '')
    .replace(/<(p|strong|em|ul|li|h3)\b[^>]*>/gi, '<$1>')
    .trim();
  if (!body.includes('freedom to inform and be informed')) body += '\n' + ENDING;
  body = body
    .replace(/<strong>/g, '<strong style="color:#c8102e;">')
    .replace(/<h3>/g, '<h3 style="color:#c8102e;font-size:1.1em;margin-top:1.4em;">')
    .replace(/<ul>/g, '<ul style="margin-left:1.2em;">')
    .replace(/<li>/g, '<li style="margin-bottom:.6em;">')
    .replace(/(<\/(p|ul|h3)>)\s*/g, '$1\n\n');
  body += '\n<p style="text-align:center;color:#c8102e;font-weight:700;letter-spacing:.2em;">###</p>\n\n'
       + '<h3 style="color:#c8102e;font-size:1.1em;">About BNN Asia</h3>\n\n'
       + '<p>Borderless News Network Asia (BNN Asia) is an independent organisation that promotes and defends press freedom, human rights and good governance across Asia. It monitors attacks on journalists, online activists and human rights defenders and calls for justice for those targeted.</p>';
  // Publish now (approval auto) or save as draft for an editor.
  const scheduled = cfg.approval === 'auto';
  const when = Date.now();
  const slug = String(d.slug || d.title).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 70);
  out.push({ json: {
    post: { title: d.title.trim(), content: body, status: scheduled ? 'publish' : 'draft',
            date_gmt: new Date(when).toISOString().slice(0, 19), slug, country_select: [term.id] },
    seo: { rank_math_title: d.seo_title || d.title, rank_math_description: d.seo_description || d.lead_summary || '', rank_math_focus_keyword: d.focus_keyword || '' },
    image: { query: d.photo_query || ('' + country + ' journalists'), prompt: d.image_prompt || ('Symbolic documentary photograph about press freedom in ' + country), alt: d.image_alt || ('Illustration for a BNN Asia alert on ' + country), caption: 'Illustration: BNN Asia' },
    country, slug, checker_notes: q.problems || [],
  }});
});
return out;
"""

IMAGE_BODY = r"""={{ JSON.stringify({
  model: $('Config').first().json.models.image,
  prompt: $json.image.prompt + ' Photorealistic documentary photograph, natural light, muted colours, serious mood, shallow depth of field, landscape 3:2. No people faces, no text, no letters, no numbers, no logos, no watermark, no flags, no blood, no graphic violence.',
  size: '1536x1024',
  quality: 'medium',
  output_format: 'jpeg',
  n: 1
}) }}"""

TOFILE_A = r"""
const meta = $('Has free photo?').item.json;
const b64 = $json.data && $json.data[0] && $json.data[0].b64_json;
if (!b64) return { json: { ...meta, image_error: $json.error ? JSON.stringify($json.error).slice(0, 300) : 'no image' } };
return { json: meta, binary: { image: { data: b64, mimeType: 'image/jpeg', fileName: meta.slug + '.jpg', fileExtension: 'jpg' } } };
"""

PHOTO_A = r"""
// Look for a real, free-licensed photo on Wikimedia Commons (CC BY, CC BY-SA, CC0 or public domain).
// Credit the photographer under the post. If nothing suitable is found, flag the item for an AI illustration.
const meta = $json;
const OK = /^(cc[- ]?by(-sa)?([- ]\d(\.\d)?)?|cc0|public domain|pd\b)/i;
const UA = { 'User-Agent': 'BNNAsiaMonitor/1.0 (https://www.bnnasia.org; info@bnnasia.org)' };
const queries = [meta.image.query, meta.country + ' press freedom', meta.country + ' city'].filter(Boolean);
try {
  for (const q of queries) {
    const r = await this.helpers.httpRequest({ url: 'https://commons.wikimedia.org/w/api.php', headers: UA, json: true,
      qs: { action: 'query', format: 'json', generator: 'search', gsrnamespace: 6, gsrsearch: q + ' filetype:bitmap',
            gsrlimit: 25, prop: 'imageinfo', iiprop: 'url|extmetadata|size|mime', iiurlwidth: 1600 } });
    const pages = Object.values((r.query || {}).pages || {}).sort((a, b) => a.index - b.index);
    for (const pg of pages) {
      const ii = (pg.imageinfo || [])[0];
      if (!ii || ii.mime !== 'image/jpeg' || ii.width < 1200 || ii.width < ii.height) continue;
      if (/corpse|dead|blood|injur|wound|nude|logo|map|flag|coat of arms|diagram|chart/i.test(pg.title)) continue;
      const m = ii.extmetadata || {};
      const lic = String((m.LicenseShortName || {}).value || '');
      if (!OK.test(lic) || /nc|nd/i.test(lic)) continue;
      const artist = String((m.Artist || {}).value || 'Unknown').replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim().slice(0, 80);
      const licUrl = String((m.LicenseUrl || {}).value || '');
      const buf = await this.helpers.httpRequest({ url: ii.thumburl || ii.url, headers: UA, encoding: 'arraybuffer' });
      const credit = `Photo: ${artist} / ${lic}, via Wikimedia Commons`;
      const creditHtml = `<p style="font-size:.85em;color:#666;"><em>Photo: <a href="${ii.descriptionurl}" rel="nofollow noopener" target="_blank">${artist}</a> / `
        + (licUrl ? `<a href="${licUrl}" rel="nofollow noopener" target="_blank">${lic}</a>` : lic) + `, via Wikimedia Commons</em></p>\n\n`;
      const content = meta.post.content.replace('<p style="text-align:center;', creditHtml + '<p style="text-align:center;');
      const alt = String((m.ImageDescription || {}).value || meta.image.alt).replace(/<[^>]+>/g, '').trim().slice(0, 125);
      return { json: { ...meta, post: { ...meta.post, content }, image: { ...meta.image, alt, caption: credit }, photo_source: ii.descriptionurl, need_ai: false },
               binary: { image: await this.helpers.prepareBinaryData(Buffer.from(buf), meta.slug + '.jpg', 'image/jpeg') } };
    }
  }
} catch (e) { /* fall back to an illustration */ }
return { json: { ...meta, need_ai: true } };
"""

POST_BODY = r"""={{ JSON.stringify({
  title: $('Image ready').item.json.post.title,
  content: $('Image ready').item.json.post.content,
  status: $('Image ready').item.json.post.status,
  date_gmt: $('Image ready').item.json.post.date_gmt,
  slug: $('Image ready').item.json.post.slug,
  country_id: $('Image ready').item.json.post.country_select[0],
  featured_media: ($json && $json.id) || 0,
  seo: { title: $('Image ready').item.json.seo.rank_math_title, description: $('Image ready').item.json.seo.rank_math_description, focus_keyword: $('Image ready').item.json.seo.rank_math_focus_keyword }
}) }}"""

SUMMARY_A = r"""
const rows = $('Create post').all().map(i => i.json).filter(p => p && p.id);
return [{ json: { published_or_scheduled: rows.length, posts: rows.map(p => ({ id: p.id, status: p.status, date: p.date, link: p.link })) } }];
"""


GATE_A = r"""
// Runs every hour 08:00-23:00 Dhaka. Picks one random hour per day and lets only that run through,
// then waits a random number of minutes, so posts go out at a different time each day.
const st = $getWorkflowStaticData('global');
const now = new Date(Date.now() + 6 * 3600e3);          // Dhaka clock
const day = now.toISOString().slice(0, 10), hour = now.getUTCHours();
if (st.gateDay !== day) { st.gateDay = day; st.gateHour = 8 + Math.floor(Math.random() * 16); st.gateDone = false; }
if (st.gateDone || hour < st.gateHour) return [];
st.gateDone = true;
return [{ json: { wait_minutes: Math.floor(Math.random() * 50), day, hour } }];
"""


def build_a():
    X = 0
    nodes = [
        {"parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "0 8-23 * * *"}]}}, "id": nid(),
         "name": "Hourly 08-23", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [X - 660, 0]},
        code("Random time gate", GATE_A, [X - 440, 0]),
        {"parameters": {"amount": "={{ $json.wait_minutes }}", "unit": "minutes"}, "id": nid(), "name": "Random wait",
         "type": "n8n-nodes-base.wait", "typeVersion": 1.1, "position": [X - 220, 0], "webhookId": nid()},
        {"parameters": {}, "id": nid(), "name": "Run now (test)", "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1,
         "position": [X, 200]},
        code("Config", CONFIG_A, [220, 100]),
        code("Sources", SOURCES_A, [440, 100]),
        http("Fetch feeds", [660, 100], "GET", "={{ $json.url }}", response="text", timeout=40000,
             headers=[("User-Agent", "Mozilla/5.0 (compatible; BNNAsiaMonitor/1.0; +https://www.bnnasia.org)")]),
        code("Parse feeds", PARSE_A, [880, 100]),
        http("Recent BNN posts", [1100, 100], "GET",
             "={{ $('Config').first().json.wp_base }}/wp-json/wp/v2/country_news",
             query=[("per_page", "40"), ("_fields", "id,title,date")], execute_once=True),
        code("Candidates", CANDIDATES_A, [1320, 100]),
        http("Triage (AI)", [1540, 100], "POST", "https://api.openai.com/v1/chat/completions", auth="openAiApi",
             json_body=TRIAGE_BODY, timeout=180000, on_error=False, retry=True),
        code("Pick stories", PICK_A, [1760, 100]),
        http("Fetch article", [1980, 100], "GET", "={{ $json.link }}", response="text", timeout=30000,
             headers=[("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131 Safari/537.36")]),
        code("Extract text", EXTRACT_A, [2200, 100], each=True),
        http("Write (AI)", [2420, 100], "POST", "https://api.openai.com/v1/chat/completions", auth="openAiApi",
             json_body=WRITE_BODY, timeout=300000, on_error=False, retry=True),
        http("Check (AI)", [2640, 100], "POST", "https://api.openai.com/v1/chat/completions", auth="openAiApi",
             json_body=CHECK_BODY, timeout=300000, on_error=False, retry=True),
        code("Approve", APPROVE_A, [2860, 100]),
        code("Find free photo", PHOTO_A, [2970, 100], each=True),
        {"parameters": {"conditions": {"options": {"caseSensitive": True, "typeValidation": "loose", "version": 2},
                        "conditions": [{"id": nid(), "leftValue": "={{ $json.need_ai }}", "rightValue": False,
                                        "operator": {"type": "boolean", "operation": "false", "singleValue": True}}],
                        "combinator": "and"}, "looseTypeValidation": True, "options": {}},
         "id": nid(), "name": "Has free photo?", "type": "n8n-nodes-base.if", "typeVersion": 2.2, "position": [3080, 100]},
        http("Make image (AI)", [3190, 260], "POST", "https://api.openai.com/v1/images/generations", auth="openAiApi",
             json_body=IMAGE_BODY, timeout=300000, retry=True),
        code("Image file", TOFILE_A, [3300, 260], each=True),
        {"parameters": {}, "id": nid(), "name": "Image ready", "type": "n8n-nodes-base.merge", "typeVersion": 3, "position": [3410, 100]},
        http("Upload image", [3520, 100], "POST", "={{ $('Config').first().json.wp_base }}/wp-json/bnn-autopilot/v1/media",
             generic="httpHeaderAuth", binary_field="image",
             query=[("filename", "={{ $json.slug }}"), ("alt", "={{ $json.image.alt }}"),
                    ("caption", "={{ $json.image.caption }}"), ("title", "={{ $json.post.title }}")],
             headers=[("Content-Type", "image/jpeg")]),
        http("Create post", [3740, 100], "POST",
             "={{ $('Config').first().json.wp_base }}/wp-json/bnn-autopilot/v1/post", generic="httpHeaderAuth",
             json_body=POST_BODY, on_error=False, retry=True),
        code("Summary", SUMMARY_A, [3960, 100]),
        {"parameters": {"source": "database", "workflowId": {"__rl": True, "value": "kOLTbtwFAQBPp11f", "mode": "id"},
                        "options": {"waitForSubWorkflow": False}},
         "id": nid(), "name": "Post to social now", "type": "n8n-nodes-base.executeWorkflow", "typeVersion": 1.2,
         "position": [4180, 100]},
    ]
    names = ["Config", "Sources", "Fetch feeds", "Parse feeds", "Recent BNN posts", "Candidates", "Triage (AI)",
             "Pick stories", "Fetch article", "Extract text", "Write (AI)", "Check (AI)", "Approve", "Find free photo", "Has free photo?"]
    tail = ["Image ready", "Upload image", "Create post", "Summary", "Post to social now"]
    conns = merge(chain("Hourly 08-23", "Random time gate", "Random wait", "Config"), chain("Run now (test)", "Config"), chain(*names), chain(*tail),
                  {"Has free photo?": {"main": [[{"node": "Image ready", "type": "main", "index": 0}], [{"node": "Make image (AI)", "type": "main", "index": 0}]]}},
                  chain("Make image (AI)", "Image file"),
                  {"Image file": {"main": [[{"node": "Image ready", "type": "main", "index": 1}]]}})
    return workflow("BNN Asia · Rights Monitor (daily, random 08–24)", nodes, conns)


# ---------------------------------------------------------------------------------------------------------------
# B. Social publisher
# ---------------------------------------------------------------------------------------------------------------
CONFIG_B = """// ===== BNN Asia social settings: edit here =====
return [{ json: {
  wp_base: 'https://www.bnnasia.org',
  card_url: 'https://api.bnnasia.org/api/v1/photocard.png',
  facebook_page_id: '998194126711977',   // BNN Asia page
  graph_version: 'v23.0',
  max_per_run: 2,
  max_per_day: 2,               // most social posts per Dhaka day
  flags: %s,
  hashtags: ['#BNNAsia', '#PressFreedom', '#HumanRights'],
}}];
""" % js_obj(FLAGS)

SELECT_B = SOFTEN_JS + DECODE_JS + r"""
const cfg = $('Config').first().json;
const st = $getWorkflowStaticData('global');
st.shared = st.shared || {};
const posts = $('Latest posts').all().map(i => i.json).filter(p => p && p.id);
if (!st.initialised) {               // first run: everything already on the site counts as shared
  posts.forEach(p => { st.shared[p.id] = Date.now() - 2 * 864e5; });
  st.initialised = true;
  return [];
}
for (const k of Object.keys(st.shared)) if (Date.now() - st.shared[k] > 60 * 864e5) delete st.shared[k];
const dhakaDay = t => new Date(t + 6 * 3600e3).toISOString().slice(0, 10);
const today = dhakaDay(Date.now());
const sharedToday = Object.values(st.shared).filter(t => dhakaDay(t) === today).length;
const room = Math.max(0, Math.min(cfg.max_per_run, (cfg.max_per_day || 2) - sharedToday));
const fresh = posts
  .filter(p => !st.shared[p.id] && Date.now() - Date.parse(p.date_gmt + 'Z') < 24 * 3600e3)
  .sort((a, b) => Date.parse(a.date_gmt) - Date.parse(b.date_gmt))
  .slice(0, room);
return fresh.map(p => {
  const terms = ((p._embedded || {})['wp:term'] || []).flat();
  const countryTerm = terms.find(t => t.taxonomy === 'country_select');
  const country = countryTerm ? decode(countryTerm.name) : '';
  const media = ((p._embedded || {})['wp:featuredmedia'] || [])[0] || {};
  const sizes = (media.media_details || {}).sizes || {};
  const image = (sizes.large || sizes.full || {}).source_url || media.source_url || '';
  const title = decode(p.title.rendered);
  const headline = title.replace(/^[^:]{2,40}:\s*/, '').replace(/^ALERT\s*\|\s*/i, '').trim();
  const firstPara = decode(((p.content.rendered || '').match(/<p[\s>][\s\S]*?<\/p>/i) || [''])[0]);
  const lead = firstPara.length > 300 ? firstPara.slice(0, 297).replace(/\s\S*$/, '') + '…' : firstPara;
  const flag = cfg.flags[country] || '';
  const tag = '#' + country.replace(/[^A-Za-z]/g, '');
  const tags = [...cfg.hashtags, country ? tag : ''].filter(Boolean).join(' ');
  const fb = soften(`${flag} ${country.toUpperCase()} | ${headline}\n\n${lead}\n\n📌 Full story: link in the first comment.\n\n${tags}`).trim();
  let xBody = soften(`${flag} ${country.toUpperCase()}: ${headline}`);
  const xTags = ' ' + tags;
  const room = 280 - xBody.length - xTags.length - 4;
  if (room > 40) xBody += '\n\n' + (soften(lead).length > room ? soften(lead).slice(0, room - 1).replace(/\s\S*$/, '') + '…' : soften(lead));
  return { json: {
    id: p.id, link: p.link, country, image,
    date_label: new Date(p.date).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }),
    card_title: soften(headline), fb_caption: fb, x_text: (xBody + xTags).slice(0, 280),
  }};
});
"""

MARK_B = r"""
const st = $getWorkflowStaticData('global');
st.shared = st.shared || {};
for (const item of $('Select new posts').all()) st.shared[item.json.id] = Date.now();
return [{ json: { shared: $('Select new posts').all().map(i => i.json.link) } }];
"""


def build_b():
    nodes = [
        {"parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "*/15 * * * *"}]}}, "id": nid(),
         "name": "Every 15 minutes", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [0, 0]},
        {"parameters": {"inputSource": "passthrough"}, "id": nid(), "name": "Called by Rights Monitor",
         "type": "n8n-nodes-base.executeWorkflowTrigger", "typeVersion": 1.1, "position": [0, 400]},
        {"parameters": {}, "id": nid(), "name": "Run now (test)", "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1,
         "position": [0, 200]},
        code("Config", CONFIG_B, [220, 100]),
        http("Latest posts", [440, 100], "GET", "={{ $json.wp_base }}/wp-json/wp/v2/country_news",
             query=[("per_page", "10"), ("_embed", "wp:featuredmedia,wp:term"), ("orderby", "date"), ("order", "desc")],
             on_error=False, retry=True),
        code("Select new posts", SELECT_B, [660, 100]),
        http("Photocard", [880, 100], "GET", "={{ $('Config').first().json.card_url }}",
             query=[("image", "={{ $json.image }}"), ("title", "={{ $json.card_title }}"), ("country", "={{ $json.country }}"), ("date", "={{ $json.date_label }}")],
             response="file:card", timeout=90000, on_error=False, retry=True),
        # Facebook branch
        http("Facebook photo", [1100, 0], "POST",
             "=https://graph.facebook.com/{{ $('Config').first().json.graph_version }}/{{ $('Config').first().json.facebook_page_id }}/photos",
             auth="facebookGraphApi",
             multipart=[("source", {"binary": "card"}), ("message", "={{ $('Select new posts').item.json.fb_caption }}"), ("published", "true")],
             timeout=120000),
        http("Facebook link comment", [1320, 0], "POST",
             "=https://graph.facebook.com/{{ $('Config').first().json.graph_version }}/{{ $json.post_id || $json.id }}/comments",
             auth="facebookGraphApi", form=[("message", "={{ 'Read the full story: ' + $('Select new posts').item.json.link }}")]),
        # X branch
        http("X upload image", [1100, 220], "POST", "https://api.x.com/2/media/upload", generic="oAuth2Api",
             multipart=[("media", {"binary": "card"}), ("media_category", "tweet_image")], timeout=120000),
        http("X post", [1320, 220], "POST", "https://api.x.com/2/tweets", generic="oAuth2Api",
             json_body="={{ JSON.stringify({ text: $('Select new posts').item.json.x_text, media: { media_ids: [String(($json.data && $json.data.id) || $json.media_id_string || '')] } }) }}"),
        http("X link reply", [1540, 220], "POST", "https://api.x.com/2/tweets", generic="oAuth2Api",
             json_body="={{ JSON.stringify({ text: 'Full story: ' + $('Select new posts').item.json.link, reply: { in_reply_to_tweet_id: $json.data && $json.data.id } }) }}"),
        code("Mark shared", MARK_B, [1760, 100]),
    ]
    conns = merge(
        chain("Every 15 minutes", "Config"), chain("Run now (test)", "Config"), chain("Called by Rights Monitor", "Config"),
        chain("Config", "Latest posts", "Select new posts", "Photocard"),
        chain("Photocard", "Facebook photo", "Facebook link comment", "Mark shared"),
        chain("Photocard", "X upload image", "X post", "Mark shared")  # X link reply off: a post with a URL costs $0.20 on X,
    )
    return workflow("BNN Asia · Social Publisher (every 15 min)", nodes, conns)


if __name__ == "__main__":
    (HERE / "workflow-a-rights-monitor.json").write_text(json.dumps(build_a(), ensure_ascii=False, indent=2))
    (HERE / "workflow-b-social-publisher.json").write_text(json.dumps(build_b(), ensure_ascii=False, indent=2))
    print("ok")
