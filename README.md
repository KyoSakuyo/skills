<img width="1791" height="690" alt="github-header-banner" src="https://github.com/user-attachments/assets/cbfb5301-9609-4939-929d-e36a98bbb119" />

此skill的实施旨在使用Google AI工具 Antigravity 对PDF扫描本的书籍进行逐页OCR并借由AI能力校正排版，以生成可编辑的Markdown文本文件，方便后续转换处理和做引用摘抄使用。

## 使用情境示例：

- 将PDF书籍转换为ePub格式，供小屏电子阅读器中阅读。
- 为扫描质量低的PDF书籍增加可读性。
- 将竖排版书籍重录入为横向排版，供阅读障碍读者方便阅读。
- 用AI翻译，制作双语版书籍。
- ……

## 使用有门槛吗？

有一些些，但不多。

- 经济成本：使用Google提供的每5h刷新一次的免费AI额度来完成工作，在工作量不大的情况下完全可以做到0成本。
- 计算机技能：整个工作流中我尽量减少了使用到命令行的场景，如果**不出差错**的话，你可以仅通过向AI发号施令和在图形界面的点击来完成整个流程；如果出了差错（像是环境的配置有问题），可能会需要多出一些些使用命令行侦错的步骤，但你把错误内容告诉AI后，AI会帮助你一步步地解决。
- 科学上网：Of Course！！！

## 具体步骤

