// Курс «AI-инжиниринг» — интерактив (CSP-safe, без inline-обработчиков)
(function(){"use strict";
 var reduce=matchMedia("(prefers-reduced-motion: reduce)").matches;

 // сплэш (один раз за сессию)
 var sp=document.getElementById("splash");
 if(sp){ if(sessionStorage.getItem("ai_splash")){sp.remove();sp=null;}
   else{sessionStorage.setItem("ai_splash","1");
     var killSplash=function(){if(sp){sp.remove();sp=null;}};
     setTimeout(function(){if(sp)sp.classList.add("gone");},reduce?200:1500);
     if(sp)sp.addEventListener("transitionend",killSplash);
     setTimeout(killSplash,reduce?500:2600);} }

 // прогресс чтения
 var pr=document.getElementById("progress");
 function onScroll(){
   var h=document.documentElement, sc=h.scrollTop||document.body.scrollTop;
   var max=h.scrollHeight-h.clientHeight; if(pr)pr.style.width=(max>0?(sc/max*100):0)+"%";
   var tt=document.getElementById("totop"); if(tt)tt.classList.toggle("show",sc>600);
 }
 addEventListener("scroll",onScroll,{passive:true}); onScroll();

 // reveal при скролле
 var rev=document.querySelectorAll(".reveal");
 if("IntersectionObserver" in window && rev.length && !reduce){
   var io=new IntersectionObserver(function(es){es.forEach(function(e){
     if(e.isIntersecting){e.target.classList.add("in");io.unobserve(e.target);}});},{threshold:.1,rootMargin:"0px 0px -8% 0px"});
   rev.forEach(function(el){io.observe(el);});
 } else { rev.forEach(function(el){el.classList.add("in");}); }

 // scrollspy: активный пункт оглавления (+ подсветка родительской части)
 var links=[].slice.call(document.querySelectorAll(".toc a.t1,.toc a.t2"));
 var map={}; links.forEach(function(a){map[a.getAttribute("href").slice(1)]=a;});
 var heads=Object.keys(map).map(function(id){return document.getElementById(id);}).filter(Boolean);
 var tcEl=document.querySelector(".toc");
 if("IntersectionObserver" in window && heads.length){
   var cur=null,curPart=null,started=false;
   var so=new IntersectionObserver(function(es){
     es.forEach(function(e){ if(!e.isIntersecting) return;
       var a=map[e.target.id]; if(!a) return;
       if(cur){cur.classList.remove("active");cur.removeAttribute("aria-current");} a.classList.add("active");a.setAttribute("aria-current","true"); cur=a;
       var part=a; if(a.classList.contains("t2")){var ul=a.closest("ul"); part=ul?ul.previousElementSibling:null;}
       if(curPart&&curPart!==part)curPart.classList.remove("active");
       if(part&&part.classList&&part.classList.contains("t1")){part.classList.add("active");curPart=part;}
       if(started&&tcEl){var ar=a.getBoundingClientRect(),cr=tcEl.getBoundingClientRect();
         if(ar.top<cr.top+44||ar.bottom>cr.bottom-44)a.scrollIntoView({block:"nearest"});}
     });
     started=true;
   },{rootMargin:"-78px 0px -68% 0px",threshold:0});
   heads.forEach(function(h){so.observe(h);});
 }

 // мобильное меню (drawer): Esc, aria-expanded, перевод фокуса
 var bg=document.getElementById("burger");
 function setOpen(o){document.body.classList.toggle("toc-open",o);
   if(bg)bg.setAttribute("aria-expanded",o?"true":"false");
   if(o){var f=document.querySelector(".toc a");if(f){try{f.focus({preventScroll:true});}catch(_){f.focus();}}}
   else if(bg){try{bg.focus({preventScroll:true});}catch(_){bg.focus();}}}
 if(bg){bg.setAttribute("aria-expanded","false");
   bg.addEventListener("click",function(){setOpen(!document.body.classList.contains("toc-open"));});}
 var mask=document.getElementById("tocmask"); if(mask)mask.addEventListener("click",function(){setOpen(false);});
 document.querySelectorAll(".toc a").forEach(function(a){a.addEventListener("click",function(){setOpen(false);});});
 addEventListener("keydown",function(e){if(e.key==="Escape"&&document.body.classList.contains("toc-open"))setOpen(false);});

 // копирование кода (CSP-safe, делегирование на код-бар)
 document.querySelectorAll(".code").forEach(function(box){
   var bar=box.querySelector(".code-bar"); if(!bar)return;
   var btn=document.createElement("button"); btn.className="code-copy"; btn.type="button"; btn.textContent="Копировать";
   bar.appendChild(btn);
   btn.addEventListener("click",function(){
     var c=box.querySelector("pre code"), txt=c?c.textContent:"";
     var done=function(){btn.textContent="✓ Скопировано";btn.classList.add("ok");
       setTimeout(function(){btn.textContent="Копировать";btn.classList.remove("ok");},1400);};
     if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(txt).then(done,done);}
     else{var t=document.createElement("textarea");t.value=txt;document.body.appendChild(t);t.select();
       try{document.execCommand("copy");}catch(_){}t.remove();done();}
   });
 });

 // пауза фоновых анимаций на скрытой вкладке (батарея)
 document.addEventListener("visibilitychange",function(){
   var ps=document.hidden?"paused":"";var b=document.querySelector(".bg");if(b)b.style.animationPlayState=ps;
   document.querySelectorAll(".blob").forEach(function(x){x.style.animationPlayState=ps;});
 });

 // параллакс фона (только мышь)
 var fine=matchMedia("(hover: hover) and (pointer: fine)").matches, bgEl=document.querySelector(".bg");
 if(bgEl&&!reduce&&fine){ bgEl.style.transition="transform .25s ease-out"; var pend=false,px=0,py=0;
   addEventListener("mousemove",function(e){px=(e.clientX/innerWidth-.5)*20;py=(e.clientY/innerHeight-.5)*20;
     if(!pend){pend=true;requestAnimationFrame(function(){bgEl.style.transform="translate("+px+"px,"+py+"px)";pend=false;});}},{passive:true}); }
})();
