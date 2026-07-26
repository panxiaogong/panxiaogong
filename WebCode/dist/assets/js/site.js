$(document).ready(function () {
  initHighlight();
  initSidebar();
  initHeaderSearch();
  initBackToTop();
  buildRightToc();
  wrapImageWithFancyBox();
  loadSidebar();
});

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
  $('#tree li.directory').removeClass('is-open');

  $('#tree li.file a').each(function () {
    var href = $(this).attr('href');
    if (!href) {
      return;
    }

    try {
      var resolved = new URL(href, window.location.origin).pathname;
      resolved = normalizePath(resolved);
      if (resolved === currentPath) {
        var $fileItem = $(this).closest('li.file');
        $fileItem.addClass('active');
        revealTreePath($fileItem, true);
        return false;
      }
    } catch (error) {
      // Ignore invalid URLs
    }
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

  function setDirectoryOpenState($directory, isOpen) {
    var $subTree = $directory.children('ul');
    var $expander = $directory.children('a').find('.tree-expander');

    if (!$subTree.length) return;

    if (isOpen) {
      $subTree.stop(true, true).slideDown(120);
      $directory.addClass('is-open');
      $expander.attr('aria-expanded', 'true');
    } else {
      $subTree.stop(true, true).slideUp(120);
      $directory.removeClass('is-open');
      $expander.attr('aria-expanded', 'false');
    }
  }

  function toggleDirectory($directory) {
    setDirectoryOpenState($directory, !$directory.hasClass('is-open'));
  }

  $tree.on('click', 'a.directory-toggle-only', function (e) {
    e.preventDefault();
    toggleDirectory($(this).parent('li.directory'));
  });

  $tree.on('click', '.tree-expander', function (e) {
    e.preventDefault();
    e.stopPropagation();
    toggleDirectory($(this).closest('li.directory'));
  });

  $tree.on('keydown', '.tree-expander', function (e) {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    e.preventDefault();
    toggleDirectory($(this).closest('li.directory'));
  });
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
