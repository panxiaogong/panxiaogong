/* Site JS — SPA nav, sidebar, typewriter, greeting, TOC */
$(function(){

  /* ===== Sidebar Load ===== */
  var openSections = [];

  function loadSidebar(){
    var url = window.__sidebarUrl || '/sidebar.html';
    $.get(url).then(function(html){
      $('#tree').html(html);
      markActive();
      // Expand only ancestors of active item
      $('#tree .md-nav__link--active').parents('.md-nav__item--nested').each(function(){
        var $toggle = $(this).children('.md-nav__toggle');
        $toggle.prop('checked', true);
        openSections.push($toggle.attr('id'));
      });
      // Label click: toggle with 2-open limit
      $('#tree').on('click', '.md-nav__item--nested > .md-nav__link[for]', function(e){
        e.preventDefault();
        var $toggle = $('#' + $(this).attr('for'));
        var wasChecked = $toggle.prop('checked');
        if(wasChecked){
          // Closing: just uncheck
          $toggle.prop('checked', false);
          openSections = openSections.filter(function(id){ return id !== $toggle.attr('id'); });
        } else {
          // Opening: enforce max 2 open (excluding active path)
          var activePathIds = [];
          $('#tree .md-nav__link--active').parents('.md-nav__item--nested').each(function(){
            activePathIds.push($(this).children('.md-nav__toggle').attr('id'));
          });
          var userOpened = openSections.filter(function(id){ return activePathIds.indexOf(id) === -1; });
          if(userOpened.length >= 1){
            // Close the oldest user-opened section
            var toClose = userOpened[0];
            $('#' + toClose).prop('checked', false);
            openSections = openSections.filter(function(id){ return id !== toClose; });
          }
          $toggle.prop('checked', true);
          openSections.push($toggle.attr('id'));
        }
      });
    }).fail(function(){
      $('#tree').html('<ul class="md-nav__list"><li class="md-nav__item"><a href="/" class="md-nav__link">加载失败</a></li></ul>');
    });
  }

  function markActive(){
    var path = normalizePath(location.pathname);
    $('#tree .md-nav__link').removeClass('md-nav__link--active');
    $('#tree .md-nav__item:not(.md-nav__item--nested) .md-nav__link').each(function(){
      var href = $(this).attr('href');
      if(!href || href==='#' || href==='javascript:void(0)') return;
      try {
        if(normalizePath(new URL(href, location.origin).pathname) === path){
          $(this).addClass('md-nav__link--active');
          $(this).parents('.md-nav__item--nested').addClass('md-nav__item--open').children('.md-nav__list').show();
          return false;
        }
      }catch(e){}
    });
  }

  function normalizePath(p){
    try { p = decodeURIComponent(p); } catch(e){}
    p = p.replace(/\/index\.html$/i,'/');
    return p.endsWith('/') ? p : p+'/';
  }

  /* ===== SPA Navigation ===== */
  $(document).on('click', '#tree a, .md-content a, .md-tabs__link', function(e){
    var href = $(this).attr('href');
    if(!href || href==='#' || href==='javascript:void(0)') return;
    if($(this).parent().hasClass('md-nav__item--nested') || $(this).closest('.md-nav__item--nested').length && $(this).parent().is('li')) return;
    if(/^(https?:)?\/\//.test(href)){
      try { if(new URL(href,location.origin).host !== location.host) return; } catch(_){}
    }
    if(/^#/.test(href)) return;
    e.preventDefault();
    navTo(href);
  });

  function navTo(url){
    if(url === location.href) return;
    fetch(url).then(function(r){ if(!r.ok) throw Error(r.status); return r.text(); }).then(function(html){
      var doc = new DOMParser().parseFromString(html,'text/html');
      var art = doc.querySelector('.md-content__inner');
      if(!art) throw Error('No content');
      var $c = $('.md-content__inner');
      $c.css({opacity:0,transition:'opacity .1s'});
      setTimeout(function(){
        $c.html(art.innerHTML);
        $c.css({opacity:1});
        setTimeout(function(){ $c.css({transition:'',opacity:''}); },100);
      },60);
      var t = doc.querySelector('title');
      if(t) document.title = t.textContent;
      history.pushState({url:url},'',url);
      scrollTo({top:0,behavior:'instant'});
      buildTOC();
      markActive();
      var isHome = url==='/'||url==='/index.html';
      $('body').toggleClass('home-page', isHome);
      $('.md-sidebar--primary,.md-sidebar--secondary').toggle(!isHome);
      $('.md-tabs__item').removeClass('md-tabs__item--active');
      if(isHome) $('.md-tabs__item:first').addClass('md-tabs__item--active');
      if(window.__typesetMath) setTimeout(window.__typesetMath,200);
      resetTypewriter();
    }).catch(function(err){
      console.error('SPA:',err);
      location.href = url;
    });
  }

  $(window).on('popstate',function(e){
    var s = e.originalEvent.state;
    if(s&&s.url) navTo(s.url); else location.reload();
  });

  /* ===== Tabs ===== */
  $(document).on('click', '.md-tabs__link', function(e){
    var href = $(this).attr('href');
    if(href==='javascript:void(0)'){
      e.preventDefault();
      $('body').removeClass('home-page');
      $('.md-tabs__item').removeClass('md-tabs__item--active');
      $(this).parent().addClass('md-tabs__item--active');
      $('.md-sidebar--primary').show();
      $('.md-sidebar--secondary').hide();
    }
  });

  /* ===== TOC ===== */
  function buildTOC(){
    var $list = $('#right-toc-list');
    if(!$list.length) return;
    var $a = $('.md-content__inner');
    var $hs = $a.find('h1,h2,h3,h4');
    if(!$hs.length){ $list.html('<li class="md-nav__item"><span class="md-nav__link" style="color:var(--md-default-fg-color--lighter)">暂无目录</span></li>'); return; }
    var min=6; $hs.each(function(){ min=Math.min(min,parseInt(this.tagName.substring(1))); });
    var h=''; $hs.each(function(i){
      var $h=$(this), txt=$.trim($h.text()); if(!txt) return;
      var id=this.id||('toc-'+i); if(!this.id) $h.attr('id',id);
      h+='<li class="md-nav__item toc-level-'+(parseInt(this.tagName.substring(1))-min+1)+'"><a href="#'+id+'" class="md-nav__link">'+esc(txt)+'</a></li>';
    });
    $list.html(h);
    $list.off('click.toc').on('click.toc','a',function(e){
      e.preventDefault();
      var t=$('#'+$(this).attr('href').replace('#',''));
      if(t.length) $('html,body').animate({scrollTop:t.offset().top-80},300);
    });
    function sync(){
      var st=$(window).scrollTop()+100, cur='';
      $hs.each(function(){ if($(this).offset().top<=st) cur=this.id; });
      $list.find('.md-nav__link').removeClass('md-nav__link--active');
      if(cur) $list.find('a[href="#'+cur+'"]').addClass('md-nav__link--active');
    }
    sync(); $(window).off('scroll.toc').on('scroll.toc',sync);
  }

  /* ===== Typewriter ===== */
  (function(){
    var phrases=['理科生','密码学学生','数学爱好者','在 Git 上写书的工匠'];
    var pi=0,ci=0,del=false,el=null;
    function tw(){
      if(!el){ el=document.getElementById('typewriter-text'); if(!el) return; }
      var p=phrases[pi%phrases.length];
      if(del){
        ci--; el.textContent=p.substring(0,ci);
        if(ci===0){ del=false; pi=(pi+1)%phrases.length; setTimeout(tw,800); }
        else setTimeout(tw,50);
      }else{
        ci++; el.textContent=p.substring(0,ci);
        if(ci===p.length){ del=true; setTimeout(tw,2000); }
        else setTimeout(tw,100);
      }
    }
    setTimeout(tw,800);
    window.resetTypewriter=function(){ el=null;pi=0;ci=0;del=false;setTimeout(function(){el=document.getElementById('typewriter-text');if(el)setTimeout(tw,800);},300);};
  })();

  /* ===== Greeting ===== */
  (function(){
    var g=[
      [0,5,'夜深了，注意休息 🌙'],[5,7,'早安，新的一天开始啦 🌅'],[7,9,'早上好，开始美好的一天 ☀️'],
      [9,11,'上午好，保持专注 ✨'],[11,13,'中午好，该休息一下了 🍲'],[13,15,'午后时光，继续加油 ☕'],
      [15,18,'下午好，别忘了喝水 🌤️'],[18,20,'傍晚好，放松一下吧 🌆'],[20,22,'晚上好，享受宁静时光 🌃'],
      [22,24,'夜深了，早点休息哦 🌠']
    ];
    var h=new Date().getHours(), m=g.find(function(x){return h>=x[0]&&h<x[1];});
    var el=document.getElementById('greeting-text');
    if(el) el.textContent=m?m[2]:'夜深了，注意休息 🌙';
  })();

  /* ===== Search ===== */
  $('#search-input-header').on('keydown',function(e){
    if(e.key==='Enter'){
      var q=$.trim($(this).val());
      if(q) window.open('https://www.google.com/search?q='+encodeURIComponent(q+' site:'+location.host),'_blank');
    }
  });

  /* ===== Init ===== */
  loadSidebar();
  if(!window.__isHome) buildTOC();

  function esc(s){ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
});
