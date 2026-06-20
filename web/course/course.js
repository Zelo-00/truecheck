// Курс «AI-инжиниринг» — ленивая загрузка глав + прогресс (CSP-safe)
(function(){"use strict";
 var reduce=matchMedia("(prefers-reduced-motion: reduce)").matches;
 function esc(s){return (s==null?"":""+s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}

 // сплэш
 var sp=document.getElementById("splash");
 if(sp){ if(sessionStorage.getItem("ai_splash")){sp.remove();sp=null;}
   else{sessionStorage.setItem("ai_splash","1");
     var killSplash=function(){if(sp){sp.remove();sp=null;}};
     setTimeout(function(){if(sp)sp.classList.add("gone");},reduce?200:1500);
     if(sp)sp.addEventListener("transitionend",killSplash);
     setTimeout(killSplash,reduce?500:2600);} }

 // прогресс чтения + наверх
 var pr=document.getElementById("progress"),tt=document.getElementById("totop");
 function onScroll(){var h=document.documentElement,sc=h.scrollTop||document.body.scrollTop,max=h.scrollHeight-h.clientHeight;
   if(pr)pr.style.width=(max>0?(sc/max*100):0)+"%"; if(tt)tt.classList.toggle("show",sc>600);}
 addEventListener("scroll",onScroll,{passive:true}); onScroll();

 // мобильный drawer
 var bg=document.getElementById("burger");
 function setOpen(o){document.body.classList.toggle("toc-open",o);
   if(bg)bg.setAttribute("aria-expanded",o?"true":"false");
   if(o){var f=document.querySelector(".toc a,.toc button");if(f){try{f.focus({preventScroll:true});}catch(_){f.focus();}}}
   else if(bg){try{bg.focus({preventScroll:true});}catch(_){bg.focus();}}}
 if(bg){bg.setAttribute("aria-expanded","false");bg.addEventListener("click",function(){setOpen(!document.body.classList.contains("toc-open"));});}
 var mask=document.getElementById("tocmask"); if(mask)mask.addEventListener("click",function(){setOpen(false);});
 addEventListener("keydown",function(e){if(e.key==="Escape"&&document.body.classList.contains("toc-open"))setOpen(false);});

 // пауза анимаций на скрытой вкладке + параллакс
 document.addEventListener("visibilitychange",function(){var ps=document.hidden?"paused":"";var b=document.querySelector(".bg");
   if(b)b.style.animationPlayState=ps;document.querySelectorAll(".blob").forEach(function(x){x.style.animationPlayState=ps;});});
 var fine=matchMedia("(hover: hover) and (pointer: fine)").matches,bgEl=document.querySelector(".bg");
 if(bgEl&&!reduce&&fine){bgEl.style.transition="transform .25s ease-out";var pend=false,mx=0,my=0;
   addEventListener("mousemove",function(e){mx=(e.clientX/innerWidth-.5)*20;my=(e.clientY/innerHeight-.5)*20;
     if(!pend){pend=true;requestAnimationFrame(function(){bgEl.style.transform="translate("+mx+"px,"+my+"px)";pend=false;});}},{passive:true});}

 // ---------- главы и прогресс ----------
 var content=document.getElementById("content"),hero=document.querySelector(".hero"),chaphead=document.getElementById("chaphead");
 var cms=[].slice.call(document.querySelectorAll(".cm"));
 var total=cms.length, cache={}, current=-1;
 var DONE="ai_course_done_v1",LASTC="ai_course_lastc_v1",LASTY="ai_course_lasty_v1",CHK="ai_course_checks_v1";
 function getDone(){try{return JSON.parse(localStorage.getItem(DONE)||"[]");}catch(_){return[];}}
 function setDoneArr(a){try{localStorage.setItem(DONE,JSON.stringify(a));}catch(_){}}
 function markDone(i){var d=getDone();if(d.indexOf(i)<0){d.push(i);setDoneArr(d);renderProgress();}}
 function getChecks(){try{return JSON.parse(localStorage.getItem(CHK)||"{}");}catch(_){return {};}}
 function setChecks(o){try{localStorage.setItem(CHK,JSON.stringify(o));}catch(_){}}
 function chName(i){var c=cms[i];return c?c.querySelector(".cm-name").textContent:"";}

 var hid2idx={}; document.querySelectorAll(".cm-pt").forEach(function(a){hid2idx[a.getAttribute("href").slice(1)]=+a.dataset.idx;});

 function renderProgress(){
   var d=getDone(),pct=total?Math.round(d.length/total*100):0,el=document.getElementById("tocprog");
   var has=d.length||Object.keys(getChecks()).length;
   if(el){el.innerHTML='<div class="ring" style="--p:'+pct+'"><span>'+pct+'%</span></div>'+
     '<div class="ring-tx"><b>Пройдено '+d.length+' из '+total+'</b><em>'+(total-d.length)+' осталось</em>'+
     (has?'<button class="reset-btn js-reset" type="button">Сбросить прогресс</button>':'')+'</div>';
     var rb=el.querySelector(".js-reset");
     if(rb)rb.addEventListener("click",function(){if(confirm("Сбросить весь прогресс по курсу (включая отметки в чек-листах)?")){
       setDoneArr([]);try{localStorage.removeItem(LASTC);localStorage.removeItem(LASTY);localStorage.removeItem(CHK);}catch(_){}
       content.querySelectorAll(".ck.on").forEach(function(x){x.classList.remove("on");x.setAttribute("aria-checked","false");var l=x.closest("li");if(l)l.classList.remove("done");});
       renderProgress();}});}
   cms.forEach(function(c){c.classList.toggle("done",d.indexOf(+c.dataset.idx)>=0);});
 }

 var revIO,spyIO,endIO;
 function enhance(){
   // появление блоков
   var rev=content.querySelectorAll(".reveal");
   if(revIO)revIO.disconnect();
   if("IntersectionObserver" in window&&!reduce){
     revIO=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.add("in");revIO.unobserve(e.target);}});},{threshold:.08,rootMargin:"0px 0px -6% 0px"});
     rev.forEach(function(el){revIO.observe(el);});
   } else rev.forEach(function(el){el.classList.add("in");});
   // кнопки копирования
   content.querySelectorAll(".code").forEach(function(box){
     var bar=box.querySelector(".code-bar"); if(!bar||bar.querySelector(".code-copy"))return;
     var btn=document.createElement("button");btn.className="code-copy";btn.type="button";btn.textContent="Копировать";bar.appendChild(btn);
     btn.addEventListener("click",function(){var c=box.querySelector("pre code"),txt=c?c.textContent:"";
       var done=function(){btn.textContent="✓ Скопировано";btn.classList.add("ok");setTimeout(function(){btn.textContent="Копировать";btn.classList.remove("ok");},1400);};
       if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(txt).then(done,done);}
       else{var t=document.createElement("textarea");t.value=txt;document.body.appendChild(t);t.select();try{document.execCommand("copy");}catch(_){}t.remove();done();}});
   });
   // интерактивные чек-листы: тап/клик/Enter отмечает пункт, отметки сохраняются
   var checks=getChecks();
   content.querySelectorAll(".ck").forEach(function(ck){
     var key=ck.dataset.k,li=ck.closest("li"); if(!li)return;
     li.classList.add("ck-li");
     if(key&&checks[key]){ck.classList.add("on");ck.setAttribute("aria-checked","true");li.classList.add("done");}
     var toggle=function(){var on=ck.classList.toggle("on");ck.setAttribute("aria-checked",on?"true":"false");li.classList.toggle("done",on);
       var c=getChecks();if(key){if(on)c[key]=1;else delete c[key];setChecks(c);}renderProgress();};
     li.addEventListener("click",function(e){if(e.target.closest("a,button"))return;toggle();});
     ck.addEventListener("keydown",function(e){if(e.key===" "||e.key==="Enter"){e.preventDefault();toggle();}});
   });

   // scrollspy по пунктам активной главы
   if(spyIO)spyIO.disconnect();
   var pts={};document.querySelectorAll('.cm-pt[data-idx="'+current+'"]').forEach(function(a){pts[a.getAttribute("href").slice(1)]=a;});
   var hs=Object.keys(pts).map(function(id){return document.getElementById(id);}).filter(Boolean);
   if("IntersectionObserver" in window&&hs.length){var ca=null;
     spyIO=new IntersectionObserver(function(es){es.forEach(function(e){if(!e.isIntersecting)return;var a=pts[e.target.id];if(!a)return;
       if(ca){ca.classList.remove("active");ca.removeAttribute("aria-current");}a.classList.add("active");a.setAttribute("aria-current","true");ca=a;});},{rootMargin:"-90px 0px -68% 0px",threshold:0});
     hs.forEach(function(h){spyIO.observe(h);});}
   // поздравление в конце главы
   var end=content.querySelector(".chap-end");
   if(end){
     var d=getDone(),already=d.indexOf(current)>=0,shown=already?d.length:d.length+1,last=current>=total-1;
     end.innerHTML='<div class="congrats"><div class="cg-emoji">🎉</div>'+
       '<div class="cg-title">Поздравляем! Вы прошли главу:</div>'+
       '<div class="cg-name">'+esc(chName(current))+'</div>'+
       '<div class="cg-stat">Пройдено глав: '+shown+' из '+total+'</div>'+
       (last?'<div class="cg-done">🏆 Это была последняя глава. Курс пройден — поздравляем!</div>'
            :'<div class="cg-actions"><button class="cg-btn js-next" type="button">Следующая глава: '+esc(chName(current+1))+' →</button></div>')+
       '</div>';
     var nx=end.querySelector(".js-next");if(nx)nx.addEventListener("click",function(){go(current+1);});
     if(endIO)endIO.disconnect();
     if("IntersectionObserver" in window){endIO=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting)markDone(current);});},{threshold:.5});endIO.observe(end);}
   }
 }

 function setChapHead(i){
   if(!chaphead)return;var last=i>=total-1;
   chaphead.innerHTML='<span class="ch-meta">Глава '+(i+1)+' из '+total+'</span>'+
     '<span class="ch-name">'+esc(chName(i))+'</span>'+
     '<span class="ch-nav">'+
       (i>0?'<button class="ch-prev js-prev" type="button">← Назад</button>':'')+
       (!last?'<button class="ch-next js-fwd" type="button">Вперёд →</button>':'')+'</span>';
   var p=chaphead.querySelector(".js-prev");if(p)p.addEventListener("click",function(){go(i-1);});
   var f=chaphead.querySelector(".js-fwd");if(f)f.addEventListener("click",function(){go(i+1);});
 }

 function setActive(i){cms.forEach(function(c){c.classList.toggle("active",+c.dataset.idx===i);});}
 function openChapter(i){var c=cms[i];if(c&&!c.classList.contains("open")){c.classList.add("open");
   var h=c.querySelector(".cm-head");if(h)h.setAttribute("aria-expanded","true");}}

 function fetchChapter(i,cb){
   if(cache[i]!==undefined){cb(cache[i]);return;}
   content.innerHTML='<div class="loader"><span></span></div>';
   fetch("chapters/ch"+i+".html",{credentials:"same-origin"}).then(function(r){if(!r.ok)throw 0;return r.text();})
     .then(function(t){cache[i]=t;cb(t);})
     .catch(function(){content.innerHTML='<div class="load-err">Не удалось загрузить главу.<br><button class="cg-btn js-retry" type="button">Повторить</button></div>';
       var rb=content.querySelector(".js-retry");if(rb)rb.addEventListener("click",function(){delete cache[i];go(i);});});
 }

 function go(i,hid,ry){
   if(i<0||i>=total)return;
   fetchChapter(i,function(htmlStr){
     current=i; content.innerHTML=htmlStr;
     if(hero)hero.style.display=(i===0?"":"none");
     setChapHead(i); setActive(i); openChapter(i); enhance();
     try{localStorage.setItem(LASTC,i);}catch(_){}
     if(hid){var t=document.getElementById(hid);if(t){t.scrollIntoView();window.scrollBy(0,-70);}else window.scrollTo(0,0);}
     else if(ry>0){setTimeout(function(){window.scrollTo(0,ry);},60);}
     else window.scrollTo({top:0,behavior:reduce?"auto":"smooth"});
     try{history.replaceState(null,"","#"+(hid||("chap"+i)));}catch(_){}
     setOpen(false);
   });
 }

 // клик по главе — раскрыть/свернуть подпункты (toggle); меню не закрывается, перехода нет
 cms.forEach(function(c){var h=c.querySelector(".cm-head");if(!h)return;
   h.addEventListener("click",function(){var op=c.classList.toggle("open");h.setAttribute("aria-expanded",op?"true":"false");});});
 // клик по подпункту — перейти туда (и закрыть мобильное меню)
 document.querySelectorAll(".cm-pt").forEach(function(a){a.addEventListener("click",function(e){e.preventDefault();go(+a.dataset.idx,a.getAttribute("href").slice(1));});});
 // переход по hash из других мест (ссылки внутри текста ведут на #sN)
 addEventListener("hashchange",function(){var hid=location.hash.slice(1);if(hid2idx[hid]!==undefined&&hid2idx[hid]!==current)go(hid2idx[hid],hid);});

 // сохранение позиции для «продолжить с места»
 function saveY(){try{localStorage.setItem(LASTY,""+(window.scrollY||window.pageYOffset||0));}catch(_){}}
 addEventListener("pagehide",saveY); addEventListener("beforeunload",saveY);
 document.addEventListener("visibilitychange",function(){if(document.hidden)saveY();});

 // старт — продолжить с последней главы (если нет якоря в адресе)
 renderProgress();
 var si=0,sh=null,ry=0;
 if(location.hash&&hid2idx[location.hash.slice(1)]!==undefined){sh=location.hash.slice(1);si=hid2idx[sh];}
 else{var lc=parseInt(localStorage.getItem(LASTC),10);
   if(!isNaN(lc)&&lc>0&&lc<total){si=lc;ry=parseInt(localStorage.getItem(LASTY),10)||0;}}
 go(si,sh,ry);
})();
