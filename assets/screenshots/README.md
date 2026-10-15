# 界面图版

本目录保存 README 使用的实际系统截图与图版。统一采用白底、分图标记、编号和中文图注，便于教学介绍和学术风格的功能展示。

| 图号 | 内容 | 图版 |
| --- | --- | --- |
| 1 | 真实课堂过程档案：原文、投入编码、历史状态 | [01-classroom-archive.png](figures/01-classroom-archive.png) |
| 2 | 教师多组课堂观察 | [02-teacher-workspace.png](figures/02-teacher-workspace.png) |
| 3 | 学生讨论与已发布教育支架 | [03-student-discussion.png](figures/03-student-discussion.png) |
| 4 | 教育智能体与平台集成、持续规则与 Skill 绑定 | [04-agent-integration.png](figures/04-agent-integration.png) |
| 5 | 持续偏题识别与自动发布的两个过程节点 | [05-automatic-intervention.png](figures/05-automatic-intervention.png) |
| 6 | 教师确认、发布与后续观察 | [06-teacher-review.png](figures/06-teacher-review.png) |

`captures/` 是未经业务内容修改的原始界面截图，`figures/` 是带编号与图注的 PNG 图版，`source/` 是对应 HTML 排版源文件；打开源文件即可按原始截图重新排版。详细图题与分图说明见 [index.json](index.json)。

截图中的学生为专门创建的模拟账号，学生发言为教学情境输入；分析与支架由真实模型 API 经 Agno SDK 生成。数据保存在 [backend/examples/classroom.json](../../backend/examples/classroom.json)，可在正常启动后的 `/examples` 页面逐步查看。

截图浏览器使用 UTC 时区，案例保留原始 Unix 时间戳；网页按访问者本地时区显示。截图只统一外部排版与图注，未改写原始消息、模型编码、指标或支架状态。观察前后变化不能用作干预有效性的因果证据。
