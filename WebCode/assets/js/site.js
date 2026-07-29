$(document).ready(function () {
  initSpaNavigation();
  initHighlight();
  initSidebar();
  initHeaderSearch();
  initBackToTop();
  buildRightToc();
  wrapImageWithFancyBox();
  loadSidebar();
});

function initSpaNavigation() {
  $(document).on('click', '#tree a, #content a', function (e) {
    var $link = $(this);
    var href = $link.attr('href');
    if (!href || href === '#') return;

    // 侧边栏目录行：手风琴展开（不导航）
    if ($link.hasClass('directory')) {
      e.preventDefault();
      toggleDir($link.closest('li.directory'));
      return;
    }

    // 跳过外部链接、锚点、非 http/https
    if (/^(https?:)?\/\//.test(href)) {
      var linkHost = '';
      try { linkHost = new URL(href, window.location.origin).host; } catch (_) {}
      if (linkHost && linkHost !== window.location.host) return;
    }

    // 跳过纯锚点
    if (/^#/.test(href)) return;

    e.preventDefault();

    var targetUrl;
    try {
      targetUrl = new URL(href, window.location.origin).href;
    } catch (_) {
      window.location.href = href;
      return;
    }

    // 移动端关闭侧边栏
    if (window.matchMedia('(max-width: 1199px)').matches) {
      $('body').removeClass('sidebar-open');
    }

    navigateTo(targetUrl);
  });

  // 浏览器前进/后退
  $(window).on('popstate', function (e) {
    var state = e.originalEvent.state;
    if (state && state.url) {
      loadPageContent(state.url, false);
    } else {
      window.location.reload();
    }
  });
}

function navigateTo(url) {
  if (url === window.location.href) return;
  loadPageContent(url, true);
}

function loadPageContent(url, pushState) {
  fetch(url)
    .then(function (resp) {
      if (!resp.ok) throw new Error('Page load failed: ' + resp.status);
      return resp.text();
    })
    .then(function (html) {
      // 解析返回的 HTML
      var doc = new DOMParser().parseFromString(html, 'text/html');

      // 提取正文内容
      var newContent = doc.querySelector('#content');
      if (!newContent) throw new Error('Content not found');

      // 替换正文
      $('#content').html(newContent.innerHTML);

      // 更新标题
      var newTitle = doc.querySelector('title');
      if (newTitle) document.title = newTitle.textContent;

      // 更新 URL
      if (pushState) {
        window.history.pushState({ url: url }, '', url);
      }

      // 滚动到顶部
      window.scrollTo(0, 0);

      // 重新初始化内容相关功能
      initHighlight();
      buildRightToc();
      wrapImageWithFancyBox();
      setActiveSidebarItem();

      // 重新渲染数学公式
      if (window.__typesetMath) {
        setTimeout(function () { window.__typesetMath(); }, 100);
      }
    })
    .catch(function (err) {
      console.error('SPA navigation error:', err);
      window.location.href = url;
    });
}

function loadSidebar() {
  var url = window.__sidebarUrl || '/sidebar.html';
  fetch(url)
    .then(function (resp) {
      if (!resp.ok) throw new Error('Sidebar load failed: ' + resp.status);
      return resp.text();
    })
    .then(function (html) {
      $('#tree').html(html);
      setActiveSidebarItem();
      initDirectoryTree();
      initTreeSearch();
    })
    .catch(function (err) {
      console.error(err);
      $('#tree').html('<ul><li class="file active"><a href="/">导航加载失败</a></li></ul>');
    });
}

function normalizePath(path) {
  var decoded;
  try {
    decoded = decodeURIComponent(path);
  } catch (e) {
    decoded = path;
  }
  var normalized = decoded.replace(/\/index\.html$/i, '/');
  if (!normalized.endsWith('/')) {
    normalized += '/';
  }
  return normalized;
}

function setActiveSidebarItem() {
  var currentPath = normalizePath(window.location.pathname);
  $('#tree li.file').removeClass('active');

  // 展开活跃文件所属的目录（不关闭其他已手动展开的目录）
  $('#tree li.file a').each(function () {
    var href = $(this).attr('href');
    if (!href || href === '#') return;

    try {
      var resolved = new URL(href, window.location.origin).pathname;
      resolved = normalizePath(resolved);
      if (resolved === currentPath) {
        var $fileItem = $(this).closest('li.file');
        $fileItem.addClass('active');
        // 只展开路径上的目录，不关其他的
        $fileItem.parents('li.directory').each(function () {
          var $d = $(this);
          if (!$d.hasClass('is-open')) {
            $d.children('ul').show();
            $d.addClass('is-open');
          }
        });
        return false;
      }
    } catch (error) {}
  });
}

function initHighlight() {
  if (!window.hljs) return;

  $('pre code').each(function (index, block) {
    if (typeof hljs.highlightBlock === 'function') {
      hljs.highlightBlock(block);
    }
  });
}

function initSidebar() {
  var mobileMedia = window.matchMedia('(max-width: 1199px)');
  var $body = $('body');
  var wasMobile = mobileMedia.matches;

  function setSidebarOpen(isOpen) {
    $body.toggleClass('sidebar-open', isOpen);
  }

  function syncSidebarState(isInitial) {
    var isMobile = mobileMedia.matches;

    if (isMobile) {
      setSidebarOpen(false);
    } else if (isInitial || wasMobile) {
      setSidebarOpen(true);
    }

    wasMobile = isMobile;
  }

  syncSidebarState(true);
  $(window).on('resize', function () {
    syncSidebarState(false);
  });

  $('#sidebar-toggle, #sidebar-toggle-mobile').on('click', function (e) {
    e.preventDefault();
    setSidebarOpen(!$body.hasClass('sidebar-open'));
  });

  $('#sidebar-close, #sidebar-overlay').on('click', function () {
    if (mobileMedia.matches) {
      setSidebarOpen(false);
    }
  });

  $('#tree').on('click', 'a', function () {
    if (mobileMedia.matches && !$(this).hasClass('directory')) {
      setSidebarOpen(false);
    }
  });
}

function initDirectoryTree() {
  var $tree = $('#tree');
  if (!$tree.length) return;

  var $activeNode = $tree.find('li.file.active');
  if ($activeNode.length) {
    revealTreePath($activeNode, true);
  } else {
    $tree.children('ul').show();
  }
}

function initTreeSearch() {
  var $tree = $('#tree');
  var $input = $('#search-input');
  if (!$tree.length || !$input.length) return;

  function collapseTree() {
    $tree.find('li').show();
    $tree.find('li.directory').removeClass('is-open');
    $tree.find('ul ul').hide();
  }

  function resetTree() {
    collapseTree();

    var $activeNode = $tree.find('li.file.active');
    if ($activeNode.length) {
      revealTreePath($activeNode, true);
    } else {
      $tree.children('ul').show();
    }
  }

  function filterTree(keyword) {
    var query = $.trim(keyword).toLowerCase();
    resetTree();

    if (!query.length) return;

    $tree.find('li').hide();

    var $matches = $tree.find('li.file').filter(function () {
      return $(this).text().toLowerCase().indexOf(query) !== -1;
    });

    if (!$matches.length) return;

    $matches.each(function () {
      var $file = $(this);
      $file.show();
      $file.parents('li.directory').show();
      $file.parents('ul').show();
      $file.parents('li.directory').addClass('is-open');
    });
  }

  $input.on('input', function () {
    filterTree($(this).val());
  });

  $input.on('keydown', function (e) {
    if (e.key === 'Enter') {
      var query = $.trim($(this).val());
      if (!query.length) return;

      window.open(
          searchEngine + encodeURIComponent(query + ' site:' + homeHost),
          '_blank'
      );
    }
  });
}

function initHeaderSearch() {
  var $input = $('#header-search-input');
  if (!$input.length) return;

  $input.on('keydown', function (e) {
    if (e.key === 'Enter') {
      var query = $.trim($(this).val());
      if (!query.length) return;

      window.open(
          searchEngine + encodeURIComponent(query + ' site:' + homeHost),
          '_blank'
      );
    }
  });
}

function revealTreePath($nodeSet, includeSiblings) {
  $nodeSet.each(function () {
    var $node = $(this);
    var $parentLists = $node.parents('ul');
    var $parentDirectories = $node.parents('li.directory');

    $parentLists.show();

    $parentDirectories.each(function () {
      var $directory = $(this);
      $directory.show();
      $directory.addClass('is-open');
      $directory.children('ul').show();

      if (includeSiblings) {
        $directory.siblings('li').show();
      }
    });

    if (includeSiblings) {
      $node.siblings('li').show();
    }
  });
}

function buildRightToc() {
  var $panel = $('#right-toc');
  var $container = $('#right-toc-content');
  var $article = $('#article-content');

  if (!$panel.length || !$container.length) return;

  if (!$article.length) {
    $panel.addClass('is-empty');
    $container.html('<p class="right-toc-empty">当前页面暂无目录</p>');
    return;
  }

  var $headings = $article.find('h1, h2, h3, h4');
  if (!$headings.length) {
    $panel.addClass('is-empty');
    $container.html('<p class="right-toc-empty">当前页面暂无目录</p>');
    return;
  }

  var minLevel = 6;
  $headings.each(function () {
    var level = parseInt(this.tagName.substring(1), 10);
    if (level < minLevel) {
      minLevel = level;
    }
  });

  var tocHtml = '<ul>';
  $headings.each(function (index) {
    var $heading = $(this);
    var text = $.trim($heading.text());
    if (!text.length) return;

    var headingId = this.id;
    if (!headingId) {
      headingId = 'toc-anchor-' + index;
      $heading.attr('id', headingId);
    }

    var level = parseInt(this.tagName.substring(1), 10) - minLevel + 1;
    tocHtml += '<li class="toc-level-' + level + '">';
    tocHtml += '<a href="#' + encodeURIComponent(headingId) + '" data-target-id="' + escapeHtml(headingId) + '">' + escapeHtml(text) + '</a>';
    tocHtml += '</li>';
  });
  tocHtml += '</ul>';

  $panel.removeClass('is-empty');
  $container.html(tocHtml);

  $container.off('click.rightToc').on('click.rightToc', 'a', function (e) {
    var targetId = $(this).attr('data-target-id');
    var targetNode = targetId ? document.getElementById(targetId) : null;
    if (!targetNode) return;
    e.preventDefault();

    $('html, body').stop(true).animate({
      scrollTop: $(targetNode).offset().top - 74
    }, 260);

    if (window.history && typeof window.history.replaceState === 'function') {
      window.history.replaceState(null, '', '#' + encodeURIComponent(targetId));
    }
  });

  function syncActiveHeading() {
    var scrollTop = $(window).scrollTop() + 120;
    var currentId = '';

    $headings.each(function () {
      if ($(this).offset().top <= scrollTop) {
        currentId = this.id;
      }
    });

    $container.find('a').removeClass('is-active');
    if (currentId) {
      $container.find('a').filter(function () {
        return $(this).attr('data-target-id') === currentId;
      }).addClass('is-active');
    }
  }

  syncActiveHeading();
  $(window).off('scroll.rightToc').on('scroll.rightToc', syncActiveHeading);
}

function initBackToTop() {
  var $button = $('#totop-toggle');
  if (!$button.length) return;

  $(window).on('scroll', function () {
    if ($(window).scrollTop() > 280) {
      $button.addClass('is-visible');
    } else {
      $button.removeClass('is-visible');
    }
  });

  $button.on('click', function () {
    $('html, body').animate({ scrollTop: 0 }, 220);
  });
}

function escapeHtml(content) {
  return content
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
}

function wrapImageWithFancyBox() {
  if (typeof $.fancybox === 'undefined') return;

  $('img').not('#header img').each(function () {
    var $image = $(this);
    var imageCaption = $image.attr('alt');
    var $imageWrapLink = $image.parent('a');

    if ($imageWrapLink.length < 1) {
      var src = this.getAttribute('src');
      var idx = src.lastIndexOf('?');
      if (idx !== -1) {
        src = src.substring(0, idx);
      }
      $imageWrapLink = $image.wrap('<a href="' + src + '"></a>').parent('a');
    }

    $imageWrapLink.attr('data-fancybox', 'images');
    if (imageCaption) {
      $imageWrapLink.attr('data-caption', imageCaption);
    }
  });

  $('[data-fancybox="images"]').fancybox({
    buttons: ['slideShow', 'thumbs', 'zoom', 'fullScreen', 'close'],
    thumbs: {
      autoStart: false
    }
  });
}

/* 侧边栏目录切换：最多 2 个同时打开，快速动画 */
function toggleDir($dir) {
  var $sub = $dir.children('ul');
  if (!$sub.length) return;

  if ($dir.hasClass('is-open')) {
    $sub.stop(true, true).slideUp(80);
    $dir.removeClass('is-open');
    return;
  }

  // 计算当前打开的目录数（排除活跃路径上的）
  var $openDirs = $('#tree li.directory.is-open');
  if ($openDirs.length >= 2) {
    // 关闭最早打开的那个（非活跃路径上的）
    $openDirs.each(function () {
      var $d = $(this);
      if (!$d.find('li.file.active').length) {
        $d.children('ul').stop(true, true).slideUp(80);
        $d.removeClass('is-open');
        return false; // 只关一个
      }
    });
  }

  $sub.stop(true, true).slideDown(80);
  $dir.addClass('is-open');
}
