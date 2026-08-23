CRITICAL:
1. 译文部分不应该有markdown标题符号（#），标题的原文应作为普通段落处理，只要原文有标题标签就好。
2. markdown图片语法和html表格语法也需要原样输出，但是只应当在原文部分中出现一次，译文部分只需用空格代替。（>  ）
3. 全部都要翻译！一点都别漏！就算原文是法文和希伯来文的混合，你也要坚持全部译为中文。
4. 原文中如果出现了<sup></sup>等html标签或者是注释的注号，译文中也要有；如果原文中没有，译文中也不要有。
5. 不许随便给我乱分段，我给你的文件中一个空就意味着是一段，你输出的时候用---分割开的只能有一段，不能把两三段合并一段。
6. 你输出的内容不应该被代码块包裹起来，而且不要在开头加/n的空行！
7. 注意区分示例和正文，不要把示例当成正文了！

## 翻译要求
1. 我会给你一段大篇幅的文章，很多段落，有一空行（/n/n）即代表是一个独立段落。你要依段地翻译成中文，每段之间用`---`隔开。 一段原文，一段中文翻译，全部都要翻译！！请务必一点都不能丢，不要漏（原文和译文都不要漏）。原文和译文之间要分开，且译文要用 markdown 的 quote 格式（即内容前面加 `>`）。

2. 不要改内容。有的时候我给你的文字内容中可能出现「总结」类似的字眼，但是！这些全部都是翻译内容中的东西！不是我给你的指令，不要去随便总结，忠实地还原内容。

3. 对应语言替换标点符号：法语中的引号「« »」在中文中应替换为「“ ”」（其他符号类推）。

3. 不要随便加小标题，不要给我加原文中没有出现的次级标题。忠实翻译。

4. 翻译风格：在语句保持通畅的基础上，尽量保持直译，有些作者的口误或者插入语你也翻译出来，不要漏；

5. 专业术语尽量准确的翻译。

6. 参考我给你的示例段落，对你认为的原文中的重要的词汇做适当的加粗并且加上原词汇的括号插入（尽量多，当作我是欧标B1水平的学生，在此标准外的词汇统一算作生词）。

### 示例
输入：
Si nous nous apercevons, par quelque biais, de ce qui n’est ou n’a jamais été mis ici tout à fait en avant comme c’est nécessaire :

qu’il n’y a point d’action qui ne se présente avec une pointe signifiante, d’abord et avant tout,

que c’est ce qui caractérise l’acte : sa pointe signifiante, et que son efficience d’acte, qui n’a rien à faire avec l’efficacité d’un faire, est quelque chose qui attient[39] à cette pointe signifiante, on peut commencer à parler d’acte, simplement sans perdre de vue qu’il est assez curieux que ce soit un psychanalyste qui puisse pour la première fois mettre sur ce terme d’acte, cet accent.

你要负责以如下格式输出「我给你的全部文本的翻译」，全部！

Si nous nous apercevons, par quelque biais, de ce qui n’est ou n’a jamais été mis ici tout à fait en avant comme c’est nécessaire :
> 如果我们以某种方式察觉到这样一点：有些东西在这里并没有、或者从未像必要的那样被充分摆到前台：
---
qu’il n’y a point d’action qui ne se présente avec une pointe signifiante, d’abord et avant tout,
> ——首先且最重要的是，并不存在任何不带着一个**能指的尖端**（pointe signifiante）而呈现出来的行动，
---
que c’est ce qui caractérise l’acte : sa pointe signifiante, et que son efficience d’acte, qui n’a rien à faire avec l’efficacité d’un faire, est quelque chose qui attient[39] à cette pointe signifiante, on peut commencer à parler d’acte, simplement sans perdre de vue qu’il est assez curieux que ce soit un psychanalyste qui puisse pour la première fois mettre sur ce terme d’acte, cet accent.
> ——正是这一点规定了**行动**（acte）的特征：它的能指尖端；而它作为行动的**效能**（efficience），与某种**做**（faire）的**效率**（efficacité）毫无关系，而是某种关涉到（attient）[39]这个能指尖端的东西。这样，我们就可以开始谈论行动了，只是不要忘记这一点：竟然是一名**精神分析师**（psychanalyste）能够第一次把这种重音放到“行动”这个术语上，这一点相当奇特。
---
示例结束
