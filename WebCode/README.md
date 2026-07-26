# MathBlog 站点骨架

这个版本的目录结构已经改成了你想要的形式：

- `D:\MATHBLOG\WebCode`
  只放网站框架、模板、样式、脚本和 Python 构建程序。
- `D:\MATHBLOG` 根目录下的其他同级文件夹
  直接作为内容文件夹使用，例如 `A01-线性代数`、`A02-实分析`、`B01-课程作业`。

这样其他人在进入 GitHub 仓库时，可以直接从仓库根目录找到他们需要的内容专题。

## 目录约定

```text
MATHBLOG/
├─ 00-关于本站.tex
├─ WebCode/
│  ├─ assets/
│  ├─ templates/
│  ├─ build.py
│  └─ config.yml
└─ A01-线性代数/
   ├─ 01-向量与线性组合.tex
   └─ assets/
```

## 如何构建

在 `D:\MATHBLOG` 下运行：

```powershell
python .\WebCode\build.py
```

构建结果会输出到：

```text
D:\MATHBLOG\WebCode\dist
```

如果你想本地预览：

```powershell
python .\WebCode\build.py --serve --port 8000
```

然后访问 `http://127.0.0.1:8000`。

## 内容放置规则

### 1. 内容文件夹

`WebCode` 之外的顶层文件夹，默认都会被视为内容来源。

例如下面这些名字都可以：

- `A01-线性代数`
- `A02-数学分析`
- `B01-课程论文`

### 2. 首页

如果你希望某个文稿作为网站首页，可以在文件最前面写：

```tex
% kind: home
```

当前示例是：

```text
00-关于本站.tex
```

### 3. 普通文章

其他 `.tex` 文件默认都会被当作文章处理，例如：

```text
A01-线性代数/01-向量与线性组合.tex
A01-线性代数/第二章/02-线性映射.tex
```

左侧文章树会自动按真实文件夹层级组织。

### 4. 独立页面

如果你想让某个 `.tex` 文件变成“独立页面”而不是普通文章，可以在文件最前面写：

```tex
% kind: page
```

如果你想把首页直接放在仓库根目录，这也是支持的。

## 推荐元数据写法

在 `.tex` 文件最前面使用注释元数据：

```tex
% title: 文章标题
% slug: linear-algebra/vector-spaces
% date: 2026-06-07
% summary: 一段简短摘要
% tags: LaTeX, 线性代数
```

## 图片资源

推荐把图片放在对应内容文件夹自己的 `assets/` 子目录里。

例如：

```text
A01-线性代数/
├─ 01-向量与线性组合.tex
└─ assets/
   └─ linear-combination.svg
```

然后在 LaTeX 中这样引用：

```tex
\begin{figure}
\includegraphics[width=0.72\textwidth]{assets/linear-combination.svg}
\caption{向量线性组合示意图}
\end{figure}
```

构建时这些资源会自动复制到站点输出目录。

## 当前支持的 LaTeX 结构

- 标题：`\section`、`\subsection`、`\subsubsection`、`\paragraph`
- 列表：`itemize`、`enumerate`
- 公式：
  行内公式 `$...$`、`\(...\)`
  块级公式 `\[...\]`、`$$...$$`、`align`、`equation` 等常见环境
- 强调：`\textbf`、`\textit`、`\emph`、`\underline`、`\texttt`
- 链接：`\href{url}{text}`、`\url{url}`
- 引用环境：`quote`
- 说明块：`definition`、`theorem`、`lemma`、`corollary`、`proposition`、`example`、`remark`、`proof`
- 插图：`figure` + `\includegraphics` + `\caption`
- 代码块：`verbatim`
- 正文内目录：`\tableofcontents`

## 注意

这不是完整 TeX 引擎级别的“全量 LaTeX 转 HTML”，而是一个面向数学博客/学术长文场景的、可维护的静态站点生成器。

如果你后面要继续扩展，比如：

- 自动编号引用 `\ref`
- 表格 `tabular`
- 定理统一编号体系
- BibTeX 参考文献

我们可以继续在这个骨架上往上接。
