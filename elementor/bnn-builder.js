// BNN Asia – HTML-widget → native Elementor converter + design system.
// Runs inside the Elementor editor (needs elementorCommon). Exposes window.BNN.
(function(){
const C = { red:'#C8102E', redDark:'#9E0B23', ink:'#0E1116', ink2:'#1B2029', body:'#3A404A', muted:'#6B7280',
  line:'#E5E7EB', soft:'#F6F7F9', tint:'#FFF4F4', white:'#FFFFFF' };
const FONT = 'Manrope';
const uid = () => Math.random().toString(16).slice(2,9);
const px = (n) => ({unit:'px', size:n, sizes:[]});
const box = (t,r,b,l,u='px') => ({unit:u, top:String(t), right:String(r), bottom:String(b), left:String(l), isLinked:false});
const gap = (n) => ({column:String(n), row:String(n), isLinked:true, unit:'px', size:n});
const typo = (p, size, weight, lh, extra={}) => Object.assign({
  [p+'typography_typography']:'custom', [p+'typography_font_family']:FONT,
  [p+'typography_font_size']:px(size), [p+'typography_font_weight']:String(weight),
  [p+'typography_line_height']: lh ? {unit:'em', size:lh, sizes:[]} : undefined }, extra);
const clean = o => { Object.keys(o).forEach(k=>o[k]===undefined && delete o[k]); return o; };

// ---------- primitives ----------
function con(settings, elements=[], inner=true){
  return {id:uid(), elType:'container', isInner:inner, settings:clean(Object.assign({
    content_width:'full', flex_direction:'column', flex_gap:gap(16) }, settings)), elements};
}
function section(children, {bg=C.white, pt=88, pb=88, dark=false}={}){
  return con({content_width:'boxed', boxed_width:px(1160), background_background:'classic', background_color:bg,
    padding:box(pt,24,pb,24), padding_mobile:box(Math.round(pt*.65),18,Math.round(pb*.65),18), flex_gap:gap(28)}, children, false);
}
function w(type, settings){ return {id:uid(), elType:'widget', widgetType:type, settings:clean(settings), elements:[]}; }
function heading(text, tag='h2', o={}){
  const sizes={h1:52,h2:36,h3:24,h4:20,h5:16,h6:14};
  const s=o.size||sizes[tag];
  return w('heading', Object.assign({title:text, header_size:tag, title_color:o.color||C.ink, align:o.align},
    typo('', s, o.weight||(tag==='h1'||tag==='h2'?800:700), o.lh||(s>30?1.15:1.3),
      {typography_letter_spacing: s>30?px(-0.5):undefined,
       typography_font_size_mobile: s>30?px(Math.round(s*.72)):undefined})));
}
function eyebrow(text, color=C.red){
  return w('heading', Object.assign({title:text.toUpperCase(), header_size:'div', title_color:color},
    typo('',12,800,1.4,{typography_letter_spacing:px(2)})));
}
function text(html, o={}){
  return w('text-editor', Object.assign({editor:html, text_color:o.color||C.body, align:o.align},
    typo('', o.size||17, o.weight||400, o.lh||1.75, {typography_font_size_mobile: px(16)})));
}
function rule(color=C.red,width=56){
  return w('divider',{style:'solid', weight:px(3), color, width:px(width), gap:px(2)});
}
function list(items, o={}){
  return w('icon-list',{icon_list: items.map(t=>({_id:uid(), text:t, selected_icon:{value:'fas fa-check-circle', library:'fa-solid'}})),
    icon_color:o.icon||C.red, text_color:o.color||C.body, icon_size:px(15), space_between:px(10), text_indent:px(10),
    ...typo('icon_',16,500,1.6)});
}
function button(label, url, o={}){
  const primary = o.style!=='ghost';
  return w('button', Object.assign({text:label, link:{url, is_external:/^https?:/.test(url)&&!/bnnasia\.org/.test(url)?'on':'', nofollow:''},
    align:o.align, button_text_color: primary? C.white : (o.dark?C.white:C.ink),
    background_background:'classic', background_color: primary? C.red : 'rgba(0,0,0,0)',
    button_background_hover_background:'classic', button_background_hover_color: primary? C.redDark : (o.dark?C.white:C.ink),
    hover_color: primary? C.white : (o.dark?C.ink:C.white),
    border_border:'solid', border_width:box(2,2,2,2), border_color: primary? C.red : (o.dark?C.white:C.ink),
    border_radius:box(6,6,6,6), text_padding:box(14,26,14,26), hover_animation:''},
    typo('',15,700,1,{typography_letter_spacing:px(.3)})));
}
function image(url, o={}){
  return w('image',{image:{url, id:o.id||'', source:'library'}, image_size:'large', align:o.align||'center',
    image_border_radius:box(12,12,12,12), width: o.width?{unit:'%',size:o.width}:undefined});
}
function html(code){ return w('html',{html:code}); }
function shortcode(sc){ return w('shortcode',{shortcode:sc}); }

function card(children, {cols=3, accent=true, bg=C.white}={}){
  const pct = cols>=4?23.5:cols===3?31.5:cols===2?48.5:100;
  return con({width:{unit:'%',size:pct}, width_tablet:{unit:'%',size:cols>=3?48.5:100}, width_mobile:{unit:'%',size:100},
    background_background:'classic', background_color:bg, padding:box(30,28,30,28), flex_gap:gap(12),
    border_border:'solid', border_width:box(accent?3:1,1,1,1), border_color:C.line,
    border_radius:box(12,12,12,12),
    box_shadow_box_shadow_type:'yes', box_shadow_box_shadow:{horizontal:0,vertical:1,blur:2,spread:0,color:'rgba(16,24,40,0.04)'},
    box_shadow_hover_box_shadow_type:'yes', box_shadow_hover_box_shadow:{horizontal:0,vertical:14,blur:34,spread:-8,color:'rgba(16,24,40,0.16)'},
    border_hover_border:'solid', border_hover_width:box(accent?3:1,1,1,1), border_hover_color: C.red,
    _transition: undefined, border_hover_transition:{unit:'px',size:0.3}}, children);
}
function grid(cards){ return con({flex_direction:'row', flex_wrap:'wrap', flex_gap:gap(24), align_items:'stretch'}, cards); }
function callout(children){
  return con({background_background:'classic', background_color:C.tint, padding:box(28,32,28,32),
    border_border:'solid', border_width:box(0,0,0,4), border_color:C.red, border_radius:box(0,10,10,0), flex_gap:gap(10)}, children);
}
function hero({kicker, title, lead, buttons=[]}){
  const kids=[];
  if(kicker) kids.push(eyebrow(kicker));
  kids.push(heading(title,'h1',{color:C.white, size:54}));
  if(lead) kids.push(text(lead,{color:'#C9CED6', size:19, lh:1.7}));
  if(buttons.length) kids.push(con({flex_direction:'row', flex_wrap:'wrap', flex_gap:gap(14), padding:box(10,0,0,0)},
    buttons.map((b,i)=>button(b.label,b.url,{style:i?'ghost':'primary', dark:true}))));
  const inner = con({width:{unit:'%',size:78}, width_mobile:{unit:'%',size:100}, flex_gap:gap(18)}, kids);
  return con({content_width:'boxed', boxed_width:px(1160), background_background:'gradient',
    background_color:C.ink, background_color_b:'#1C1F2A', background_gradient_type:'linear', background_gradient_angle:{unit:'deg',size:135},
    padding:box(104,24,96,24), padding_mobile:box(72,18,64,18),
    border_border:'solid', border_width:box(0,0,4,0), border_color:C.red}, [inner], false);
}
function ctaBand({title, lead, buttons}){
  return con({content_width:'boxed', boxed_width:px(1160), background_background:'classic', background_color:C.red,
    padding:box(72,24,72,24), flex_direction:'row', flex_wrap:'wrap', justify_content:'space-between', align_items:'center', flex_gap:gap(24)},
    [con({width:{unit:'%',size:62}, width_mobile:{unit:'%',size:100}, flex_gap:gap(10)},[heading(title,'h2',{color:C.white, size:34}), lead?text(lead,{color:'#FFE3E3'}):null].filter(Boolean)),
     con({flex_direction:'row', flex_wrap:'wrap', flex_gap:gap(12), width:{unit:'auto'}}, buttons.map((b,i)=>{
       const bt=button(b.label,b.url,{style:'ghost',dark:true}); if(i===0){Object.assign(bt.settings,{background_color:C.white, button_text_color:C.red, border_color:C.white, button_background_hover_color:C.ink, hover_color:C.white});} return bt;}))], false);
}

// ---------- generic HTML → native converter ----------
const SKIP = new Set(['STYLE','SCRIPT','NOSCRIPT']);
const T = el => (el.textContent||'').replace(/\s+/g,' ').trim();
const inlineHTML = el => {
  const c = el.cloneNode(true);
  c.querySelectorAll('[style],[class]').forEach(n=>{n.removeAttribute('style'); n.removeAttribute('class');});
  return c.innerHTML.replace(/\s+/g,' ').trim();
};
const hasCls = (el, re) => typeof el.className==='string' && re.test(el.className);
const isInteractive = el => el.matches?.('form,button,input,select,textarea,iframe,script') || el.querySelector?.('form,button,input,select,textarea,iframe,script');

function convertHTML(src, opts={}){
  const doc = new DOMParser().parseFromString('<div id="__r">'+src+'</div>','text/html');
  const root = doc.getElementById('__r');
  const scripts = [...root.querySelectorAll('script')].map(s=>s.outerHTML);
  const styles = [...root.querySelectorAll('style')].map(s=>s.outerHTML);
  root.querySelectorAll('style,script,noscript').forEach(n=>n.remove());

  const sections=[]; let cur=null; let heroDone=false; let heroData={title:opts.title||'', lead:'', kicker:opts.kicker||'', buttons:[]};
  let pendingP=[];
  const flushP = (into) => { if(pendingP.length){ into.push(text(pendingP.map(p=>'<p>'+p+'</p>').join(''))); pendingP=[]; } };
  const newSection = (title, sub) => { if(cur){ flushP(cur.kids); } cur={kids:[]}; sections.push(cur);
    if(sub) cur.kids.push(eyebrow(sub)); if(title){ cur.kids.push(heading(title,'h2')); cur.kids.push(rule()); } };

  function cardFrom(el, cols){
    const kids=[]; let ps=[];
    const flush=()=>{ if(ps.length){ kids.push(text(ps.map(p=>'<p>'+p+'</p>').join(''),{size:16,lh:1.7})); ps=[]; } };
    const visit = (n) => {
      for(const c of n.children){
        if(SKIP.has(c.tagName)) continue;
        if(isInteractive(c)){ flush(); kids.push(html(c.outerHTML)); continue; }
        if(/^H[1-6]$/.test(c.tagName) || hasCls(c,/title|head|name/)) { flush(); kids.push(heading(T(c),'h3',{size:20})); continue; }
        if(hasCls(c,/role|badge|tag|eyebrow|label|dateline|flag|step-num|\bs\b|icon/) && T(c).length<40){ flush(); kids.push(eyebrow(T(c))); continue; }
        if(c.tagName==='P'){ ps.push(inlineHTML(c)); continue; }
        if(c.tagName==='UL'||c.tagName==='OL'){ flush(); kids.push(list([...c.querySelectorAll('li')].map(T))); continue; }
        if(c.tagName==='A'){ flush(); kids.push(button(T(c)||'Learn more', c.getAttribute('href')||'#',{style:'ghost'})); continue; }
        if(c.tagName==='IMG'){ flush(); kids.push(image(c.getAttribute('src'))); continue; }
        if(c.children.length) visit(c); else if(T(c)) ps.push(inlineHTML(c));
      }
    };
    visit(el); flush();
    return card(kids,{cols});
  }

  function isGrid(el){
    const ch=[...el.children].filter(c=>!SKIP.has(c.tagName));
    if(ch.length<2) return false;
    if(hasCls(el,/grid|cards|steps|boxes|impact|row|list-grid/)) return ch.every(c=>c.tagName==='DIV'||c.tagName==='ARTICLE'||c.tagName==='LI');
    return ch.length>=2 && ch.every(c=>(c.tagName==='DIV'||c.tagName==='ARTICLE') && c.querySelector('h3,h4,h5') && c.children.length<=6);
  }

  function walk(el){
    for(const c of [...el.children]){
      if(SKIP.has(c.tagName)) continue;
      const tag=c.tagName, txt=T(c);
      // shortcodes in plain text nodes
      if(/^\s*\[[a-z_\-]+[^\]]*\]\s*$/.test(c.textContent) && !c.querySelector('*')){ if(!cur) newSection(); flushP(cur.kids); cur.kids.push(shortcode(c.textContent.trim())); continue; }
      if(isInteractive(c) && !c.querySelector('h1,h2') ){ if(!cur) newSection(); flushP(cur.kids); cur.kids.push(html(c.outerHTML)); continue; }
      const isHeroTitle = tag==='H1' || (!heroDone && hasCls(c,/(^|-)title$|-title\b/) && !c.querySelector('*:not(span):not(strong):not(em)'));
      if(!heroDone && isHeroTitle){ heroData.title = txt; heroDone='lead'; continue; }
      if(heroDone==='lead'){
        if(tag==='P' || hasCls(c,/text|lead|intro|sub/) && !c.querySelector('h2,h3,div')){ heroData.lead += (heroData.lead?' ':'')+txt; continue; }
        if(hasCls(c,/badge|dateline|eyebrow/) && txt.length<60){ heroData.kicker = txt; continue; }
        if(tag==='A'){ heroData.buttons.push({label:txt, url:c.getAttribute('href')||'#'}); continue; }
        if(hasCls(c,/actions|buttons|btns/)){ c.querySelectorAll('a').forEach(a=>heroData.buttons.push({label:T(a), url:a.getAttribute('href')||'#'})); continue; }
        if(hasCls(c,/hero/) || (tag==='DIV' && !c.querySelector('h2,h3,h4') )){ walk(c); continue; }
        heroDone=true;
      }
      if(tag==='H2' || hasCls(c,/subtitle|section-head\b|(^|-)head$/) && !c.querySelector('p,div,ul') ){ newSection(txt); continue; }
      if(hasCls(c,/section-head|head$/) && c.querySelector('h2,h3')){ const h=c.querySelector('h2,h3'); const e=c.querySelector('.eyebrow,[class*=eyebrow]');
        newSection(T(h), e?T(e):null); c.querySelectorAll('p').forEach(p=>pendingP.push(inlineHTML(p))); continue; }
      if(!cur) newSection();
      if(tag==='H3'||tag==='H4'||tag==='H5'){ flushP(cur.kids); cur.kids.push(heading(txt, tag==='H3'?'h3':'h4')); continue; }
      if(tag==='P'){ if(/^\s*\[[a-z_]/.test(txt)){ flushP(cur.kids); cur.kids.push(shortcode(txt)); } else if(txt) pendingP.push(inlineHTML(c)); continue; }
      if(tag==='UL'||tag==='OL'){ flushP(cur.kids); cur.kids.push(list([...c.querySelectorAll(':scope > li')].map(T))); continue; }
      if(tag==='IMG'){ flushP(cur.kids); cur.kids.push(image(c.getAttribute('src'))); continue; }
      if(tag==='A'){ flushP(cur.kids); cur.kids.push(button(txt||'Learn more', c.getAttribute('href')||'#')); continue; }
      if(tag==='TABLE'){ flushP(cur.kids); cur.kids.push(html(c.outerHTML)); continue; }
      if(hasCls(c,/highlight|note|callout|statement|quote/) || tag==='BLOCKQUOTE'){ flushP(cur.kids);
        const inner=[]; const hh=c.querySelector('h3,h4,strong'); if(hh && c.querySelector('h3,h4')) inner.push(heading(T(hh),'h4'));
        const ps=[...c.querySelectorAll('p')]; if(ps.length) inner.push(text(ps.map(p=>'<p>'+inlineHTML(p)+'</p>').join('')));
        else inner.push(text('<p>'+inlineHTML(c)+'</p>'));
        const ul=c.querySelector('ul'); if(ul) inner.push(list([...ul.querySelectorAll('li')].map(T)));
        cur.kids.push(callout(inner)); continue; }
      if(isGrid(c)){ flushP(cur.kids); const items=[...c.children].filter(x=>!SKIP.has(x.tagName));
        const cols = items.length%3===0||items.length>4?3:(items.length===4?4:items.length===2?2:3);
        cur.kids.push(grid(items.map(it=>cardFrom(it, cols)))); continue; }
      if(hasCls(c,/actions|buttons|btns|cta-row/) && c.querySelector('a')){ flushP(cur.kids);
        cur.kids.push(con({flex_direction:'row', flex_wrap:'wrap', flex_gap:gap(12)}, [...c.querySelectorAll('a')].map((a,i)=>button(T(a),a.getAttribute('href')||'#',{style:i?'ghost':'primary'})))); continue; }
      if(c.children.length){ walk(c); continue; }
      if(txt){ pendingP.push(inlineHTML(c)); }
    }
  }
  walk(root);
  if(cur) flushP(cur.kids);
  const out=[];
  if(heroData.title) out.push(hero(heroData));
  sections.filter(s=>s.kids.length).forEach((s,i)=>out.push(section(s.kids,{bg: i%2? C.soft : C.white})));
  if(scripts.length) out.push(html(scripts.join('\n')));
  return out;
}

// Convert a whole Elementor document: every HTML widget is replaced by native sections,
// other native widgets are kept, restyled where cheap.
function convertDoc(elements, opts={}){
  const out=[];
  const visit=(els)=>{ for(const e of els){
    if(e.elType==='widget' && e.widgetType==='html'){ convertHTML(e.settings.html||'', opts).forEach(x=>out.push(x)); }
    else if(e.elType==='widget'){ out.push(section([e],{pt:48,pb:48})); }
    else if(e.elements) visit(e.elements);
  }};
  visit(elements);
  // merge consecutive single-widget wrapper sections
  return out;
}

async function save(postId, elements, status='publish', settings={template:'elementor_header_footer'}){
  return new Promise((ok,no)=>elementorCommon.ajax.addRequest('save_builder',{
    data:{editor_post_id:postId, status, elements, settings},
    success:ok, error:no}, true));
}
async function load(postId){
  const cfg = await new Promise((ok,no)=>elementorCommon.ajax.addRequest('get_document_config',{data:{id:postId}, success:ok, error:no}));
  return cfg.elements;
}
window.BNN = {C, con, section, heading, eyebrow, text, rule, list, button, image, html, shortcode, card, grid, callout, hero, ctaBand, convertHTML, convertDoc, save, load, uid};
})();