### 1. 下载并安装所需的软件
   - [Pandoc](https://github.com/jgm/pandoc/releases)：转换Markdown格式书籍为各种格式。
   - [Python](https://www.python.org/downloads/)：处理执行各项代码任务。
   - [Typora](https://typora.io/)：调用Pandoc；可视化查看markdown文件。
   - [Antigravity](https://antigravity.google/)：Google的AI工具。
   - [Antigravity Tools](https://github.com/lbjlaq/Antigravity-Manager)：为前者补充更多实用性。
   - [我的skills](https://github.com/KyoSakuyo/skills)：谢谢您喜欢🥹

### 2. 配置Typora

   - 打开Typora的偏好设置，在其导出面板中设置好Pandoc的安装位置。

     ![image-20260126102128490](https://s2.loli.net/2026/01/26/buQD6iSyfoG5LwW.png)

     ![image-20260126102208105](https://s2.loli.net/2026/01/26/TsiMDSLBHelfy4R.png)

### 3. 选择合适的目录

   - 在合适的目录（最好是纯英文路径）新建文件夹作为工作区。（以C盘根目录下的OCR文件夹为例）

   - 参考[Antigravity的文档](https://antigravity.google/docs/skills)，在该文件夹下新建`.agent\skills`目录，你将得到如下的目录结构：

     ![image-20260126110353891](https://s2.loli.net/2026/01/26/uBLZQ3GEXCRcF8S.png)

   - 解压下载好的skills, 将pdf-set文件夹复制粘贴到上面的目录，结构如下

     ![image-20260126110608095](https://s2.loli.net/2026/01/26/JTzL8oOrf6aE4mU.png)

### 4. 配置 Antigravity Tools 

   - 在Antigravity Tools的**账号管理**面板中**添加账号**，然后选择下方**操控**栏中的**切换到此账号**

     ![image-20260126102703647](https://s2.loli.net/2026/01/26/QoAWTmeV8PHzv7w.png)

   - 在Antigravity Tools的**API反代**面板中选择**启动服务**

     ![image-20260126103202804](https://s2.loli.net/2026/01/26/Ak6gXbsBLwx1d2p.png)
     
   - 打开工作区文件夹中的`.agent\skills\pdf-set\scripts`目录，找到`secrets.txt`

     ![image-20260126110932232](https://s2.loli.net/2026/01/26/lDme7OLREQTS9pY.png)

   - 在Antigravity Tools的**API反代**面板中找到**多协议支持**，选择Gemini协议后，在下面的**快速集成**选项中单击**复制**按钮，粘贴至`secrets.txt`中保存。

     ![image-20260126111052656](https://s2.loli.net/2026/01/26/JtndNwH2gGF87CT.png)

### 5. 进入Antigravity，打开工作区

   - 在Antigravity的主页面中选择**Open Folder**, 打开你刚刚建立的工作区文件夹

   ![image-20260126111800920](https://s2.loli.net/2026/01/26/sQVh4zA8FYerfyn.png)

   - 在你的workspace中新建文件夹，命名为你要转换的书籍名
     ![image-20260126112402499](https://s2.loli.net/2026/01/26/aFkvQxUOrzdXeoj.png)
     
   - 将书籍粘贴至该目录下（直接拖拽或者复制粘贴）

     ![image-20260126113007315](https://s2.loli.net/2026/01/26/IniCXFuyfDv4EJV.png)

### 6. 安装前置python组件：

   - 对AI施咒：`导入该工作区内的.agent文件夹内的skill,用pdf-set安装前置组件`

     AI会依次帮你安装后续工作所需安装的两个Python库，分别是[google-genai](https://pypi.org/project/google-genai/)和[pdf2image](https://pypi.org/project/pdf2image/)，如果出了问题，AI会一步步告诉你问题出在哪里并解决。

     ![image-20260126125950131](https://s2.loli.net/2026/01/26/cLVAl8j6qTG34fJ.png)

### 7. 将PDF转化为图片

   - 对AI施咒：`导入该工作区内的.agent文件夹内的skill,用pdf-set对【书籍名】分图`

     AI会逐页地把PDF书籍转换为图片格式并且向你报告工作进度，输出结果会在`images`内

     ![image-20260126130307254](https://s2.loli.net/2026/01/26/aUy6Tu3ClQx4p8W.png)

### 8. 开始OCR

   - 对AI施咒：`导入该工作区内的.agent文件夹内的skill,用pdf-set对【书籍名】开始OCR`

     AI会逐页地开始OCR, 并且向你报告工作进度，输出结果会在`ocr-result`内

     ![image-20260126113841068](https://s2.loli.net/2026/01/26/TkCczEVaxyRtJiH.png)

### 9. （可选）OCR查漏补缺

   如果在ocr-result内有【序号.fail.md】的文件，则需要继续向AI施咒：`导入该工作区内的.agent文件夹内的skill,用pdf-set对【书籍名】进行OCR查漏补缺`，等待AI处理完毕后，检查补缺后的文件，若没有问题，手动删除*.fail.md文件。

![image-20260126130904089](https://s2.loli.net/2026/01/26/iljRy74sgEWkId8.png)

![image-20260126131249624](https://s2.loli.net/2026/01/26/qoTlHbreYWQ8NPK.png)

#### 为什么会fail？

因为Antigravity调用API会有道德审查──《索多玛120天》有一半内容都会被屏蔽掉，甚至一本弗洛伊德的精神分析案例书《鼠人》都能被屏蔽掉两三页……除此以外还有版权审查，sometimes 一本书正文都没事，但是最后译者的译后记（可能因为译者发送到了豆瓣上被AI拿来训练了）就被识别成了版权内容，禁止识别，like 《千高原》……

而使用此skill中OCR查漏补缺的步骤可以变相避免审查发生。

### 10. 粗合并

- 对AI施咒：`导入该工作区内的.agent文件夹内的skill,用pdf-set对【书籍名】的全部OCR结果粗合并`

  ![image-20260126133643078](https://s2.loli.net/2026/01/26/cRFC8TlNMideXb5.png)

  命令执行后，会新建文件夹`merge-result`并在其中输出`0.rough.md`

### 11. 修改标题层次

- 使用typora打开`0.rough.md`，打开文章大纲

  ![image-20260126134031911](https://s2.loli.net/2026/01/26/JhU49lIkgnDHMuE.png)

  所有的大标题小标题都被设计为了**二级标题**，你需要手动地给文章设计标题层级──

  - 对照PDF源文件，在Typora的大纲中找到对应的标题内容

  - 按下`Ctrl+1`设置为一级标题、按下`Ctrl+3`设置为三级标题……以此类推

  **注意：设计标题层次时不应给书名设为一级标题，各章节名设为二级标题──书名应该对应于该文件的文件名。**

  **你应该将书的各章节（第一章、第二章……），或书的各部分（第一部、第二部……）设为一级标题。**

  一份处理好的文章大纲应如下👇

  ![image-20260126134912395](https://s2.loli.net/2026/01/26/wrq9JEGMKZ5DFjz.png)

### 12. 分割&排版&排版合并

依次对AI施咒：

- `导入该工作区内的.agent文件夹内的skill,用pdf-set对【书籍名】分割`
- `导入该工作区内的.agent文件夹内的skill,用pdf-set对【书籍名】排版`
- `导入该工作区内的.agent文件夹内的skill,用pdf-set对【书籍名】排版合并`

（或者一起施咒也行……）

![image-20260126140038043](https://s2.loli.net/2026/01/26/j5ViMNDp2wm4TPI.png)

工作区目录中会补全`merge-result`中的文件；新建`typeset-result`文件夹并输出排版好的各章节及全书文件──被命名为`【书籍名】.md` ，示例如下👇

![image-20260126143003150](https://s2.loli.net/2026/01/26/n9c1Gt8srhNjHPz.png)

### 13. 补全书籍图片和被分开的注释

- 用typora打开`【书籍名.md】`文件，按下`Ctrl+F`搜寻⬆️这个emoji符号
  ![image-20260126143125030](https://s2.loli.net/2026/01/26/vbrZTNB2pmkiR7G.png)

  - 搜寻到的结果是被书籍的分页分开的注释，依次把它们手动地拼接上。

    ![image-20260126143311277](https://s2.loli.net/2026/01/26/lZrqx5tBzGb2E4I.png)

- 按下`Ctrl+F`搜寻🀄这个emoji符号，对应页码找到原书中的图片，截图原书，粘贴替换掉🀄

  ![image-20260126143747750](https://s2.loli.net/2026/01/26/bOInXGs3idPF2kQ.png)

### 14. 导出ePub

- 在Typora中依次选择`文件`、`导出`、`Epub`，成功导出epub格式书籍🎉

  ![image-20260126144212551](https://s2.loli.net/2026/01/26/HxJ2ynFN8CmaTG7.png)

  开始阅读吧！

  ![image-20260126144352253](https://s2.loli.net/2026/01/26/CAdzbO8D5FGLIyo.png)

### 15. （可选）翻译

如果你需要对提取出的内容翻译，可以对AI施咒：`导入该工作区内的.agent文件夹内的skill,用pdf-set对【书籍名】的【文件序号】翻译`

注意：

- 这里的文件序号对应的是分割后的文件序号，翻译的输入文件在`typeset-result`中。
- 翻译会使用大量的AI额度，而且一次翻译的内容太多的话，AI会变得笨笨的；如果在完成分割后，每章节仍旧有超过100000字符的内容，建议再次做分割后再进行翻译。
- 建议根据需要自行修改翻译prompt

翻译后的结果会输出在`translate-result`中，检查无误后，对AI施咒：`导入该工作区内的.agent文件夹内的skill,用pdf-set对【书籍名】的翻译结果合并`，即可得到全书译文。

## Q&A

1. Q：什么类型的书籍无法被正确排版？

   A：注释格式过于诡异的书！你可以参考此skills的Github库中的`生成结果参考`中的《像女孩一样丢球》一书，因为原书的PDF格式是在随机1-x页正文后，才会出现一次对应前面好几页内容的尾注，会让AI整个晕掉😵‍💫──生成出的结果注释会乱掉，会稍微影响阅读体验。

2. Q：既然Antigravity本体没有内容审查，为什么要用Antigravity Tools来反代API呢？

   A：因为前者识图时无法准确识别每页的内容边界，很容易将前后页的内容弄混。

3. Q：为什么我出现了Antigravity无法登录，python安装组件没反应……等情况？

   A：很有可能是你的网络环境出了问题，请自行Google检索相关讯息后，检查你的网络配置。

4. Q：Typora有15天的免费使用期限，有什么替代方案吗？

   A：使用盗版的Typora…或者换用Obsidian, 安装一些可以调用pandoc导出文件的插件。

